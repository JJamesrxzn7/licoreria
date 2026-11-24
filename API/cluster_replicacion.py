"""
Replicación en anillo, continuidad (DR), detalle por operación de agente y medición de paralelismo real.

ANILLO DE REPLICACIÓN (cada sede guarda una copia de la anterior):
    QUITO (BD 1, MariaDB) ──► GUAYAQUIL (BD 4, MariaDB) ──► CUENCA (BD 6, PostgreSQL) ──► QUITO

Tipo: replicación LÓGICA, ASÍNCRONA e INCREMENTAL a nivel de aplicación (similar a un CDC):
  - Los motores son heterogéneos (MariaDB <-> PostgreSQL): la replicación nativa (binlog de MariaDB,
    streaming/logical replication de PostgreSQL) no puede cruzar de un motor a otro.
  - Marca de agua = MAX(id_origen) ya copiado en la tabla réplica del destino: si una corrida falla,
    la siguiente continúa desde ahí; PRIMARY KEY(id_origen) + INSERT IGNORE / ON CONFLICT DO NOTHING
    la hacen idempotente aunque las 3 réplicas de la API la ejecuten a la vez.
  - Si el nodo primario cae, GET /api/replicacion/leer/{sede} sirve sus datos desde la réplica (failover de lectura).
"""

import asyncio
import json
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from arquitectura_cluster import (
    AGENTES_IA,
    REPLICA_ID,
    _agent_num,
    _feed_agent_sync,
    _rows_as_dicts,
    connect_mariadb_with_fallback,
    connect_mongo_with_fallback,
    connect_postgres_with_fallback,
    get_cluster_6dbs_config,
    serialize_value,
)

router = APIRouter(tags=["Replicación en anillo, DR y paralelismo"])

ANILLO = [
    {"id": "QUITO->GUAYAQUIL", "origen": "QUITO", "destino": "GUAYAQUIL", "tabla": "replica_quito_log"},
    {"id": "GUAYAQUIL->CUENCA", "origen": "GUAYAQUIL", "destino": "CUENCA", "tabla": "replica_guayaquil_log"},
    {"id": "CUENCA->QUITO", "origen": "CUENCA", "destino": "QUITO", "tabla": "replica_cuenca_log"},
]
REPLICA_DE = {e["origen"]: e for e in ANILLO}
TABLA_ORIGEN = {"QUITO": "operaciones_agentes_ia", "GUAYAQUIL": "operaciones_agentes_ia", "CUENCA": "operaciones_agentes_cloud"}
LOTE_MAX = 2000
# Lo que se replica es el LOG DE CAMBIOS del ERP (LOG_AUDITORIA, ordenado por log_seq): cada INSERT/UPDATE/DELETE de
# cualquier tabla de la sede, con su usuario y sus valores antes/después. Las propias filas de réplica no se reenvían
# (si no, cada nodo devolvería al anillo lo que recibió y el log crecería sin fin).
FILTRO_LOG = "log_tablaafectada NOT LIKE 'REPLICA%%'"

DDL_MARIADB = (
    "CREATE TABLE IF NOT EXISTS {t} ("
    " log_seq_origen BIGINT PRIMARY KEY, sede_origen VARCHAR(20) NOT NULL,"
    " etiqueta_replica VARCHAR(60) NOT NULL DEFAULT '{etiqueta}', id_log_origen CHAR(15), id_usuario VARCHAR(16),"
    " fecha_origen DATETIME, tabla VARCHAR(50), accion VARCHAR(20), valor_anterior LONGTEXT, valor_nuevo LONGTEXT,"
    " replicado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, KEY idx_{t}_tabla (tabla))"
)
DDL_PG = (
    "CREATE TABLE IF NOT EXISTS {t} ("
    " log_seq_origen BIGINT PRIMARY KEY, sede_origen VARCHAR(20) NOT NULL,"
    " etiqueta_replica VARCHAR(60) NOT NULL DEFAULT '{etiqueta}', id_log_origen CHAR(15), id_usuario VARCHAR(16),"
    " fecha_origen TIMESTAMP, tabla VARCHAR(50), accion VARCHAR(20), valor_anterior TEXT, valor_nuevo TEXT,"
    " replicado_en TIMESTAMP NOT NULL DEFAULT now())"
)


# ------------------------------------------------------------------------------------------------
# Conexiones genéricas
# ------------------------------------------------------------------------------------------------

def _conectar(sede: str):
    cfg = get_cluster_6dbs_config()[sede]
    if cfg["engineType"] == "postgresql":
        conn, _ = connect_postgres_with_fallback(cfg)
        return conn, "pg"
    conn, _ = connect_mariadb_with_fallback(cfg)
    return conn, "my"


def _es_pg(sede: str) -> bool:
    return get_cluster_6dbs_config()[sede]["engineType"] == "postgresql"


def _query(sede: str, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn, _kind = _conectar(sede)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = _rows_as_dicts(cur) if cur.description else []
        cur.close()
        return rows
    finally:
        conn.close()


def _naive(dt: Any) -> Any:
    return dt.replace(tzinfo=None) if isinstance(dt, datetime) and dt.tzinfo else dt


def _json(texto: Any) -> dict[str, Any]:
    """Valores del log como dict con llaves en minúsculas (MariaDB guarda id_Factura, PostgreSQL id_factura)."""
    try:
        d = json.loads(texto) if texto else {}
        return {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _documento_del_cambio(valor_nuevo: Any, valor_anterior: Any) -> str | None:
    """Primer valor del registro cambiado (su llave primaria en el ERP), para mostrar QUÉ documento cambió."""
    d = _json(valor_nuevo) or _json(valor_anterior)
    for v in d.values():
        if v not in (None, ""):
            return str(v).strip()[:40]
    return None


# ------------------------------------------------------------------------------------------------
# Replicación (log shipping del LOG_AUDITORIA de cada ERP)
# ------------------------------------------------------------------------------------------------

ETIQUETA_REPLICA = {
    "QUITO": "RÉPLICA de Quito (BD 1)",
    "GUAYAQUIL": "RÉPLICA de Guayaquil (BD 4)",
    "CUENCA": "RÉPLICA de Cuenca (BD 6)",
}
_TABLAS_LISTAS: set[str] = set()


def _asegurar_tabla_replica(enlace: dict) -> None:
    """Crea en el destino la tabla réplica del log del origen, con su etiqueta «RÉPLICA de <sede>» por defecto."""
    if enlace["id"] in _TABLAS_LISTAS:
        return
    conn, kind = _conectar(enlace["destino"])
    try:
        cur = conn.cursor()
        cur.execute((DDL_PG if kind == "pg" else DDL_MARIADB).format(t=enlace["tabla"], etiqueta=ETIQUETA_REPLICA[enlace["origen"]]))
        if kind == "pg":
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{enlace['tabla']}_tabla ON {enlace['tabla']} (tabla)")
        cur.close()
        _TABLAS_LISTAS.add(enlace["id"])
    finally:
        conn.close()


def _auditar_corrida(enlace: dict, cur, kind: str, desde: int, hasta: int, copiadas: int) -> None:
    """La replicación también queda en el LOG_AUDITORIA de la BD que recibe la copia (hecha por el usuario dba)."""
    datos = json.dumps({"enlace": enlace["id"], "origen": enlace["origen"], "log_seq_desde": desde, "log_seq_hasta": hasta,
                        "filas_copiadas": copiadas, "replica_api": REPLICA_ID}, ensure_ascii=False)
    id_log = uuid4().hex[:15].upper()
    tabla = enlace["tabla"].upper()
    if kind == "pg":
        cur.execute("INSERT INTO log_auditoria (id_log, id_usuario, log_fechahora, log_tablaafectada, log_accion, log_valornuevo) "
                    "SELECT %s, (SELECT id_usuario FROM usuarios WHERE usr_username = 'dba'), now(), %s, 'INSERT', %s",
                    (id_log, tabla, datos))
    else:
        cur.execute("INSERT INTO log_auditoria (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_ValorNuevo) "
                    "SELECT %s, (SELECT id_Usuario FROM usuarios WHERE usr_Username = 'dba'), NOW(), %s, 'INSERT', %s",
                    (id_log, tabla, datos))


def sincronizar_enlace(enlace: dict) -> dict[str, Any]:
    """Copia al destino los cambios del log del origen con log_seq mayor a la marca de agua del destino."""
    t0 = time.perf_counter()
    res = {"enlace": enlace["id"], "origen": enlace["origen"], "destino": enlace["destino"], "tablaReplica": enlace["tabla"]}
    try:
        _asegurar_tabla_replica(enlace)
        marca = int(_query(enlace["destino"], f"SELECT COALESCE(MAX(log_seq_origen), 0) AS m FROM {enlace['tabla']}")[0]["m"] or 0)
    except Exception as exc:
        return {**res, "ok": False, "copiadas": 0, "error": f"Destino {enlace['destino']} no disponible: {str(exc)[:160]}",
                "ms": round((time.perf_counter() - t0) * 1000, 1)}

    try:
        filas = [tuple(f.values()) for f in _query(
            enlace["origen"],
            f"SELECT log_seq, id_log, id_usuario, log_fechahora, log_tablaafectada, log_accion, log_valoranterior, log_valornuevo "
            f"FROM log_auditoria WHERE log_seq > %s AND {FILTRO_LOG} ORDER BY log_seq LIMIT {LOTE_MAX}", (marca,))]
    except Exception as exc:
        return {**res, "ok": False, "copiadas": 0, "marcaDeAgua": marca,
                "error": f"Origen {enlace['origen']} no disponible: {str(exc)[:160]}",
                "ms": round((time.perf_counter() - t0) * 1000, 1)}

    copiadas = 0
    if filas:
        conn_d, kind_d = _conectar(enlace["destino"])
        try:
            cur_d = conn_d.cursor()
            sql = (f"INSERT INTO {enlace['tabla']} (log_seq_origen, sede_origen, id_log_origen, id_usuario, fecha_origen, tabla, accion, "
                   f"valor_anterior, valor_nuevo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
            sql = sql + " ON CONFLICT (log_seq_origen) DO NOTHING" if kind_d == "pg" else sql.replace("INSERT INTO", "INSERT IGNORE INTO", 1)
            datos = [(int(f[0]), enlace["origen"], (f[1] or "").strip(), (f[2] or "").strip() or None, _naive(f[3]), f[4], f[5], f[6], f[7])
                     for f in filas]
            cur_d.executemany(sql, datos)
            copiadas = len(datos)
            _auditar_corrida(enlace, cur_d, kind_d, int(filas[0][0]), int(filas[-1][0]), copiadas)
            cur_d.close()
        finally:
            conn_d.close()
    return {**res, "ok": True, "copiadas": copiadas, "marcaDeAgua": marca,
            "nuevaMarca": int(filas[-1][0]) if filas else marca, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def estado_enlace(enlace: dict) -> dict[str, Any]:
    """Cambios en el log del origen, cambios ya replicados y retraso (pendientes y antigüedad del más viejo sin copiar = RPO)."""
    res = {"enlace": enlace["id"], "origen": enlace["origen"], "destino": enlace["destino"], "tablaReplica": enlace["tabla"]}
    origen_ok = destino_ok = True
    try:
        o = _query(enlace["origen"], f"SELECT COUNT(*) AS n, COALESCE(MAX(log_seq), 0) AS maxid FROM log_auditoria WHERE {FILTRO_LOG}")[0]
    except Exception as exc:
        origen_ok, o = False, {"n": None, "maxid": None}
        res["errorOrigen"] = str(exc)[:160]
    try:
        _asegurar_tabla_replica(enlace)
        hace = ("EXTRACT(EPOCH FROM (now() - MAX(replicado_en)))::int" if _es_pg(enlace["destino"])
                else "TIMESTAMPDIFF(SECOND, MAX(replicado_en), NOW())")
        d = _query(enlace["destino"], f"SELECT COUNT(*) AS n, COALESCE(MAX(log_seq_origen), 0) AS marca, {hace} AS hace FROM {enlace['tabla']}")[0]
    except Exception as exc:
        destino_ok, d = False, {"n": None, "marca": None, "hace": None}
        res["errorDestino"] = str(exc)[:160]

    pendientes = rpo = None
    if origen_ok and destino_ok:
        edad = ("EXTRACT(EPOCH FROM (now() - MIN(log_fechahora)))::int" if _es_pg(enlace["origen"])
                else "TIMESTAMPDIFF(SECOND, MIN(log_fechahora), NOW())")
        try:
            p = _query(enlace["origen"], f"SELECT COUNT(*) AS n, {edad} AS rpo FROM log_auditoria "
                                         f"WHERE log_seq > %s AND {FILTRO_LOG}", (int(d["marca"] or 0),))[0]
            pendientes, rpo = int(p["n"] or 0), (int(p["rpo"]) if p["rpo"] is not None else 0)
        except Exception:
            pass
    estado = "SINCRONIZADO" if pendientes == 0 else "CON RETRASO" if pendientes else "SIN DATOS"
    if not origen_ok and destino_ok:
        estado = "ORIGEN CAÍDO · RÉPLICA DISPONIBLE"
    elif not destino_ok:
        estado = "DESTINO CAÍDO"
    return {
        **res,
        "origenOnline": origen_ok, "destinoOnline": destino_ok,
        "filasOrigen": o["n"], "maxIdOrigen": o["maxid"],
        "filasReplica": d["n"], "marcaDeAgua": d["marca"],
        "segundosDesdeUltimaCopia": d["hace"],
        "pendientes": pendientes, "rpoSegundos": rpo, "estado": estado,
    }


@router.post("/api/replicacion/sincronizar")
async def replicacion_sincronizar():
    """Ejecuta una ronda de replicación en los 3 enlaces del anillo (en paralelo)."""
    t0 = time.perf_counter()
    resultados = await asyncio.gather(*(asyncio.to_thread(sincronizar_enlace, e) for e in ANILLO))
    return {"timestamp": datetime.now().isoformat(), "apiReplica": REPLICA_ID,
            "ms": round((time.perf_counter() - t0) * 1000, 1), "enlaces": resultados}


@router.get("/api/replicacion/estado")
async def replicacion_estado():
    estados = await asyncio.gather(*(asyncio.to_thread(estado_enlace, e) for e in ANILLO))
    return {"timestamp": datetime.now().isoformat(), "apiReplica": REPLICA_ID, "enlaces": estados}


def _facturas_desde_replica(enlace: dict, limit: int) -> list[dict[str, Any]]:
    """Reconstruye el estado ACTUAL de las facturas de la sede caída aplicando su log replicado (el último cambio gana)."""
    filas = _query(enlace["destino"], f"SELECT log_seq_origen, etiqueta_replica, accion, valor_anterior, valor_nuevo, fecha_origen "
                                      f"FROM {enlace['tabla']} WHERE tabla = 'FACTURAS' ORDER BY log_seq_origen DESC LIMIT 3000")
    vistas: dict[str, dict[str, Any]] = {}
    for f in filas:  # de la más nueva a la más vieja
        nuevo, viejo = _json(f["valor_nuevo"]), _json(f["valor_anterior"])
        fac = str((nuevo or viejo).get("id_factura") or "").strip()
        if not fac or fac in vistas:
            continue
        vistas[fac] = {
            "etiqueta_replica": f["etiqueta_replica"], "id_factura": fac,
            "fac_fecha": nuevo.get("fac_fecha"), "fac_total": nuevo.get("fac_total"),
            "estado_fac": "ELIMINADA" if f["accion"] == "DELETE" else nuevo.get("estado_fac"),
            "ultimo_cambio": f"{f['accion']} · log_seq {f['log_seq_origen']}",
        }
    return sorted(vistas.values(), key=lambda x: str(x["fac_fecha"] or ""), reverse=True)[:limit]


@router.get("/api/replicacion/leer/{sede}")
def replicacion_leer(
    sede: str,
    limit: int = Query(default=8, ge=1, le=50),
    simular_caida: bool = Query(default=False, alias="simularCaida",
                                description="Ignora la primaria a propósito para mostrar el failover sin apagar la máquina"),
):
    """Lee las últimas FACTURAS de una sede; si su ERP no responde, las reconstruye desde su log replicado en otra sede."""
    sede = sede.strip().upper()
    if sede not in REPLICA_DE:
        raise HTTPException(status_code=404, detail="Sede no válida (QUITO, GUAYAQUIL o CUENCA).")
    enlace = REPLICA_DE[sede]
    t0 = time.perf_counter()
    error_primaria = None
    if not simular_caida:
        try:
            filas = _query(sede, "SELECT id_factura, fac_fecha, fac_total, estado_fac FROM facturas "
                                 "ORDER BY fac_fecha DESC LIMIT %s", (limit,))
            return {"sede": sede, "servidoDesde": "PRIMARIA", "nodo": sede, "tabla": "facturas (ERP)",
                    "ms": round((time.perf_counter() - t0) * 1000, 1), "filas": filas}
        except Exception as exc:
            error_primaria = str(exc)[:200]
    else:
        error_primaria = "Caída simulada a pedido (la primaria no se consultó)."
    try:
        _asegurar_tabla_replica(enlace)
        filas = _facturas_desde_replica(enlace, limit)
        return {"sede": sede, "servidoDesde": "REPLICA", "nodo": enlace["destino"],
                "tabla": f"{enlace['tabla']} (log replicado → facturas reconstruidas)",
                "errorPrimaria": error_primaria, "ms": round((time.perf_counter() - t0) * 1000, 1), "filas": filas}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Primaria y réplica de {sede} sin respuesta: {error_primaria} / {exc}") from exc


@router.get("/api/replicacion/comparar/{origen}")
async def replicacion_comparar(origen: str, limit: int = Query(default=10, ge=1, le=50)):
    """
    Lado a lado: últimos cambios del LOG del ERP de ORIGEN y lo que ya llegó a la tabla RÉPLICA del siguiente nodo.
    Cada cambio del origen dice si ya está copiado; cada fila de la réplica trae su etiqueta y cuánto tardó en llegar.
    """
    origen = origen.strip().upper()
    if origen not in REPLICA_DE:
        raise HTTPException(status_code=404, detail="Origen no válido (QUITO, GUAYAQUIL o CUENCA).")
    enlace = REPLICA_DE[origen]
    cfg_all = get_cluster_6dbs_config()

    def leer_origen():
        t = time.perf_counter()
        filas = _query(origen, f"SELECT log_seq, log_fechahora, id_usuario, log_tablaafectada, log_accion, log_valoranterior, "
                               f"log_valornuevo FROM log_auditoria WHERE {FILTRO_LOG} ORDER BY log_seq DESC LIMIT %s", (limit,))
        salida = [{"id_op": f["log_seq"], "fecha_hora": f["log_fechahora"], "usuario_rbac": (f["id_usuario"] or "").strip(),
                   "modulo": f"{f['log_accion']} {f['log_tablaafectada']}",
                   "documento": _documento_del_cambio(f["log_valornuevo"], f["log_valoranterior"])} for f in filas]
        return salida, round((time.perf_counter() - t) * 1000, 1)

    def leer_replica():
        t = time.perf_counter()
        _asegurar_tabla_replica(enlace)
        retraso = ("EXTRACT(EPOCH FROM (replicado_en - fecha_origen))::int" if _es_pg(enlace["destino"])
                   else "TIMESTAMPDIFF(SECOND, fecha_origen, replicado_en)")
        filas = _query(enlace["destino"], f"SELECT etiqueta_replica, log_seq_origen, fecha_origen, replicado_en, {retraso} AS segundos_en_llegar, "
                                          f"id_usuario, tabla, accion, valor_anterior, valor_nuevo FROM {enlace['tabla']} "
                                          f"ORDER BY log_seq_origen DESC LIMIT %s", (limit,))
        salida = [{"etiqueta_replica": f["etiqueta_replica"], "id_origen": f["log_seq_origen"], "fecha_origen": f["fecha_origen"],
                   "replicado_en": f["replicado_en"], "segundos_en_llegar": f["segundos_en_llegar"],
                   "usuario_rbac": (f["id_usuario"] or "").strip(), "modulo": f"{f['accion']} {f['tabla']}",
                   "documento": _documento_del_cambio(f["valor_nuevo"], f["valor_anterior"])} for f in filas]
        return salida, round((time.perf_counter() - t) * 1000, 1)

    (o, o_ms), (r, r_ms) = await asyncio.gather(asyncio.to_thread(leer_origen), asyncio.to_thread(leer_replica))
    marca = max((int(x["id_origen"]) for x in r), default=0)
    for fila in o:
        fila["estado_replica"] = "copiada" if int(fila["id_op"]) <= marca else "pendiente"
    cfg_o, cfg_d = cfg_all[origen], cfg_all[enlace["destino"]]
    return {
        "enlace": enlace["id"],
        "origen": {"sede": origen, "bd": cfg_o["bdId"], "maquina": cfg_o["machine"], "motor": cfg_o["engine"],
                   "tabla": "log_auditoria (ERP)", "ms": o_ms, "filas": o},
        "replica": {"sede": enlace["destino"], "bd": cfg_d["bdId"], "maquina": cfg_d["machine"], "motor": cfg_d["engine"],
                    "tabla": enlace["tabla"], "etiqueta": ETIQUETA_REPLICA[origen], "ms": r_ms, "filas": r},
        "pendientes": sum(1 for f in o if f["estado_replica"] == "pendiente"),
    }


# ------------------------------------------------------------------------------------------------
# Detalle de UNA operación de un agente (qué hizo exactamente y dónde quedó)
# ------------------------------------------------------------------------------------------------

APP_DOCS = {
    # documento del ERP -> (consulta cabecera, consulta detalle, ruta de la pantalla, módulo).
    # Sin comillas en los nombres: valen igual en el ERP MariaDB (Quito, Guayaquil) y en el PostgreSQL (Cuenca).
    "RECEPCIONES": (
        "SELECT TRIM(id_Recibo) AS recepcion, TRIM(id_Compra) AS orden_compra, rec_Descripcion AS descripcion, "
        "rec_FechaHora AS fecha, ESTADO_REC AS estado FROM RECEPCIONES WHERE id_Recibo = %s",
        "SELECT TRIM(D.id_Producto) AS producto, TRIM(P.pro_Descripcion) AS nombre, D.pxr_Cantidad AS solicitado, "
        "D.pxr_Qty_Recibida AS recibido, D.pxr_Motivo AS motivo, D.ESTADO_PxREC AS estado "
        "FROM PROxREC D LEFT JOIN PRODUCTOS P ON P.id_Producto = D.id_Producto WHERE D.id_Recibo = %s",
        "receptions", "Bodega · Recepciones",
    ),
    "ENTREGAS": (
        "SELECT TRIM(id_Entrega) AS entrega, TRIM(id_Factura) AS factura, ent_Descripcion AS descripcion, "
        "ent_FechaHora AS fecha, ESTADO_ENT AS estado FROM ENTREGAS WHERE id_Entrega = %s",
        "SELECT TRIM(D.id_Producto) AS producto, TRIM(P.pro_Descripcion) AS nombre, D.pxe_Cantidad AS solicitado, "
        "D.pxe_Qty_Entregada AS entregado, D.pxe_Motivo AS motivo, D.ESTADO_PxENT AS estado "
        "FROM PROxENT D LEFT JOIN PRODUCTOS P ON P.id_Producto = D.id_Producto WHERE D.id_Entrega = %s",
        "deliveries", "Bodega · Entregas",
    ),
}


def _auditoria_de_operacion(sede: str, patron: str) -> list[dict[str, Any]]:
    """Filas del LOG_AUDITORIA del ERP de la sede que mencionan el documento o la operación (quién, qué tabla, qué acción)."""
    try:
        return _query(sede, "SELECT log_seq, log_fechahora AS fecha_hora, id_usuario AS usuario, log_tablaafectada AS tabla, "
                            "log_accion AS accion, log_ip AS ip FROM log_auditoria "
                            "WHERE log_valornuevo LIKE %s OR log_valoranterior LIKE %s ORDER BY log_seq DESC LIMIT 25",
                      (f"%{patron}%", f"%{patron}%"))
    except Exception:
        return []


def _auditoria_bd_apoyo(sede: str, op_id: str) -> list[dict[str, Any]]:
    """BD 3 y BD 5 (no son ERP): la API deja su propia fila en log_auditoria con el id de la operación."""
    try:
        return _query(sede, "SELECT log_FechaHora AS fecha_hora, id_Usuario AS usuario, log_TablaAfectada AS tabla, "
                            "log_Accion AS accion, log_IP AS ip FROM log_auditoria WHERE log_ValorNuevo LIKE %s "
                            "ORDER BY log_FechaHora", (f'%"operacion_id": "{op_id}"%',))
    except Exception:
        return []


def _detalle_oltp(sede: str, agent_num: int, op_id: str) -> dict[str, Any]:
    tabla = TABLA_ORIGEN[sede]
    filas = _query(sede, f"SELECT * FROM {tabla} WHERE id_op = %s", (int(op_id),))
    if not filas:
        raise HTTPException(status_code=404, detail="Operación no encontrada.")
    op = filas[0]
    documento = None
    auditoria_doc: list[dict[str, Any]] = []
    tabla_ref = str(op.get("tabla_ref") or "").upper().removeprefix("APP:")
    doc_ref = op.get("documento_ref")
    if tabla_ref in APP_DOCS and doc_ref:
        sql_cab, sql_det, ruta, modulo = APP_DOCS[tabla_ref]
        try:
            cab = _query(sede, sql_cab, (doc_ref,))
            det = _query(sede, sql_det, (doc_ref,))
            auditoria_doc = _auditoria_de_operacion(sede, doc_ref)
            fila = dict(cab[0]) if cab else None
            if fila is not None:
                fila["productos"] = "\n".join(
                    " · ".join(f"{k}: {v}" for k, v in d.items() if v not in (None, "")) for d in det
                )
            documento = {"tabla": f"{tabla_ref} (ERP {sede.title()})", "id": doc_ref, "modulo": modulo, "fila": fila,
                         "consultaSql": sql_cab.replace("%s", f"'{doc_ref}'") + ";", "appRoute": ruta}
        except Exception as exc:
            documento = {"tabla": f"{tabla_ref} (ERP {sede.title()})", "id": doc_ref, "modulo": modulo,
                         "fila": {"error": f"No se pudo leer el ERP de {sede}: {str(exc)[:150]}"}, "consultaSql": None, "appRoute": ruta}
    # ¿Ya llegó al siguiente nodo del anillo? (se busca el documento en el log replicado)
    enlace = REPLICA_DE[sede]
    replicada = None
    if doc_ref:
        try:
            r = _query(enlace["destino"], f"SELECT MIN(replicado_en) AS replicado_en, COUNT(*) AS cambios FROM {enlace['tabla']} "
                                          f"WHERE valor_nuevo LIKE %s OR valor_anterior LIKE %s", (f"%{doc_ref}%", f"%{doc_ref}%"))
            presente = bool(r and r[0]["cambios"])
            replicada = {"nodo": enlace["destino"], "tabla": enlace["tabla"], "presente": presente,
                         "replicadoEn": r[0]["replicado_en"] if presente else None,
                         "cambiosReplicados": int(r[0]["cambios"] or 0) if r else 0}
        except Exception as exc:
            replicada = {"nodo": enlace["destino"], "tabla": enlace["tabla"], "presente": None, "error": str(exc)[:120]}
    return {
        "operacion": op,
        "documento": documento,
        # bd = cómo quedó auditado el documento en el ERP; app se mantiene por compatibilidad con la GUI
        "auditoria": {"bd": auditoria_doc, "app": []},
        "replica": replicada,
        "consultaSqlOperacion": f"SELECT * FROM {tabla} WHERE id_op = {int(op_id)};",
        "sinDocumento": None if documento else _motivo_sin_documento(op),
    }


def _motivo_sin_documento(op: dict[str, Any]) -> str:
    if "FALLÓ" in str(op.get("operacion") or ""):
        return "La transacción no se pudo completar en el ERP; la bitácora deja constancia del intento y del error."
    return ("Operación anterior a que los agentes trabajaran sobre el ERP de su sede "
            "(las nuevas siempre enlazan el documento que crearon o confirmaron).")


@router.get("/api/agentes/{agente_id}/operacion/{op_id}")
def agente_operacion_detalle(agente_id: str, op_id: str):
    num = _agent_num(agente_id)
    ag = AGENTES_IA[num]
    cfg = get_cluster_6dbs_config()[ag["sede"]]
    base = {"agentId": f"agente-{num}", "codigo": ag["codigo"], "agente": ag["nombre"], "bdId": cfg["bdId"],
            "nodeId": cfg["id"], "baseDatos": cfg["database"], "motor": cfg["engine"], "puerto": cfg["port"]}

    if num in (1, 4):
        return {**base, **_detalle_oltp(ag["sede"], num, op_id)}
    if num == 6:
        return {**base, **_detalle_oltp("CUENCA", num, op_id)}
    if num == 2:
        cli, _ = connect_mongo_with_fallback(cfg)
        db = cli[cfg["database"]]
        ev = db["eventos_agentes"].find_one({"evento_id": op_id})
        log = db["logs_auditoria"].find_one({"evento_id": op_id})
        cli.close()
        if not ev:
            raise HTTPException(status_code=404, detail="Documento no encontrado.")
        limpio = {k: serialize_value(v) for k, v in ev.items() if k != "_id"}
        return {**base, "operacion": limpio, "documento": {
            "tabla": "eventos_agentes (colección MongoDB)", "id": op_id, "modulo": limpio.get("modulo"),
            "fila": {"documento_json": json.dumps(limpio, ensure_ascii=False, default=str),
                     "copia_en_logs_auditoria": bool(log)},
            "consultaSql": "MONGO_COLLECTION:eventos_agentes",
        }, "replica": None, "consultaSqlOperacion": "MONGO_COLLECTION:eventos_agentes"}
    if num == 3:
        filas = _query("QUITO_PARALELA", "SELECT *, CONCAT('p', particion_hash) AS particion FROM historico_transacciones WHERE id = %s", (int(op_id),))
        if not filas:
            raise HTTPException(status_code=404, detail="Registro no encontrado.")
        sql = f"SELECT * FROM historico_transacciones WHERE id = {int(op_id)};"
        return {**base, "operacion": filas[0], "documento": {
            "tabla": f"historico_transacciones · partición {filas[0]['particion']}", "id": op_id, "modulo": filas[0].get("modulo"),
            "fila": filas[0], "consultaSql": sql,
        }, "auditoria": {"bd": _auditoria_bd_apoyo("QUITO_PARALELA", op_id), "app": []},
            "replica": None, "consultaSqlOperacion": sql}
    # num == 5: una corrida del ETL y los hechos que cargó
    if op_id.upper().startswith("ETL-"):
        corrida = _query("GUAYAQUIL_DWH", "SELECT * FROM etl_corridas WHERE lote = %s ORDER BY id DESC LIMIT 1", (op_id,))
        if not corrida:  # lotes anteriores a la bitácora de corridas
            corrida = [{"id": None, "lote": op_id, "fecha_corrida": None, "hechos_cargados": None, "detalle": "Lote anterior a etl_corridas"}]
    else:
        corrida = _query("GUAYAQUIL_DWH", "SELECT * FROM etl_corridas WHERE id = %s", (int(op_id),))
    if not corrida:
        raise HTTPException(status_code=404, detail="Corrida ETL no encontrada.")
    lote = corrida[0]["lote"]
    hechos = _query("GUAYAQUIL_DWH", "SELECT id_fact, id_sede, id_producto, cantidad_botellas, total_venta_usd, usuario_rbac "
                                     "FROM fact_ventas WHERE etl_lote = %s ORDER BY id_fact LIMIT 25", (lote,))
    sql = f"SELECT * FROM fact_ventas WHERE etl_lote = '{lote}';"
    return {**base, "operacion": corrida[0], "documento": {
        "tabla": "fact_ventas (esquema estrella)", "id": lote, "modulo": "Ventas (análisis OLAP)",
        "fila": {"hechos_cargados": len(hechos), "hechos": json.dumps(hechos, ensure_ascii=False, default=str)},
        "consultaSql": sql,
    }, "auditoria": {"bd": _auditoria_bd_apoyo("GUAYAQUIL_DWH", str(lote)), "app": []},
        "replica": None, "consultaSqlOperacion": "SELECT * FROM etl_corridas ORDER BY id DESC LIMIT 10;"}


# ------------------------------------------------------------------------------------------------
# Paralelismo: solo mediciones reales
# ------------------------------------------------------------------------------------------------

def _medir_cpu_mariadb(n: int, iteraciones: int) -> dict[str, Any]:
    """N consultas que consumen CPU en el motor (BENCHMARK), primero en serie y luego en N conexiones a la vez."""
    cfg = get_cluster_6dbs_config()["GUAYAQUIL"]
    sql = f"SELECT BENCHMARK({iteraciones}, SHA2('la-cava', 256))"

    def una():
        conn, _ = connect_mariadb_with_fallback(cfg)
        cur = conn.cursor()
        t = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        ms = (time.perf_counter() - t) * 1000
        cur.close()
        conn.close()
        return ms

    t0 = time.perf_counter()
    serie = [una() for _ in range(n)]
    t_serie = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as ex:
        paralelo = list(ex.map(lambda _: una(), range(n)))
    t_par = (time.perf_counter() - t0) * 1000
    return {"consultas": n, "sql": sql, "serieMs": round(t_serie, 1), "paraleloMs": round(t_par, 1),
            "speedup": round(t_serie / t_par, 2) if t_par else None,
            "msPorConsultaSerie": round(sum(serie) / n, 1), "msPorConsultaParalelo": round(sum(paralelo) / n, 1)}


@router.get("/api/paralelismo/medir")
async def paralelismo_medir(consultas: int = Query(default=8, ge=2, le=16), iteraciones: int = Query(default=1500000, ge=100000, le=5000000)):
    """
    Mide (no simula) tres cosas:
      A) Paralelismo inter-nodo: leer las 6 BDs una tras otra vs. las 6 a la vez.
      B) Paralelismo inter-consulta en MariaDB (BD 4, Laptop): N consultas de CPU en serie vs. N conexiones simultáneas.
      C) Paralelismo intra-consulta: qué permite cada motor (MariaDB no lo tiene; PostgreSQL sí, con condiciones).
    """
    # A) inter-nodo
    t0 = time.perf_counter()
    for n in AGENTES_IA:
        await asyncio.to_thread(_feed_agent_sync, n, 1)
    a_serie = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    await asyncio.gather(*(asyncio.to_thread(_feed_agent_sync, n, 1) for n in AGENTES_IA))
    a_par = (time.perf_counter() - t0) * 1000

    # B) inter-consulta (CPU) en MariaDB local
    try:
        b = await asyncio.to_thread(_medir_cpu_mariadb, consultas, iteraciones)
    except Exception as exc:
        b = {"error": str(exc)[:200]}

    # C) intra-consulta
    c_mariadb: dict[str, Any] = {}
    try:
        v = _query("GUAYAQUIL", "SELECT @@version AS version, @@thread_handling AS manejo_hilos")[0]
        plan = _query("QUITO_PARALELA", "EXPLAIN PARTITIONS SELECT * FROM historico_transacciones WHERE id = 42")
        c_mariadb = {
            "version": v["version"], "manejoHilos": v["manejo_hilos"],
            "explicacionPoda": plan[0] if plan else None,
            "conclusion": "MariaDB ejecuta cada consulta en un solo hilo: no tiene paralelismo intra-consulta (no hay 'parallel query'). "
                          "Las particiones HASH de BD 3 no reparten una consulta entre núcleos: aceleran por PODA de particiones "
                          "(una búsqueda por id lee 1 de 4 particiones, ver 'partitions' en el EXPLAIN).",
        }
    except Exception as exc:
        c_mariadb = {"error": str(exc)[:200]}
    c_pg: dict[str, Any] = {}
    try:
        s = _query("CUENCA", "SELECT current_setting('max_parallel_workers_per_gather') AS por_consulta, "
                             "current_setting('max_parallel_workers') AS total, "
                             "current_setting('min_parallel_table_scan_size') AS tam_minimo, "
                             "pg_size_pretty(pg_relation_size('operaciones_agentes_cloud')) AS tam_tabla")[0]
        plan = _query("CUENCA", "EXPLAIN SELECT modulo, COUNT(*) FROM operaciones_agentes_cloud GROUP BY modulo")
        texto_plan = "\n".join(str(list(r.values())[0]) for r in plan)
        usa = "Gather" in texto_plan
        c_pg = {
            "trabajadoresPorConsulta": s["por_consulta"], "trabajadoresTotales": s["total"],
            "tamanoMinimoTabla": s["tam_minimo"], "tamanoTabla": s["tam_tabla"], "plan": texto_plan, "usaParalelismo": usa,
            "conclusion": ("PostgreSQL SÍ paraleliza esta consulta (aparece Gather en el plan)." if usa else
                           f"PostgreSQL soporta paralelismo intra-consulta (hasta {s['por_consulta']} trabajadores por consulta), "
                           f"pero el planificador no lo usa aquí: la tabla mide {s['tam_tabla']}, menos que min_parallel_table_scan_size "
                           f"({s['tam_minimo']}). Arrancar trabajadores costaría más que leerla. No lo forzamos ni lo simulamos."),
        }
    except Exception as exc:
        c_pg = {"error": str(exc)[:200]}

    return {
        "timestamp": datetime.now().isoformat(),
        "hardware": {"maquina": "Laptop (nodo Guayaquil + API)", "nucleosLogicos": os.cpu_count(),
                     "procesador": platform.processor(), "sistema": platform.platform()},
        "interNodo": {"nodos": len(AGENTES_IA), "serieMs": round(a_serie, 1), "paraleloMs": round(a_par, 1),
                      "speedup": round(a_serie / a_par, 2) if a_par else None},
        "interConsultaMariaDB": b,
        "intraConsulta": {"mariadb": c_mariadb, "postgresql": c_pg},
    }
