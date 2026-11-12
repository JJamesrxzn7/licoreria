import re
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException

from postgres_connection import connect_postgres


def _set_actor(cursor, actor: str, ip: str | None) -> None:
    cursor.execute(
        "SELECT set_config('app.auditoria_usuario', %s, true), "
        "set_config('app.auditoria_ip', %s, true)",
        (actor, ip or ""),
    )


def crear_compra(
    supplier_id: str,
    delivery_date: datetime | date | str | None,
    tax_rate: Decimal,
    items: list[tuple[str, int, Decimal]],
    subtotal: Decimal,
    tax: Decimal,
    total: Decimal,
    actor: str,
    ip: str | None,
) -> dict:
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('licoreria_compras_id'))")
            cur.execute("SELECT trim(id_compra) FROM compras")
            numbers = []
            for (existing,) in cur.fetchall():
                match = re.fullmatch(r"(?:COM-|OC-?)(\d+)", existing, re.IGNORECASE)
                if match:
                    numbers.append(int(match.group(1)))
            number = max(numbers, default=0) + 1
            if number > 999999:
                raise HTTPException(status_code=409, detail="No quedan códigos de compra disponibles.")
            order_id = f"COM-{number:06d}"

            cur.execute(
                "SELECT 1 FROM proveedores WHERE id_proveedor = %s AND estado_prv = 'ACT'",
                (supplier_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=422, detail="El proveedor no existe o no está activo.")
            product_ids = [item[0] for item in items]
            cur.execute(
                "SELECT trim(id_producto) FROM productos WHERE estado_prod = 'ACT' "
                "AND id_producto = ANY(%s)",
                (product_ids,),
            )
            missing = set(product_ids) - {row[0] for row in cur.fetchall()}
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=f"Productos inexistentes o inactivos: {', '.join(sorted(missing))}.",
                )

            cur.execute(
                "CALL public.sp_compra_crear(%s, %s, %s, %s, %s, %s, %s)",
                (order_id, supplier_id, delivery_date, subtotal, tax, total, actor),
            )
            cur.execute(
                "UPDATE compras SET oc_tasaiva = %s WHERE id_compra = %s",
                (tax_rate, order_id),
            )
            for product_id, quantity, unit_cost in items:
                cur.execute(
                    "CALL public.sp_compra_agregar_producto(%s, %s, %s, %s, %s)",
                    (order_id, product_id, quantity, unit_cost, actor),
                )
            cur.execute(
                "SELECT oc_subtotal, oc_iva, oc_total FROM compras WHERE id_compra = %s",
                (order_id,),
            )
            if cur.fetchone() != (subtotal, tax, total):
                raise HTTPException(
                    status_code=500, detail="Los totales calculados por la base no coinciden."
                )
            return {
                "id": order_id, "estado": "ABI", "subtotal": str(subtotal),
                "iva": str(tax), "total": str(total),
                "mensaje": f"Orden {order_id} creada exitosamente.",
            }


def cambiar_estado_compra(order_id: str, approve: bool, actor: str, ip: str | None) -> dict:
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT estado_oc FROM compras WHERE id_compra = %s FOR UPDATE", (order_id,))
            order = cur.fetchone()
            if not order:
                raise HTTPException(status_code=404, detail="La orden de compra no existe.")
            if order[0] != "ABI":
                raise HTTPException(status_code=409, detail="La orden ya no está abierta.")
            if approve:
                cur.execute("CALL public.sp_compra_aprobar(%s, %s)", (order_id, actor))
                cur.execute(
                    "SELECT trim(id_recibo) FROM recepciones WHERE id_compra = %s "
                    "ORDER BY rec_fechahora DESC, id_recibo DESC LIMIT 1",
                    (order_id,),
                )
                receipt = cur.fetchone()
                if receipt is None:
                    raise HTTPException(
                        status_code=500, detail="La base no generó la recepción de la compra."
                    )
                receipt_id = receipt[0]
                cur.execute(
                    """
                    INSERT INTO proxrec (id_recibo, id_producto, pxr_cantidad,
                                         pxr_qty_recibida, pxr_motivo, estado_pxrec)
                    SELECT %s, id_producto, pxo_cantidad, 0, NULL, 'PEN'
                    FROM proxoc WHERE id_compra = %s
                    """,
                    (receipt_id, order_id),
                )
                cur.execute(
                    "UPDATE recepciones SET rec_num_produc = "
                    "(SELECT count(*) FROM proxrec WHERE id_recibo = %s) WHERE id_recibo = %s",
                    (receipt_id, receipt_id),
                )
                state, label = "APR", "aprobada"
            else:
                cur.execute("CALL public.sp_compra_anular(%s, %s)", (order_id, actor))
                state, label = "ANU", "anulada"
            return {"id": order_id, "estado": state, "mensaje": f"Orden {order_id} {label} exitosamente."}


def confirmar_recepcion(
    receipt_id: str, items: list[tuple[str, int, str]], actor: str, ip: str | None,
) -> dict:
    product_ids = [product_id for product_id, _, _ in items]
    if len(set(product_ids)) != len(product_ids):
        raise HTTPException(status_code=422, detail="Cada producto debe aparecer una sola vez.")
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT estado_rec FROM recepciones WHERE id_recibo = %s FOR UPDATE", (receipt_id,))
            receipt = cur.fetchone()
            if not receipt:
                raise HTTPException(status_code=404, detail="La recepción no existe.")
            if receipt[0] != "PEN":
                raise HTTPException(status_code=409, detail="La recepción ya no está pendiente.")
            cur.execute(
                "SELECT trim(id_producto), pxr_cantidad, pxr_qty_recibida "
                "FROM proxrec WHERE id_recibo = %s FOR UPDATE",
                (receipt_id,),
            )
            expected = {product_id: (quantity, received) for product_id, quantity, received in cur.fetchall()}
            if not expected or set(product_ids) != set(expected):
                raise HTTPException(
                    status_code=422,
                    detail="Debes informar todos los productos de la recepción, sin añadir otros.",
                )
            for product_id, received, reason in items:
                quantity, previous = expected[product_id]
                if received != quantity and not reason.strip():
                    raise HTTPException(
                        status_code=422,
                        detail=f"Debes indicar el motivo de la diferencia del producto {product_id}.",
                    )
                cur.execute(
                    "UPDATE proxrec SET pxr_qty_recibida = %s, pxr_motivo = %s, estado_pxrec = 'APR' "
                    "WHERE id_recibo = %s AND id_producto = %s",
                    (received, reason.strip()[:60] or None, receipt_id, product_id),
                )
                delta = received - previous
                if delta:
                    cur.execute(
                        "UPDATE productos SET pro_qty_ingresos = pro_qty_ingresos + %s, "
                        "pro_saldo_final = pro_saldo_final + %s WHERE id_producto = %s",
                        (delta, delta, product_id),
                    )
            cur.execute("UPDATE recepciones SET estado_rec = 'APR' WHERE id_recibo = %s", (receipt_id,))
            return {
                "id": receipt_id, "estado": "APR",
                "mensaje": "Ingreso a bodega confirmado exitosamente.",
            }
