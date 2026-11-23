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
    registrar_auditoria,
    serialize_value,
)
import mysql.connector

router = APIRouter(tags=["Replicación en anillo, DR y paralelismo"])

ANILLO = [
    {"id": "QUITO->GUAYAQUIL", "origen": "QUITO", "destino": "GUAYAQUIL", "tabla": "replica_quito_operaciones"},
    {"id": "GUAYAQUIL->CUENCA", "origen": "GUAYAQUIL", "destino": "CUENCA", "tabla": "replica_guayaquil_operaciones"},
    {"id": "CUENCA->QUITO", "origen": "CUENCA", "destino": "QUITO", "tabla": "replica_cuenca_operaciones"},
]
REPLICA_DE = {e["origen"]: e for e in ANILLO}
TABLA_ORIGEN = {"QUITO": "operaciones_agentes_ia", "GUAYAQUIL": "operaciones_agentes_ia", "CUENCA": "operaciones_agentes_cloud"}
LOTE_MAX = 500

DDL_MARIADB = (
    "CREATE TABLE IF NOT EXISTS {t} ("
    " id_origen BIGINT PRIMARY KEY, sede_origen VARCHAR(20) NOT NULL, agente_nombre VARCHAR(60),"
    " usuario_rbac VARCHAR(30), rol_rbac VARCHAR(30), modulo VARCHAR(30), operacion VARCHAR(255),"
    " monto_usd DECIMAL(12,2), fecha_origen DATETIME, replicado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)
DDL_PG = (
    "CREATE TABLE IF NOT EXISTS {t} ("
    " id_origen BIGINT PRIMARY KEY, sede_origen VARCHAR(20) NOT NULL, agente_nombre VARCHAR(60),"
    " usuario_rbac VARCHAR(30), rol_rbac VARCHAR(30), modulo VARCHAR(30), operacion VARCHAR(255),"
    " monto_usd NUMERIC(12,2), fecha_origen TIMESTAMP, replicado_en TIMESTAMP NOT NULL DEFAULT now())"
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


# ------------------------------------------------------------------------------------------------
# Replicación
# ------------------------------------------------------------------------------------------------

def _asegurar_tabla_replica(enlace: dict) -> None:
    conn, kind = _conectar(enlace["destino"])
    try:
        cur = conn.cursor()
        cur.execute((DDL_PG if kind == "pg" else DDL_MARIADB).format(t=enlace["tabla"]))
        if kind == "pg":
            conn.commit() if not conn.autocommit else None
        cur.close()
    finally:
        conn.close()


def sincronizar_enlace(enlace: dict) -> dict[str, Any]:
    """Copia al destino las operaciones del origen con id mayor a la marca de agua del destino."""
    t0 = time.perf_counter()
    res = {"enlace": enlace["id"], "origen": enlace["origen"], "destino": enlace["destino"], "tablaReplica": enlace["tabla"]}
    try:
        _asegurar_tabla_replica(enlace)
        marca = _query(enlace["destino"], f"SELECT COALESCE(MAX(id_origen), 0) AS m FROM {enlace['tabla']}")[0]["m"]
        marca = int(marca or 0)
    except Exception as exc:
        return {**res, "ok": False, "copiadas": 0, "error": f"Destino {enlace['destino']} no disponible: {str(exc)[:160]}",
                "ms": round((time.perf_counter() - t0) * 1000, 1)}

    try:
        conn_o, kind_o = _conectar(enlace["origen"])
        cur_o = conn_o.cursor()
        cur_o.execute(
            f"SELECT id_op, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, fecha_hora "
            f"FROM {TABLA_ORIGEN[enlace['origen']]} WHERE id_op > %s ORDER BY id_op LIMIT {LOTE_MAX}",
            (marca,),
        )
        filas = cur_o.fetchall()
        cur_o.close()
        conn_o.close()
    except Exception as exc:
        return {**res, "ok": False, "copiadas": 0, "marcaDeAgua": marca,
                "error": f"Origen {enlace['origen']} no disponible: {str(exc)[:160]}",
                "ms": round((time.perf_counter() - t0) * 1000, 1)}

    copiadas = 0
    if filas:
        conn_d, kind_d = _conectar(enlace["destino"])
        try:
            cur_d = conn_d.cursor()
            sql = (
                f"INSERT INTO {enlace['tabla']} (id_origen, sede_origen, agente_nombre, usuario_rbac, rol_rbac, modulo, "
                f"operacion, monto_usd, fecha_origen) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            )
            sql += " ON CONFLICT (id_origen) DO NOTHING" if kind_d == "pg" else ""
            if kind_d != "pg":
                sql = sql.replace("INSERT INTO", "INSERT IGNORE INTO", 1)
            datos = [
                (int(f[0]), enlace["origen"], f[1], f[2], f[3], f[4], (f[5] or "")[:255], f[6], _naive(f[7]))
                for f in filas
            ]
            cur_d.executemany(sql, datos)
            copiadas = len(datos)
            if not getattr(conn_d, "autocommit", True):
                conn_d.commit()
            cur_d.close()
        finally:
            conn_d.close()
    if copiadas:
        # La copia queda auditada en la BD que la recibe
        registrar_auditoria(enlace["destino"], "SYS-REPLICA", [{
            "tabla": enlace["tabla"], "accion": "INSERT replicación",
            "id": f"id_origen {marca + 1}..{int(filas[-1][0])}",
        }], {"enlace": enlace["id"], "origen": enlace["origen"], "filas_copiadas": copiadas, "replica_api": REPLICA_ID}, "")
    return {**res, "ok": True, "copiadas": copiadas, "marcaDeAgua": marca,
            "nuevaMarca": int(filas[-1][0]) if filas else marca, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def estado_enlace(enlace: dict) -> dict[str, Any]:
    """Filas en el origen, filas replicadas y retraso (pendientes y antigüedad de la más vieja sin copiar = RPO actual)."""
    res = {"enlace": enlace["id"], "origen": enlace["origen"], "destino": enlace["destino"], "tablaReplica": enlace["tabla"]}
    origen_ok = destino_ok = True
    try:
        o = _query(enlace["origen"], f"SELECT COUNT(*) AS n, COALESCE(MAX(id_op), 0) AS maxid FROM {TABLA_ORIGEN[enlace['origen']]}")[0]
    except Exception as exc:
        origen_ok, o = False, {"n": None, "maxid": None}
        res["errorOrigen"] = str(exc)[:160]
    try:
        _asegurar_tabla_replica(enlace)
        if get_cluster_6dbs_config()[enlace["destino"]]["engineType"] == "postgresql":
            d = _query(enlace["destino"], f"SELECT COUNT(*) AS n, COALESCE(MAX(id_origen), 0) AS marca, "
                                          f"EXTRACT(EPOCH FROM (now() - MAX(replicado_en)))::int AS hace FROM {enlace['tabla']}")[0]
        else:
            d = _query(enlace["destino"], f"SELECT COUNT(*) AS n, COALESCE(MAX(id_origen), 0) AS marca, "
                                          f"TIMESTAMPDIFF(SECOND, MAX(replicado_en), NOW()) AS hace FROM {enlace['tabla']}")[0]
    except Exception as exc:
        destino_ok, d = False, {"n": None, "marca": None, "hace": None}
        res["errorDestino"] = str(exc)[:160]

    pendientes = rpo = None
    if origen_ok and destino_ok:
        marca = int(d["marca"] or 0)
        try:
            if get_cluster_6dbs_config()[enlace["origen"]]["engineType"] == "postgresql":
                p = _query(enlace["origen"], f"SELECT COUNT(*) AS n, EXTRACT(EPOCH FROM (now() - MIN(fecha_hora)))::int AS rpo "
                                             f"FROM {TABLA_ORIGEN[enlace['origen']]} WHERE id_op > %s", (marca,))[0]
            else:
                p = _query(enlace["origen"], f"SELECT COUNT(*) AS n, TIMESTAMPDIFF(SECOND, MIN(fecha_hora), NOW()) AS rpo "
                                             f"FROM {TABLA_ORIGEN[enlace['origen']]} WHERE id_op > %s", (marca,))[0]
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


@router.get("/api/replicacion/leer/{sede}")
def replicacion_leer(
    sede: str,
    limit: int = Query(default=8, ge=1, le=50),
    simular_caida: bool = Query(default=False, alias="simularCaida",
                                description="Ignora la primaria a propósito para mostrar el failover sin apagar la máquina"),
):
    """Lee las últimas operaciones de una sede; si su BD primaria no responde, las sirve desde su réplica."""
    sede = sede.strip().upper()
    if sede not in REPLICA_DE:
        raise HTTPException(status_code=404, detail="Sede no válida (QUITO, GUAYAQUIL o CUENCA).")
    enlace = REPLICA_DE[sede]
    t0 = time.perf_counter()
    error_primaria = None
    if not simular_caida:
        try:
            filas = _query(sede, f"SELECT id_op, fecha_hora, usuario_rbac, modulo, operacion, monto_usd "
                                 f"FROM {TABLA_ORIGEN[sede]} ORDER BY id_op DESC LIMIT %s", (limit,))
            return {"sede": sede, "servidoDesde": "PRIMARIA", "nodo": sede, "tabla": TABLA_ORIGEN[sede],
                    "ms": round((time.perf_counter() - t0) * 1000, 1), "filas": filas}
        except Exception as exc:
            error_primaria = str(exc)[:200]
    else:
        error_primaria = "Caída simulada a pedido (la primaria no se consultó)."
    try:
        filas = _query(enlace["destino"], f"SELECT id_origen AS id_op, fecha_origen AS fecha_hora, usuario_rbac, modulo, "
                                          f"operacion, monto_usd, replicado_en FROM {enlace['tabla']} "
                                          f"ORDER BY id_origen DESC LIMIT %s", (limit,))
        return {"sede": sede, "servidoDesde": "REPLICA", "nodo": enlace["destino"], "tabla": enlace["tabla"],
                "errorPrimaria": error_primaria, "ms": round((time.perf_counter() - t0) * 1000, 1), "filas": filas}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Primaria y réplica de {sede} sin respuesta: {error_primaria} / {exc}") from exc


# ------------------------------------------------------------------------------------------------
# Detalle de UNA operación de un agente (qué hizo exactamente y dónde quedó)
# ------------------------------------------------------------------------------------------------

DOC_KEYS = {
    "QUITO": {"facturas": "numero_factura", "compras": "numero_orden", "asientos": "codigo_asiento", "productos": "id_producto"},
    "GUAYAQUIL": {"facturas": "id_Factura", "compras": "id_Compra", "asientos": "id_Asiento", "productos": "id_Producto"},
    "CUENCA": {"frag_austral_facturas": "id_factura"},
}
MODULO_DE_TABLA = {"facturas": "Ventas", "frag_austral_facturas": "Ventas", "compras": "Compras",
                   "asientos": "Contabilidad", "productos": "Inventarios"}


APP_DOCS = {
    # tabla en la app principal -> (consulta cabecera, consulta detalle, ruta de la pantalla, módulo)
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


def _app_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Consulta la base principal de la app (la que leen las pantallas de negocio)."""
    conn = mysql.connector.connect(
        host=os.getenv("MARIADB_HOST", "localhost"), port=int(os.getenv("MARIADB_PORT", "3307")),
        user=os.getenv("MARIADB_USER", "root"), password=os.getenv("MARIADB_PASSWORD", ""),
        database=os.getenv("MARIADB_DATABASE", "licoreriadatabase"), use_pure=True, connection_timeout=4,
    )
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        filas = _rows_as_dicts(cur)
        cur.close()
        return filas
    finally:
        conn.close()


def _auditoria_de_operacion(sede: str, op_id: str) -> list[dict[str, Any]]:
    patron = f'%"operacion_id": "{op_id}"%'
    try:
        if get_cluster_6dbs_config()[sede]["engineType"] == "postgresql":
            return _query(sede, "SELECT fecha_hora, usuario_cloud AS usuario, evento, detalle FROM log_auditoria_cloud "
                                "WHERE detalle LIKE %s ORDER BY id_log", (patron,))
        return _query(sede, "SELECT log_FechaHora AS fecha_hora, id_Usuario AS usuario, log_TablaAfectada AS tabla, "
                            "log_Accion AS accion, log_IP AS ip FROM log_auditoria WHERE log_ValorNuevo LIKE %s "
                            "ORDER BY log_FechaHora", (patron,))
    except Exception:
        return []


def _detalle_oltp(sede: str, agent_num: int, op_id: str) -> dict[str, Any]:
    tabla = TABLA_ORIGEN[sede]
    filas = _query(sede, f"SELECT * FROM {tabla} WHERE id_op = %s", (int(op_id),))
    if not filas:
        raise HTTPException(status_code=404, detail="Operación no encontrada.")
    op = filas[0]
    documento = None
    auditoria_app: list[dict[str, Any]] = []
    tabla_ref, doc_ref = op.get("tabla_ref"), op.get("documento_ref")
    if tabla_ref and doc_ref and tabla_ref.startswith("app:") and tabla_ref[4:] in APP_DOCS:
        sql_cab, sql_det, ruta, modulo = APP_DOCS[tabla_ref[4:]]
        try:
            cab = _app_query(sql_cab, (doc_ref,))
            det = _app_query(sql_det, (doc_ref,))
            auditoria_app = _app_query(
                "SELECT log_FechaHora AS fecha_hora, id_Usuario AS usuario, log_TablaAfectada AS tabla, log_Accion AS accion "
                "FROM log_auditoria WHERE log_ValorNuevo LIKE %s OR log_ValorAnterior LIKE %s ORDER BY log_FechaHora DESC LIMIT 12",
                (f"%{doc_ref}%", f"%{doc_ref}%"),
            )
            fila = dict(cab[0]) if cab else None
            if fila is not None:
                fila["productos"] = "\n".join(
                    " · ".join(f"{k}: {v}" for k, v in d.items() if v not in (None, "")) for d in det
                )
            documento = {"tabla": f"{tabla_ref[4:]} (app principal)", "id": doc_ref, "modulo": modulo, "fila": fila,
                         "consultaSql": None, "appRoute": ruta}
        except Exception as exc:
            documento = {"tabla": f"{tabla_ref[4:]} (app principal)", "id": doc_ref, "modulo": modulo,
                         "fila": {"error": f"No se pudo leer la base de la app: {str(exc)[:150]}"}, "consultaSql": None, "appRoute": ruta}
    elif tabla_ref and doc_ref and tabla_ref in DOC_KEYS[sede]:
        clave = DOC_KEYS[sede][tabla_ref]
        fila = _query(sede, f"SELECT * FROM {tabla_ref} WHERE {clave} = %s", (doc_ref,))
        documento = {
            "tabla": tabla_ref, "clave": clave, "id": doc_ref, "modulo": MODULO_DE_TABLA.get(tabla_ref),
            "fila": fila[0] if fila else None,
            "consultaSql": f"SELECT * FROM {tabla_ref} WHERE {clave} = '{doc_ref}';",
        }
    # ¿Ya está replicada en el siguiente nodo del anillo?
    enlace = REPLICA_DE[sede]
    replicada = None
    try:
        r = _query(enlace["destino"], f"SELECT replicado_en FROM {enlace['tabla']} WHERE id_origen = %s", (int(op_id),))
        replicada = {"nodo": enlace["destino"], "tabla": enlace["tabla"], "presente": bool(r),
                     "replicadoEn": r[0]["replicado_en"] if r else None}
    except Exception as exc:
        replicada = {"nodo": enlace["destino"], "tabla": enlace["tabla"], "presente": None, "error": str(exc)[:120]}
    return {
        "operacion": op,
        "documento": documento,
        "auditoria": {"bd": _auditoria_de_operacion(sede, op_id), "app": auditoria_app},
        "replica": replicada,
        "consultaSqlOperacion": f"SELECT * FROM {tabla} WHERE id_op = {int(op_id)};",
        "sinDocumento": None if documento else _motivo_sin_documento(sede, str(op.get("modulo") or "")),
    }


def _motivo_sin_documento(sede: str, modulo: str) -> str:
    if sede == "CUENCA" and modulo != "VENTAS":
        return (f"En Cuenca solo las operaciones de VENTAS crean un documento (factura en frag_austral_facturas). "
                f"Esta es de {modulo}: queda registrada únicamente en la bitácora operaciones_agentes_cloud.")
    if modulo == "TALENTO_HUMANO":
        return "Talento Humano no crea un documento de negocio: la operación queda registrada solo en la bitácora del agente."
    return "Operación registrada antes de que se enlazara cada operación con su documento (las nuevas ya traen el enlace)."


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
        }, "auditoria": {"bd": _auditoria_de_operacion("QUITO_PARALELA", op_id), "app": []},
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
    }, "auditoria": {"bd": _auditoria_de_operacion("GUAYAQUIL_DWH", str(lote)), "app": []},
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
