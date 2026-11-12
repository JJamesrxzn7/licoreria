"""Creación y anulación de ajustes sin impacto en inventario."""

from uuid import uuid4

from fastapi import HTTPException

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


def crear_ajuste(adjustment, actor: str, ip: str | None) -> dict:
    if len(adjustment.reason) > 30:
        raise HTTPException(status_code=422, detail="El motivo no puede superar 30 caracteres en PostgreSQL.")
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute(
                """SELECT TRIM(e.id_empleado)
                   FROM usuarios u JOIN empleados e ON e.id_empleado = u.id_empleado
                   WHERE u.id_usuario = %s AND u.estado_usr = 'ACT' AND e.estado_emp = 'ACT'""",
                (actor,),
            )
            employee = cur.fetchone()
            if not employee:
                raise HTTPException(status_code=403, detail="El usuario debe tener un empleado activo.")
            cur.execute(
                "SELECT 1 FROM productos WHERE id_producto = %s AND estado_prod = 'ACT' FOR SHARE",
                (adjustment.product_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=422, detail="El producto no existe o no está activo.")
            adjustment_id = f"AJU-{uuid4().hex[:11].upper()}"
            signed_quantity = adjustment.quantity if adjustment.type == "IN" else -adjustment.quantity
            cur.execute(
                """INSERT INTO ajustes
                   (id_ajuste, id_empleado, aju_descripcion, aju_fechahora, aju_num_produc, estado_aju)
                   VALUES (%s, %s, %s, NOW(), 1, 'ABI')""",
                (adjustment_id, employee[0], adjustment.reason),
            )
            cur.execute(
                """INSERT INTO proxaju
                   (id_ajuste, id_producto, pxa_cantidad, pxa_qty_ajustada, estado_pxaju)
                   VALUES (%s, %s, %s, %s, 'ABI')""",
                (adjustment_id, adjustment.product_id, adjustment.quantity, signed_quantity),
            )
            return {"id": adjustment_id, "estado": "ABI", "mensaje": "Ajuste registrado sin afectar el inventario."}


def anular_ajuste(adjustment_id: str, actor: str, ip: str | None) -> dict:
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT estado_aju FROM ajustes WHERE id_ajuste = %s FOR UPDATE", (adjustment_id,))
            current = cur.fetchone()
            if not current:
                raise HTTPException(status_code=404, detail="El ajuste de inventario no existe.")
            if current[0] != "ABI":
                raise HTTPException(status_code=409, detail="Solo se pueden anular ajustes abiertos.")
            cur.execute("UPDATE proxaju SET estado_pxaju = 'ANU' WHERE id_ajuste = %s", (adjustment_id,))
            cur.execute("UPDATE ajustes SET estado_aju = 'ANU' WHERE id_ajuste = %s", (adjustment_id,))
            return {"id": adjustment_id, "estado": "ANU", "mensaje": "Ajuste anulado sin afectar el inventario."}
