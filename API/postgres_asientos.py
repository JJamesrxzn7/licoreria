"""Registro de asientos manuales abiertos, sin contabilizar saldos."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


def crear_asiento(entry, actor: str, ip: str | None) -> dict:
    total = sum((line.debit for line in entry.lines), Decimal("0"))
    if total > Decimal("99999.99"):
        raise HTTPException(status_code=422, detail="El total del asiento supera 99999.99.")
    ids = [line.account_id for line in entry.lines]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="Una cuenta no puede aparecer más de una vez en el asiento.")
    entry_date = (
        datetime.combine(date.fromisoformat(str(entry.entry_date)[:10]), time(12))
        if entry.entry_date is not None else None
    )
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute(
                """SELECT TRIM(id_cuenta), TRIM(cue_tipo), TRIM(estado_cue)
                   FROM cuentas WHERE TRIM(id_cuenta) = ANY(%s)
                   ORDER BY id_cuenta FOR SHARE""",
                (ids,),
            )
            accounts = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
            for account_id in ids:
                account = accounts.get(account_id)
                if not account or account[0] != "DET" or account[1] not in ("ACT", None):
                    raise HTTPException(
                        status_code=422,
                        detail=f"La cuenta {account_id} debe existir, estar activa y ser de detalle.",
                    )
            asiento_id = f"ASI{uuid4().hex[:7].upper()}"
            cur.execute(
                """INSERT INTO asientos
                   (id_asiento, asi_descripcion, asi_total_debe, asi_total_haber, asi_fechahora, user_id, estado_asi)
                   VALUES (%s, %s, %s, %s, COALESCE(%s, LOCALTIMESTAMP), %s, 'ABI')""",
                (asiento_id, entry.description, total, total, entry_date, actor),
            )
            for line in entry.lines:
                cur.execute(
                    """INSERT INTO ctaxasi (id_asiento, id_cuenta, cxa_debe, cxa_haber, estado_cxa)
                       VALUES (%s, %s, %s, %s, 'ABI')""",
                    (asiento_id, line.account_id, line.debit, line.credit),
                )
            return {"id": asiento_id, "estado": "ABI", "mensaje": "Asiento abierto registrado; aún no está contabilizado."}
