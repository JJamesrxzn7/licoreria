"""Gestión de conceptos de nómina."""

from fastapi import HTTPException
from psycopg import sql

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


CATALOGOS = {
    "bonificaciones": ("bonificaciones", "id_bonificacion", "bon_descripcion", "bon_valor", "estado_bon", "BON"),
    "descuentos": ("descuentos", "id_descuento", "des_descripcion", "des_valor", "estado_des", "DES"),
}


def crear(tipo: str, data, actor: str, ip: str | None) -> dict:
    if len(data.name) > 40:
        raise HTTPException(status_code=422, detail="El nombre no puede superar 40 caracteres en PostgreSQL.")
    if data.status != "ACT":
        raise HTTPException(status_code=422, detail="Los conceptos nuevos deben crearse activos.")
    table, id_col, name_col, value_col, status_col, prefix = CATALOGOS[tipo]
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(table)))
            cur.execute(sql.SQL("SELECT 1 FROM {} WHERE LOWER(TRIM({})) = LOWER(%s)").format(
                sql.Identifier(table), sql.Identifier(name_col)), (data.name,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe un concepto con el nombre '{data.name}'.")
            cur.execute(sql.SQL(
                "SELECT COALESCE(MAX(CASE WHEN TRIM({}) ~ %s "
                "THEN SUBSTRING(TRIM({}) FROM 5)::integer ELSE 0 END), 0) FROM {}"
            ).format(sql.Identifier(id_col), sql.Identifier(id_col), sql.Identifier(table)),
                (f"^{prefix}-[0-9]{{6}}$",))
            number = cur.fetchone()[0] + 1
            if number > 999999:
                raise HTTPException(status_code=409, detail="Se agotaron los códigos automáticos del catálogo.")
            catalog_id = f"{prefix}-{number:06d}"
            cur.execute(sql.SQL("INSERT INTO {} ({}, {}, {}, {}) VALUES (%s, %s, %s, 'ACT')").format(
                sql.Identifier(table), sql.Identifier(id_col), sql.Identifier(name_col),
                sql.Identifier(value_col), sql.Identifier(status_col)),
                (catalog_id, data.name, data.amount))
            return {"id": catalog_id, "mensaje": f"Concepto '{data.name}' creado correctamente."}


def actualizar(tipo: str, catalog_id: str, data, actor: str, ip: str | None) -> dict:
    if len(data.name) > 40:
        raise HTTPException(status_code=422, detail="El nombre no puede superar 40 caracteres en PostgreSQL.")
    table, id_col, name_col, value_col, status_col, _ = CATALOGOS[tipo]
    clean_id = catalog_id.strip().upper()
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(table)))
            cur.execute(sql.SQL("SELECT COALESCE(TRIM({}), 'ACT') FROM {} WHERE {} = %s FOR UPDATE").format(
                sql.Identifier(status_col), sql.Identifier(table), sql.Identifier(id_col)), (clean_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"No se encontró el concepto '{clean_id}'.")
            if row[0] == "ACT" and data.status == "INA":
                raise HTTPException(status_code=403, detail="La desactivación requiere permiso para anular.")
            cur.execute(sql.SQL(
                "SELECT 1 FROM {} WHERE LOWER(TRIM({})) = LOWER(%s) AND {} <> %s"
            ).format(sql.Identifier(table), sql.Identifier(name_col), sql.Identifier(id_col)),
                (data.name, clean_id))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe otro concepto con el nombre '{data.name}'.")
            cur.execute(sql.SQL("UPDATE {} SET {} = %s, {} = %s, {} = %s WHERE {} = %s").format(
                sql.Identifier(table), sql.Identifier(name_col), sql.Identifier(value_col),
                sql.Identifier(status_col), sql.Identifier(id_col)),
                (data.name, data.amount, data.status, clean_id))
            return {"id": clean_id, "mensaje": f"Concepto '{clean_id}' actualizado correctamente."}


def desactivar(tipo: str, catalog_id: str, actor: str, ip: str | None) -> dict:
    table, id_col, _, _, status_col, _ = CATALOGOS[tipo]
    clean_id = catalog_id.strip().upper()
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute(sql.SQL("SELECT TRIM({}) FROM {} WHERE {} = %s FOR UPDATE").format(
                sql.Identifier(status_col), sql.Identifier(table), sql.Identifier(id_col)), (clean_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"No se encontró el concepto '{clean_id}'.")
            if row[0] == "INA":
                raise HTTPException(status_code=409, detail=f"El concepto '{clean_id}' ya está inactivo.")
            cur.execute(sql.SQL("UPDATE {} SET {} = 'INA' WHERE {} = %s").format(
                sql.Identifier(table), sql.Identifier(status_col), sql.Identifier(id_col)), (clean_id,))
            return {"id": clean_id, "mensaje": f"Concepto '{clean_id}' desactivado correctamente."}
