"""Creación de cuentas contables sin modificar cuentas existentes."""

from fastapi import HTTPException

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


def crear_cuenta(account, actor: str, ip: str | None) -> dict:
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT 1 FROM tipo_cuenta WHERE id_tipo_cta = %s", (account.type,))
            if not cur.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail=f"El tipo de cuenta {account.type} no existe; solicita su configuración al administrador.",
                )
            cur.execute(
                """INSERT INTO cuentas
                   (id_cuenta, cue_descripcion, cue_tipo, cue_debe00, cue_haber00, estado_cue)
                   VALUES (%s, %s, %s, 0, 0, 'ACT')
                   ON CONFLICT (id_cuenta) DO NOTHING
                   RETURNING TRIM(id_cuenta)""",
                (account.id, account.name, account.type),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe una cuenta con el código {account.id}.")
            label = "MAYOR" if account.type == "MAY" else "DETALLE"
            return {"id": account.id, "mensaje": f"Cuenta {account.id} registrada exitosamente como tipo {label}."}
