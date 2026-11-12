"""Gestión de bancos en PostgreSQL con auditoría transaccional."""

import re

from fastapi import HTTPException

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


def crear_banco(banco, actor: str, ip: str | None) -> dict:
    banco_id = banco.id.strip().upper() if banco.id else ""
    if banco_id and not re.fullmatch(r"[A-Z0-9-]{1,10}", banco_id):
        raise HTTPException(status_code=422, detail="El código del banco no es válido.")

    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("LOCK TABLE bancos IN SHARE ROW EXCLUSIVE MODE")
            if not banco_id:
                cur.execute(
                    """SELECT COALESCE(MAX(SUBSTRING(TRIM(id_banco) FROM 5)::integer), 0)
                       FROM bancos WHERE TRIM(id_banco) ~ '^BAN-[0-9]{6}$'"""
                )
                sequence = cur.fetchone()[0] + 1
                if sequence > 999999:
                    raise HTTPException(status_code=409, detail="Se agotaron los códigos automáticos de bancos.")
                banco_id = f"BAN-{sequence:06d}"

            cur.execute("SELECT 1 FROM bancos WHERE id_banco = %s", (banco_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe un banco con el código {banco_id}.")
            cur.execute("SELECT 1 FROM bancos WHERE LOWER(TRIM(ban_nombre)) = LOWER(%s)", (banco.name,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe un banco con el nombre '{banco.name}'.")
            cur.execute(
                "INSERT INTO bancos (id_banco, ban_nombre, estado_ban) VALUES (%s, %s, %s)",
                (banco_id, banco.name, banco.status),
            )
            return {"id": banco_id, "mensaje": f"Banco '{banco.name}' registrado exitosamente con código {banco_id}."}


def actualizar_banco(banco_id: str, banco, actor: str, ip: str | None) -> dict:
    clean_id = banco_id.strip().upper()
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("LOCK TABLE bancos IN SHARE ROW EXCLUSIVE MODE")
            cur.execute("SELECT 1 FROM bancos WHERE id_banco = %s FOR UPDATE", (clean_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"No se encontró el banco con código {clean_id}.")
            cur.execute(
                "SELECT 1 FROM bancos WHERE LOWER(TRIM(ban_nombre)) = LOWER(%s) AND id_banco <> %s",
                (banco.name, clean_id),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe un banco con el nombre '{banco.name}'.")
            cur.execute(
                "UPDATE bancos SET ban_nombre = %s, estado_ban = %s WHERE id_banco = %s",
                (banco.name, banco.status, clean_id),
            )
            return {"id": clean_id, "mensaje": f"Banco {clean_id} actualizado exitosamente."}
