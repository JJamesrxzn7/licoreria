"""Creación de roles de nómina abiertos en una única transacción."""

from collections import defaultdict
from decimal import Decimal

import psycopg
from fastapi import HTTPException

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


MAX_AMOUNT = Decimal("99999.99")


def _aprobacion_disponible(cur) -> bool:
    cur.execute(
        """SELECT EXISTS (
               SELECT 1 FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
               WHERE t.tgrelid = 'pagos'::regclass AND t.tgname = 'trg_pago_apr'
                 AND NOT t.tgisinternal AND t.tgenabled IN ('O', 'A')
                 AND p.proname = 'fn_nomina_aprobacion_v1'
           )"""
    )
    return cur.fetchone()[0]


def crear(payroll, actor: str, ip: str | None) -> dict:
    bonus_total = sum((line.amount for line in payroll.bonus_lines), Decimal("0"))
    deduction_total = sum((line.amount for line in payroll.deduction_lines), Decimal("0"))
    net = payroll.base_salary + bonus_total - deduction_total
    if payroll.base_salary > Decimal("50000.00"):
        raise HTTPException(status_code=422, detail="El sueldo base no puede exceder $50,000.00.")
    if net < 0:
        raise HTTPException(status_code=422, detail="Los descuentos superan el ingreso total del colaborador.")
    if max(payroll.base_salary, bonus_total, deduction_total, net) > MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="Un importe del rol excede el límite de la base de datos.")

    bonuses = defaultdict(lambda: Decimal("0"))
    for line in payroll.bonus_lines:
        bonuses[(line.bonus_id, line.line_date or payroll.end_date)] += line.amount
    deductions = defaultdict(lambda: Decimal("0"))
    for line in payroll.deduction_lines:
        deductions[(line.deduction_id, line.line_date or payroll.end_date)] += line.amount
    if any(value > MAX_AMOUNT for value in (*bonuses.values(), *deductions.values())):
        raise HTTPException(status_code=422, detail="El total por concepto y fecha excede el límite de la base de datos.")

    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('licoreria_nomina_id'))")
            cur.execute(
                """SELECT COALESCE(MAX(
                       CASE WHEN TRIM(id_pago) ~ '^PAG-[0-9]+$'
                            THEN SUBSTRING(TRIM(id_pago) FROM 5)::integer ELSE 0 END
                   ), 0) FROM pagos"""
            )
            sequence = cur.fetchone()[0] + 1
            if sequence > 999999:
                raise HTTPException(status_code=409, detail="Se agotaron los códigos disponibles para roles de pago.")
            payroll_id = f"PAG-{sequence:06d}"

            cur.execute(
                "SELECT 1 FROM empleados WHERE id_empleado = %s AND estado_emp = 'ACT' FOR SHARE",
                (payroll.employee_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="El colaborador no existe o no está activo.")
            for kind, table, id_column, status_column, items in (
                ("bonificación", "bonificaciones", "id_bonificacion", "estado_bon", bonuses),
                ("descuento", "descuentos", "id_descuento", "estado_des", deductions),
            ):
                if not items:
                    continue
                ids = sorted({item_id for item_id, _ in items})
                cur.execute(
                    f"SELECT TRIM({id_column}) FROM {table} "
                    f"WHERE {id_column} = ANY(%s) AND COALESCE({status_column}, 'ACT') = 'ACT' FOR SHARE",
                    (ids,),
                )
                active_ids = {row[0] for row in cur.fetchall()}
                missing = set(ids) - active_ids
                if missing:
                    raise HTTPException(
                        status_code=422,
                        detail=f"El concepto de {kind} {sorted(missing)[0]} no existe o no está activo.",
                    )

            cur.execute(
                """INSERT INTO pagos
                   (id_pago, pag_descripcion, pag_fecha_inicio, pag_fecha_fin, user_id, estado_pag)
                   VALUES (%s, %s, %s, %s, %s, 'ABI')""",
                (payroll_id, payroll.description, payroll.start_date, payroll.end_date, actor),
            )
            cur.execute(
                """INSERT INTO pagxemp
                   (id_pago, id_empleado, pxe_sueldo, pxe_bonificaciones, pxe_descuentos,
                    pxe_valor_neto, estado_pxe)
                   VALUES (%s, %s, %s, %s, %s, %s, 'ABI')""",
                (payroll_id, payroll.employee_id, payroll.base_salary, bonus_total, deduction_total, net),
            )
            for (bonus_id, line_date), amount in sorted(bonuses.items()):
                cur.execute(
                    """INSERT INTO bonxempxpag
                       (id_pago, id_empleado, id_bonificacion, bxe_fecha, bxe_valor, estado_bxe)
                       VALUES (%s, %s, %s, %s, %s, 'ACT')""",
                    (payroll_id, payroll.employee_id, bonus_id, line_date, amount),
                )
            for (deduction_id, line_date), amount in sorted(deductions.items()):
                cur.execute(
                    """INSERT INTO desxempxpag
                       (id_pago, id_empleado, id_descuento, dxe_fecha, dxe_valor, estado_dxe)
                       VALUES (%s, %s, %s, %s, %s, 'ACT')""",
                    (payroll_id, payroll.employee_id, deduction_id, line_date, amount),
                )
            return {
                "id": payroll_id,
                "estado": "ABI",
                "neto": str(net.quantize(Decimal("0.01"))),
                "mensaje": f"Rol de pago {payroll_id} generado correctamente.",
            }


def anular(payroll_id: str, actor: str, ip: str | None) -> dict:
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT estado_pag FROM pagos WHERE id_pago = %s FOR UPDATE", (payroll_id,))
            current = cur.fetchone()
            if not current:
                raise HTTPException(status_code=404, detail=f"No existe el rol de pago {payroll_id}.")
            if current[0] != "ABI":
                raise HTTPException(status_code=409, detail="Solo se pueden anular roles de pago abiertos.")
            cur.execute("UPDATE pagos SET estado_pag = 'ANU' WHERE id_pago = %s", (payroll_id,))
            cur.execute("UPDATE pagxemp SET estado_pxe = 'ANU' WHERE id_pago = %s", (payroll_id,))
            return {"id": payroll_id, "estado": "ANU", "mensaje": "Rol de pago anulado."}


def aprobar(payroll_id: str, actor: str, ip: str | None) -> dict:
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            if not _aprobacion_disponible(cur):
                raise HTTPException(status_code=503, detail="Falta aplicar la migración de aprobación de nómina.")
            cur.execute("SELECT estado_pag FROM pagos WHERE id_pago = %s FOR UPDATE", (payroll_id,))
            current = cur.fetchone()
            if not current:
                raise HTTPException(status_code=404, detail=f"No existe el rol de pago {payroll_id}.")
            if current[0] != "ABI":
                raise HTTPException(status_code=409, detail="Solo se pueden aprobar roles de pago abiertos.")
            try:
                cur.execute("UPDATE pagos SET estado_pag = 'APR' WHERE id_pago = %s", (payroll_id,))
            except psycopg.errors.RaiseException as error:
                messages = {
                    "No hay centro de costo activo para el departamento del empleado.",
                    "Configure cuentas activas distintas de gasto de nomina y obligaciones laborales.",
                    "El total de la nomina debe ser positivo.",
                }
                if error.diag.message_primary not in messages:
                    raise
                raise HTTPException(status_code=409, detail=error.diag.message_primary) from error
            cur.execute("UPDATE pagxemp SET estado_pxe = 'APR' WHERE id_pago = %s", (payroll_id,))
            return {"id": payroll_id, "estado": "APR", "mensaje": "Rol de pago aprobado y asiento pendiente generado."}
