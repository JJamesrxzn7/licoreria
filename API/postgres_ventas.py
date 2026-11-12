"""Ciclo PostgreSQL de venta y despacho; requiere la migración 20261108.

Las cantidades de confirmar_entrega son acumuladas, no incrementos. Las rutas
deben autorizar al actor antes de llamar estas funciones. Las excepciones de
dominio llevan status_code y detail para su traducción HTTP.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from postgres_connection import connect_postgres

CENT = Decimal("0.01")
MAX_MONEY = Decimal("99999.99")


class VentaError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _id(value, name, maximum):
    value = str(value or "").strip()
    if not value or len(value) > maximum:
        raise VentaError(422, f"{name} inválido.")
    return value


def _amount(value, name, maximum=MAX_MONEY):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or value > maximum or value != value.quantize(CENT):
            raise ValueError()
        return value
    except (InvalidOperation, ValueError):
        raise VentaError(422, f"{name} debe ser no negativo y tener máximo dos decimales.")


def _context(cursor, actor, client_ip):
    actor = _id(actor, "Usuario", 16)
    cursor.execute(
        """SELECT TRIM(u.id_empleado) AS empleado
             FROM usuarios u JOIN empleados e ON e.id_empleado = u.id_empleado
            WHERE u.id_usuario = %s AND u.estado_usr = 'ACT' AND e.estado_emp = 'ACT'""",
        (actor,),
    )
    row = cursor.fetchone()
    if not row:
        raise VentaError(401, "El usuario o su empleado no está activo.")
    cursor.execute(
        "SELECT set_config('app.auditoria_usuario', %s, true), "
        "set_config('app.auditoria_ip', %s, true)", (actor, client_ip or "")
    )
    return row["empleado"]


def _managed_invoice(cursor, invoice_id):
    cursor.execute(
        """SELECT f.estado_fac, f.fac_total, c.id_asiento, c.id_entrega
             FROM facturas f LEFT JOIN ventas_control c ON c.id_factura = f.id_factura
            WHERE f.id_factura = %s FOR UPDATE OF f""", (invoice_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise VentaError(404, "Factura no encontrada.")
    cursor.execute("SELECT 1 FROM ventas_control WHERE id_factura = %s", (invoice_id,))
    if not cursor.fetchone():
        raise VentaError(409, "Factura histórica: requiere conciliación antes de operar.")
    return row


def _validate_delivery(cursor, invoice_id, delivery_id):
    """Rechazar entregas ausentes, adicionales o inconsistentes antes de mutar."""
    cursor.execute(
        "SELECT id_entrega FROM entregas WHERE id_factura = %s ORDER BY id_entrega",
        (invoice_id,),
    )
    deliveries = cursor.fetchall()
    if len(deliveries) != 1 or str(deliveries[0]["id_entrega"]).strip() != str(delivery_id or "").strip():
        raise VentaError(409, "Las entregas de la factura son inconsistentes; requiere conciliación.")
    cursor.execute(
        """SELECT TRIM(id_producto) AS id, pxf_cantidad AS cantidad
             FROM proxfac WHERE id_factura = %s ORDER BY id_producto""", (invoice_id,)
    )
    invoiced = {row["id"]: row["cantidad"] for row in cursor.fetchall()}
    cursor.execute(
        """SELECT TRIM(id_producto) AS id, pxe_cantidad AS cantidad, pxe_qty_entregada AS entregada
             FROM proxent WHERE id_entrega = %s ORDER BY id_producto""", (delivery_id,)
    )
    details = cursor.fetchall()
    if not invoiced or {row["id"]: row["cantidad"] for row in details} != invoiced or any(
        row["entregada"] < 0 or row["entregada"] > row["cantidad"] for row in details
    ):
        raise VentaError(409, "El detalle de entrega no coincide con la factura; requiere conciliación.")
    return details


def crear_venta(sale, actor, client_ip=None, *, request_id):
    """request_id estable por intento lógico; nunca generar uno nuevo al reintentar."""
    actor = _id(actor, "Usuario", 16)
    request_id = str(request_id or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", request_id):
        raise VentaError(422, "Se requiere un identificador de solicitud estable de 16 a 64 caracteres.")
    customer_id = _id(sale.customer_id, "Cliente", 10)
    rate = _amount(sale.tax_rate, "Tasa de IVA", Decimal("100"))
    discount = _amount(sale.discount_amount, "Descuento")
    payment = str(sale.payment_method or "").strip()
    description = str(sale.description or "").strip()
    if not payment or len(payment) > 20 or len(description) > 60:
        raise VentaError(422, "Forma de pago o descripción inválida.")
    if sale.installments != 1:
        raise VentaError(422, "Las ventas a cuotas no están implementadas.")
    lines = []
    seen = set()
    for item in sale.items:
        pid = _id(item.product_id, "Producto", 10)
        if pid in seen:
            raise VentaError(422, "No se admiten productos repetidos en una factura.")
        seen.add(pid)
        quantity = item.quantity
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0 or quantity > 2147483647:
            raise VentaError(422, "Cantidad de venta inválida.")
        price = _amount(item.unit_price, "Precio unitario")
        line_total = (price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        if line_total > MAX_MONEY:
            raise VentaError(422, "El subtotal de línea excede el límite.")
        lines.append((pid, quantity, price, line_total))
    if not lines:
        raise VentaError(422, "La factura requiere productos.")
    subtotal = sum((line[3] for line in lines), Decimal("0"))
    if subtotal > MAX_MONEY or discount > subtotal:
        raise VentaError(422, "Subtotal o descuento inválido.")
    tax = ((subtotal - discount) * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    total = subtotal - discount + tax
    if tax > MAX_MONEY or total > MAX_MONEY:
        raise VentaError(422, "El total excede el límite de la base de datos.")
    fingerprint = hashlib.sha256(json.dumps({
        "cliente": customer_id, "tasa": str(rate.quantize(CENT)),
        "descuento": str(discount.quantize(CENT)), "forma": payment,
        "descripcion": description,
        "items": [(p, q, str(price.quantize(CENT))) for p, q, price, _ in sorted(lines)],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    invoice_id, delivery_id = "FAC" + uuid4().hex[:12].upper(), "ENT" + uuid4().hex[:12].upper()
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            employee = _context(cur, actor, client_ip)
            # Serializa reintentos concurrentes antes de consultar la clave única.
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (f"{actor}:{request_id}",))
            cur.execute(
                """SELECT c.huella, TRIM(c.id_factura) AS id, TRIM(c.id_entrega) AS entrega,
                          f.estado_fac, f.fac_total
                     FROM ventas_control c JOIN facturas f ON f.id_factura = c.id_factura
                    WHERE c.id_usuario = %s AND c.id_solicitud = %s""",
                (actor, request_id),
            )
            previous = cur.fetchone()
            if previous:
                if previous["huella"] != fingerprint:
                    raise VentaError(409, "El identificador de solicitud ya corresponde a otra venta.")
                if not previous["entrega"]:
                    raise VentaError(409, "Solicitud previa incompleta; requiere conciliación.")
                return {"id": previous["id"], "deliveryId": previous["entrega"],
                        "estado": previous["estado_fac"], "total": str(previous["fac_total"]),
                        "mensaje": "Solicitud previamente procesada."}
            cur.execute("SELECT 1 FROM clientes WHERE id_cliente = %s AND estado_cli = 'ACT'", (customer_id,))
            if not cur.fetchone():
                raise VentaError(404, "Cliente inexistente o inactivo.")
            cur.execute(
                """INSERT INTO facturas
                   (id_factura, id_cliente, id_empleado, fac_descripcion, fac_fecha,
                    fac_subtotal, fac_descuento, fac_iva, fac_total, fac_formapago,
                    fac_tasa_iva, estado_fac)
                   VALUES (%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,'ABI')""",
                (invoice_id, customer_id, employee, description, subtotal, discount, tax, total, payment, rate),
            )
            cur.execute(
                "INSERT INTO ventas_control (id_factura,id_usuario,id_solicitud,huella) VALUES (%s,%s,%s,%s)",
                (invoice_id, actor, request_id, fingerprint),
            )
            # Orden estable para evitar deadlocks entre facturas concurrentes.
            for pid, qty, price, line_total in sorted(lines):
                try:
                    cur.execute(
                        """INSERT INTO proxfac
                           (id_factura,id_producto,pxf_cantidad,pxf_precio,pxf_subtotal,estado_pxfac)
                           VALUES (%s,%s,%s,%s,%s,'ABI')""",
                        (invoice_id, pid, qty, price, line_total),
                    )
                except psycopg.errors.RaiseException as error:
                    if error.diag.message_primary == "Producto inexistente, inactivo o con stock insuficiente":
                        raise VentaError(409, f"Producto {pid} inexistente, inactivo o con stock insuficiente.") from error
                    raise
            cur.execute(
                """INSERT INTO entregas
                   (id_entrega,id_factura,ent_descripcion,ent_fechahora,ent_num_produc,estado_ent)
                   VALUES (%s,%s,'Entrega venta',NOW(),%s,'PEN')""",
                (delivery_id, invoice_id, len(lines)),
            )
            cur.execute("UPDATE ventas_control SET id_entrega = %s WHERE id_factura = %s",
                        (delivery_id, invoice_id))
            for pid, qty, _, _ in sorted(lines):
                cur.execute(
                    """INSERT INTO proxent
                       (id_entrega,id_producto,pxe_cantidad,pxe_qty_entregada,pxe_motivo,estado_pxent)
                       VALUES (%s,%s,%s,0,NULL,'PEN')""", (delivery_id, pid, qty)
                )
    return {"id": invoice_id, "deliveryId": delivery_id, "estado": "ABI",
            "total": str(total), "mensaje": "Venta registrada."}


def listar_ventas():
    """Tasa exacta guardada en cada factura; NULL significa histórica desconocida."""
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT TRIM(f.id_factura) AS id, f.fac_fecha AS date,
                          TRIM(f.id_cliente) AS "customerId", TRIM(c.cli_nombre) AS "customerName",
                          f.fac_subtotal AS subtotal, f.fac_descuento AS discount,
                          f.fac_tasa_iva AS "taxRate", f.fac_iva AS tax, f.fac_total AS total,
                          f.fac_formapago AS "paymentMethod", 1 AS installments, f.estado_fac AS status
                     FROM facturas f JOIN clientes c ON c.id_cliente = f.id_cliente
                    ORDER BY f.fac_fecha DESC, f.id_factura DESC"""
            )
            invoices = cur.fetchall()
            cur.execute(
                """SELECT TRIM(d.id_factura) AS factura, TRIM(d.id_producto) AS "productId",
                          TRIM(p.pro_descripcion) AS "productName", d.pxf_cantidad AS qty,
                          d.pxf_precio AS price, d.pxf_subtotal AS subtotal
                     FROM proxfac d JOIN productos p ON p.id_producto = d.id_producto
                    ORDER BY d.id_factura, d.id_producto"""
            )
            details = {}
            for item in cur.fetchall():
                details.setdefault(item.pop("factura"), []).append(item)
            for invoice in invoices:
                invoice["items"] = details.get(invoice["id"], [])
            return invoices


def aprobar_factura(invoice_id, actor, client_ip=None):
    invoice_id = _id(invoice_id, "Factura", 15)
    actor = _id(actor, "Usuario", 16)
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _context(cur, actor, client_ip)
            row = _managed_invoice(cur, invoice_id)
            if row["estado_fac"] != "ABI" or row["id_asiento"] is not None:
                raise VentaError(409, "Solo se aprueban facturas abiertas.")
            _validate_delivery(cur, invoice_id, row["id_entrega"])
            # Conserva el asiento pendiente que creaba el trigger anterior,
            # pero usa un identificador no derivado del sufijo de factura.
            entry_id = "ASI" + uuid4().hex[:7].upper()
            cur.execute(
                """INSERT INTO asientos
                   (id_asiento,asi_descripcion,asi_total_debe,asi_total_haber,asi_fechahora,user_id,estado_asi)
                   VALUES (%s,%s,%s,%s,NOW(),%s,'PEN')""",
                (entry_id, f"Venta {invoice_id}", row["fac_total"], row["fac_total"], actor),
            )
            cur.execute("UPDATE ventas_control SET id_asiento = %s WHERE id_factura = %s", (entry_id, invoice_id))
            cur.execute("UPDATE proxfac SET estado_pxfac = 'APR' WHERE id_factura = %s", (invoice_id,))
            cur.execute("UPDATE facturas SET estado_fac = 'APR' WHERE id_factura = %s", (invoice_id,))
    return {"id": invoice_id, "estado": "APR", "mensaje": "Factura aprobada."}


def anular_factura(invoice_id, actor, client_ip=None):
    invoice_id = _id(invoice_id, "Factura", 15)
    actor = _id(actor, "Usuario", 16)
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _context(cur, actor, client_ip)
            invoice = _managed_invoice(cur, invoice_id)
            if invoice["estado_fac"] not in ("ABI", "APR"):
                raise VentaError(409, "La factura ya está anulada o no se puede anular.")
            _validate_delivery(cur, invoice_id, invoice["id_entrega"])
            cur.execute(
                """SELECT e.id_entrega, e.estado_ent, d.pxe_qty_entregada
                   FROM entregas e JOIN proxent d ON d.id_entrega = e.id_entrega
                   WHERE e.id_factura = %s ORDER BY e.id_entrega, d.id_producto""",
                (invoice_id,),
            )
            deliveries = cur.fetchall()
            if not deliveries or any(d["pxe_qty_entregada"] != 0 or d["estado_ent"] != "PEN" for d in deliveries):
                raise VentaError(409, "No se puede anular una factura con entregas realizadas o inconsistentes.")
            if invoice["id_asiento"]:
                cur.execute("SELECT estado_asi FROM asientos WHERE id_asiento = %s FOR UPDATE",
                            (invoice["id_asiento"],))
                entry = cur.fetchone()
                if not entry or entry["estado_asi"] != "PEN":
                    raise VentaError(409, "El asiento ya no está pendiente; requiere reverso contable.")
                cur.execute("UPDATE asientos SET estado_asi = 'ANU' WHERE id_asiento = %s", (invoice["id_asiento"],))
            cur.execute("SELECT id_producto, pxf_cantidad FROM proxfac WHERE id_factura = %s ORDER BY id_producto",
                        (invoice_id,))
            details = cur.fetchall()
            if not details:
                raise VentaError(409, "La factura no tiene detalle para restituir stock.")
            for detail in details:
                cur.execute(
                    """UPDATE productos SET pro_qty_egresos = pro_qty_egresos - %s,
                              pro_saldo_final = pro_saldo_final + %s
                       WHERE id_producto = %s AND pro_qty_egresos >= %s""",
                    (detail["pxf_cantidad"], detail["pxf_cantidad"], detail["id_producto"], detail["pxf_cantidad"]),
                )
                if cur.rowcount != 1:
                    raise VentaError(409, "Stock inconsistente: no es posible restituirlo.")
            cur.execute("UPDATE proxent SET estado_pxent = 'ANU' WHERE id_entrega IN "
                        "(SELECT id_entrega FROM entregas WHERE id_factura = %s)", (invoice_id,))
            cur.execute("UPDATE entregas SET estado_ent = 'ANU' WHERE id_factura = %s", (invoice_id,))
            cur.execute("UPDATE proxfac SET estado_pxfac = 'ANU' WHERE id_factura = %s", (invoice_id,))
            cur.execute("SELECT set_config('app.venta_anulacion', %s, true)", (invoice_id,))
            cur.execute("UPDATE facturas SET estado_fac = 'ANU' WHERE id_factura = %s", (invoice_id,))
    return {"id": invoice_id, "estado": "ANU", "mensaje": "Factura anulada y stock restituido."}


def confirmar_entrega(delivery_id, payload, actor, client_ip=None):
    delivery_id = _id(delivery_id, "Entrega", 15)
    actor = _id(actor, "Usuario", 16)
    requested = {}
    for item in payload.items:
        pid = _id(item.product_id, "Producto", 10)
        if pid in requested:
            raise VentaError(422, "No se admiten productos repetidos.")
        qty = item.delivered_qty
        reason = str(item.reason or "").strip()
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0 or len(reason) > 60:
            raise VentaError(422, "Cantidad o motivo inválido.")
        requested[pid] = (qty, reason)
    if not requested:
        raise VentaError(422, "La entrega requiere detalle.")
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _context(cur, actor, client_ip)
            cur.execute("SELECT id_factura FROM entregas WHERE id_entrega = %s", (delivery_id,))
            ref = cur.fetchone()
            if not ref:
                raise VentaError(404, "Entrega no encontrada.")
            invoice = _managed_invoice(cur, ref["id_factura"])
            if invoice["estado_fac"] != "APR":
                raise VentaError(409, "La factura debe estar aprobada para despachar.")
            _validate_delivery(cur, ref["id_factura"], invoice["id_entrega"])
            if str(invoice["id_entrega"] or "").strip() != delivery_id:
                raise VentaError(409, "Entrega no gestionada por esta factura.")
            cur.execute("SELECT estado_ent FROM entregas WHERE id_entrega = %s FOR UPDATE", (delivery_id,))
            if cur.fetchone()["estado_ent"] != "PEN":
                raise VentaError(409, "La entrega ya fue completada o anulada.")
            cur.execute(
                """SELECT TRIM(id_producto) AS id, pxe_cantidad, pxe_qty_entregada
                   FROM proxent WHERE id_entrega = %s ORDER BY id_producto FOR UPDATE""", (delivery_id,)
            )
            details = cur.fetchall()
            if {d["id"] for d in details} != set(requested):
                raise VentaError(422, "Debe informar exactamente todos los productos de la entrega.")
            changed, complete = False, True
            for detail in details:
                qty, reason = requested[detail["id"]]
                if qty < detail["pxe_qty_entregada"] or qty > detail["pxe_cantidad"]:
                    raise VentaError(422, "La cantidad acumulada no puede disminuir ni superar lo facturado.")
                if qty < detail["pxe_cantidad"] and not reason:
                    raise VentaError(422, "Debe indicar el motivo de la entrega incompleta.")
                changed |= qty > detail["pxe_qty_entregada"]
                complete &= qty == detail["pxe_cantidad"]
            if not changed:
                raise VentaError(409, "No se registraron nuevas unidades entregadas.")
            for detail in details:
                qty, reason = requested[detail["id"]]
                cur.execute(
                    """UPDATE proxent SET pxe_qty_entregada = %s, pxe_motivo = %s,
                       estado_pxent = %s WHERE id_entrega = %s AND id_producto = %s""",
                    (qty, reason or None, "ENT" if qty == detail["pxe_cantidad"] else "PEN",
                     delivery_id, detail["id"]),
                )
            status = "ENT" if complete else "PEN"
            cur.execute("UPDATE entregas SET estado_ent = %s WHERE id_entrega = %s", (status, delivery_id))
    return {"id": delivery_id, "estado": status,
            "mensaje": "Entrega completada." if complete else "Entrega parcial; queda pendiente."}
