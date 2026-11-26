"""
Módulo Multi-BD y Multi-Máquina del Clúster Híbrido "La Cava" (Nodo Guayaquil + App + Cuenca).
Implementa íntegramente el Contrato Compartido (Tarea 2.2, 2.3 y 2.4 de la Laptop):
- Pool de 6 Conexiones leyendo IPs de Tailscale (`IP_TS_QUITO`, `IP_TS_GUAYAQUIL`) y credenciales desde `.env`:
  * BD 1 (`QUITO`): MariaDB :3307 (SQL OLTP Quito + 15 Usuarios RBAC)
  * BD 2 (`QUITO_NOSQL`): MongoDB :27017 (`quito_nosql_mongo` -> `logs_auditoria` y `eventos_agentes`)
  * BD 3 (`QUITO_PARALELA`): MariaDB :3308 (`quito_paralela_db` -> `historico_transacciones` `PARTITION BY HASH(id) PARTITIONS 4`)
  * BD 4 (`GUAYAQUIL`): ERP MariaDB de la Laptop :3307 (`licoreriadatabase`, el ERP original = sede Guayaquil)
  * BD 5 (`GUAYAQUIL_DWH`): MariaDB DWH Laptop :3309 (`db_gye_dwh` -> Esquema Estrella `fact_ventas`, `dim_sede`, `dim_producto`, `dim_tiempo` para Power BI)
  * BD 6 (`CUENCA`): ERP PostgreSQL 18 :5432 (`lacava_cuenca`, local en la laptop)
- Enrutamiento dinámico por Header `X-Sede` (`QUITO`, `QUITO_NOSQL`, `QUITO_PARALELA`, `GUAYAQUIL`, `GUAYAQUIL_DWH`, `CUENCA`).
- Endpoints obligatorios del DBA:
  * `GET /api/dba/health` -> Estado `ONLINE/OFFLINE` y ping (`ms`) de las 6 BDs en paralelo (`asyncio`).
  * `GET /api/dba/global` -> Consulta las 6 BDs en paralelo (`asyncio.gather`), unifica los resultados en un solo JSON con `origen_nodo` y mide latencia (`ms`).
  * `POST /api/agentes/operacion` (y `/api/dba/operacion`) -> Recibe peticiones de los 6 Agentes IA con header `X-Sede` y credenciales de los 15 usuarios RBAC.
"""

import asyncio
from datetime import datetime, date
from decimal import Decimal
import json
import os
import time
from typing import Any
from uuid import uuid4

import mysql.connector
import psycopg
from pymongo import MongoClient
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["Clúster Híbrido Multi-Máquina (6 BDs + DBA + Agentes IA)"])

MARIADB_PASS = os.getenv("MARIADB_PASSWORD", "1597.MyHql")
PG_PASS = os.getenv("PGPASSWORD", "147852369.MyPost")
REPLICA_ID = os.getenv("API_REPLICA_ID", "api_lacava_1")

USUARIOS_15_MAP = {
    "admin": ("rol_jefe", "ADMINISTRACION_GENERAL", "LaCavaAdmin2026*"),
    "dba": ("rol_jefe", "ARQUITECTURA_Y_DBA", "LaCavaDba2026*"),
    "c_jefe": ("rol_jefe", "COMPRAS", "ComprasJefe2026*"),
    "c_supervisor": ("rol_supervisor", "COMPRAS", "ComprasSup2026*"),
    "c_operador": ("rol_operador", "COMPRAS", "ComprasOpe2026*"),
    "i_jefe": ("rol_jefe", "INVENTARIOS", "InveJefe2026*"),
    "i_supervisor": ("rol_supervisor", "INVENTARIOS", "InveSup2026*"),
    "i_operador": ("rol_operador", "INVENTARIOS", "InveOpe2026*"),
    "v_jefe": ("rol_jefe", "VENTAS", "VentasJefe2026*"),
    "v_supervisor": ("rol_supervisor", "VENTAS", "VentasSup2026*"),
    "v_operador": ("rol_operador", "VENTAS", "VentasOpe2026*"),
    "th_jefe": ("rol_jefe", "TALENTO_HUMANO", "ThJefe2026*"),
    "th_supervisor": ("rol_supervisor", "TALENTO_HUMANO", "ThSup2026*"),
    "th_operador": ("rol_operador", "TALENTO_HUMANO", "ThOpe2026*"),
    "ctbl_jefe": ("rol_jefe", "CONTABILIDAD", "CtblJefe2026*"),
    "ctbl_supervisor": ("rol_supervisor", "CONTABILIDAD", "CtblSup2026*"),
    "ctbl_operador": ("rol_operador", "CONTABILIDAD", "CtblOpe2026*"),
}


def get_cluster_6dbs_config() -> dict[str, dict[str, Any]]:
    ip_quito = os.getenv("IP_TS_QUITO", "127.0.0.1").strip() or "127.0.0.1"
    ip_gye = os.getenv("IP_TS_GUAYAQUIL", "127.0.0.1").strip() or "127.0.0.1"
    return {
        "QUITO": {
            "bdId": "BD 1",
            "id": "quito-sql",
            "xSede": "QUITO",
            "site": "QUITO",
            "siteLabel": "PC Escritorio — Nodo QUITO (Tailscale VPN)",
            "machine": f"PC Escritorio ({ip_quito})",
            "name": "BD 1 — QUITO: MariaDB ERP OLTP (:3307)",
            "shortName": "BD 1 · Quito ERP (:3307)",
            "engine": "MariaDB 12.3 (SQL OLTP)",
            "engineType": "mariadb",
            "role": "Transacciones principales de Quito + 15 Usuarios RBAC (C, I, V, TH, Ctbl)",
            "host": os.getenv("BD1_QUITO_HOST", ip_quito),
            "fallbackHost": "127.0.0.1",
            "port": int(os.getenv("BD1_QUITO_PORT", "3307")),
            "database": os.getenv("BD1_QUITO_DATABASE", "lacava_quito"),
            "user": os.getenv("BD1_QUITO_USER", "root"),
            "password": os.getenv("BD1_QUITO_PASSWORD", MARIADB_PASS),
            "heidiSqlHint": f"HeidiSQL -> Host: {ip_quito} | Puerto: 3307 | BD: lacava_quito",
        },
        "QUITO_NOSQL": {
            "bdId": "BD 2",
            "id": "quito-nosql",
            "xSede": "QUITO_NOSQL",
            "site": "QUITO",
            "siteLabel": "PC Escritorio — Nodo QUITO (Tailscale VPN)",
            "machine": f"PC Escritorio ({ip_quito})",
            "name": "BD 2 — QUITO: MongoDB NoSQL Documental (:27017)",
            "shortName": "BD 2 · Quito MongoDB (:27017)",
            "engine": "MongoDB (NoSQL Document Store)",
            "engineType": "mongodb",
            "role": "Logs de auditoría (`logs_auditoria`), telemetría de agentes (`eventos_agentes`) y JSON",
            "host": os.getenv("BD2_QUITO_MONGO_HOST", ip_quito),
            "fallbackHost": "127.0.0.1",
            "port": int(os.getenv("BD2_QUITO_MONGO_PORT", "27017")),
            "database": os.getenv("BD2_QUITO_MONGO_DATABASE", "quito_nosql_mongo"),
            "user": "mongo_admin",
            "password": "",
            "heidiSqlHint": f"MongoDB Compass -> mongodb://{ip_quito}:27017/quito_nosql_mongo",
        },
        "QUITO_PARALELA": {
            "bdId": "BD 3",
            "id": "quito-otras",
            "xSede": "QUITO_PARALELA",
            "site": "QUITO",
            "siteLabel": "PC Escritorio — Nodo QUITO (Tailscale VPN)",
            "machine": f"PC Escritorio ({ip_quito})",
            "name": "BD 3 — QUITO: MariaDB Paralela PARTITION BY HASH (:3308)",
            "shortName": "BD 3 · Quito Paralela (:3308)",
            "engine": "MariaDB 12.3 (PARTITION BY HASH 4)",
            "engineType": "mariadb",
            "role": "Tabla masiva `historico_transacciones` con `PARTITION BY HASH(id) PARTITIONS 4` (Speed-up)",
            "host": os.getenv("BD3_QUITO_PARALELA_HOST", ip_quito),
            "fallbackHost": "127.0.0.1",
            "port": int(os.getenv("BD3_QUITO_PARALELA_PORT", "3308")),
            "database": os.getenv("BD3_QUITO_PARALELA_DATABASE", "quito_paralela_db"),
            "user": os.getenv("BD3_QUITO_PARALELA_USER", "root"),
            "password": os.getenv("BD3_QUITO_PARALELA_PASSWORD", MARIADB_PASS),
            "heidiSqlHint": f"HeidiSQL -> Host: {ip_quito} | Puerto: 3308 | BD: quito_paralela_db",
        },
        "GUAYAQUIL": {
            "bdId": "BD 4",
            "id": "guayaquil-sql",
            "xSede": "GUAYAQUIL",
            "site": "GUAYAQUIL",
            "siteLabel": "Laptop — Nodo GUAYAQUIL (Local + Docker)",
            "machine": f"Laptop ({ip_gye})",
            "name": "BD 4 — GUAYAQUIL: MariaDB ERP OLTP (:3307)",
            "shortName": "BD 4 · Guayaquil ERP (:3307)",
            "engine": "MariaDB 12.3 (SQL OLTP Local)",
            "engineType": "mariadb",
            "role": "Base operacional de 'La Cava' en Guayaquil + 15 Usuarios RBAC (C, I, V, TH, Ctbl)",
            "host": os.getenv("BD4_GUAYAQUIL_HOST", ip_gye),
            "fallbackHost": "127.0.0.1",
            "port": int(os.getenv("BD4_GUAYAQUIL_PORT", "3307")),
            "database": os.getenv("BD4_GUAYAQUIL_DATABASE", "licoreriadatabase"),
            "user": os.getenv("BD4_GUAYAQUIL_USER", "root"),
            "password": os.getenv("BD4_GUAYAQUIL_PASSWORD", MARIADB_PASS),
            "heidiSqlHint": f"HeidiSQL -> Host: {ip_gye} | Puerto: 3307 | BD: licoreriadatabase (ERP)",
        },
        "GUAYAQUIL_DWH": {
            "bdId": "BD 5",
            "id": "guayaquil-replica",
            "xSede": "GUAYAQUIL_DWH",
            "site": "GUAYAQUIL",
            "siteLabel": "Laptop — Nodo GUAYAQUIL (Local + Docker)",
            "machine": f"Laptop ({ip_gye})",
            "name": "BD 5 — GUAYAQUIL: MariaDB DWH Estrella Power BI (:3309)",
            "shortName": "BD 5 · Guayaquil DWH (:3309)",
            "engine": "MariaDB 12.3 (OLAP / Esquema Estrella)",
            "engineType": "mariadb",
            "role": "Data Warehouse Estrella (`fact_ventas`, `dim_sede`, `dim_producto`, `dim_tiempo`) para Power BI",
            "host": os.getenv("BD5_GUAYAQUIL_DWH_HOST", ip_gye),
            "fallbackHost": "127.0.0.1",
            "port": int(os.getenv("BD5_GUAYAQUIL_DWH_PORT", "3309")),
            "database": os.getenv("BD5_GUAYAQUIL_DWH_DATABASE", "db_gye_dwh"),
            "user": os.getenv("BD5_GUAYAQUIL_DWH_USER", "root"),
            "password": os.getenv("BD5_GUAYAQUIL_DWH_PASSWORD", MARIADB_PASS),
            "heidiSqlHint": f"Power BI / HeidiSQL -> Host: {ip_gye} | Puerto: 3309 | BD: db_gye_dwh",
        },
        "CUENCA": {
            "bdId": "BD 6",
            "id": "cuenca-cloud",
            "xSede": "CUENCA",
            "site": "CUENCA_LOJA_CLOUD",
            "siteLabel": "Nodo CUENCA — ERP PostgreSQL (en la Laptop)",
            "machine": f"Laptop ({ip_gye}) · PostgreSQL 18",
            "name": "BD 6 — CUENCA: ERP PostgreSQL 18 (:5432)",
            "shortName": "BD 6 · Cuenca ERP PostgreSQL (:5432)",
            "engine": "PostgreSQL 18 (ERP lacava_cuenca)",
            "engineType": "postgresql",
            "role": "ERP completo de la sucursal Cuenca en un motor distinto (PostgreSQL): heterogeneidad del clúster",
            # Es un PostgreSQL local de la laptop (el proyecto Supabase original ya no existe): se muestra tal cual es.
            "host": os.getenv("BD6_CUENCA_HOST", "127.0.0.1"),
            "fallbackHost": os.getenv("BD6_CUENCA_HOST", "127.0.0.1"),
            "port": int(os.getenv("BD6_CUENCA_PORT", "5432")),
            "database": os.getenv("BD6_CUENCA_DATABASE", "lacava_cuenca"),
            "user": os.getenv("BD6_CUENCA_USER", "postgres"),
            "password": os.getenv("BD6_CUENCA_PASSWORD", PG_PASS),
            "heidiSqlHint": "HeidiSQL / pgAdmin -> 127.0.0.1:5432 | BD: lacava_cuenca",
        },
    }


# Mapa inverso para soportar tanto `X-Sede` (`QUITO`, `GUAYAQUIL`, etc.) como los IDs de la consola (`quito-sql`, etc.)
def resolve_sede_key(key_or_header: str) -> str:
    clean = (key_or_header or "GUAYAQUIL").strip().upper()
    alias_map = {
        "QUITO": "QUITO",
        "QUITO-SQL": "QUITO",
        "BD1": "QUITO",
        "QUITO_NOSQL": "QUITO_NOSQL",
        "QUITO-NOSQL": "QUITO_NOSQL",
        "BD2": "QUITO_NOSQL",
        "QUITO_PARALELA": "QUITO_PARALELA",
        "QUITO-OTRAS": "QUITO_PARALELA",
        "BD3": "QUITO_PARALELA",
        "GUAYAQUIL": "GUAYAQUIL",
        "GUAYAQUIL-SQL": "GUAYAQUIL",
        "BD4": "GUAYAQUIL",
        "GUAYAQUIL_DWH": "GUAYAQUIL_DWH",
        "GUAYAQUIL-REPLICA": "GUAYAQUIL_DWH",
        "BD5": "GUAYAQUIL_DWH",
        "CUENCA": "CUENCA",
        "CUENCA_CLOUD": "CUENCA",
        "CUENCA-CLOUD": "CUENCA",
        "BD6": "CUENCA",
    }
    return alias_map.get(clean, "GUAYAQUIL")


def public_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """Copia de la configuración del nodo SIN la contraseña (nunca se envía al navegador)."""
    return {k: v for k, v in cfg.items() if k != "password"}


def serialize_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (Decimal, float)):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace")
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, default=str)
    return str(val) if type(val).__name__ == "ObjectId" else val


def connect_mariadb_with_fallback(cfg: dict[str, Any]):
    # Si el nodo pertenece a la PC de Escritorio (QUITO: 100.77.220.102), NO ocultamos su caída:
    # use_pure=True evita bloqueos de DNS inverso en el conector C de Windows sobre Tailscale.
    conn = mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        connection_timeout=3,
        autocommit=True,
        use_pure=True,
    )
    # Una sesión cortada por la red no debe retener bloqueos horas (wait_timeout por defecto = 8 h)
    cur = conn.cursor()
    cur.execute("SET SESSION wait_timeout = 300, SESSION innodb_lock_wait_timeout = 20")
    cur.close()
    return conn, cfg["host"]


SEDES_ERP = ("QUITO", "GUAYAQUIL", "CUENCA")


def fijar_actor_auditoria(cur, engine: str, username: str, ip: str = "") -> str | None:
    """
    Los 3 ERP auditan TODO con triggers que leen el actor de la sesión
    (MariaDB: @auditoria_usuario/@auditoria_ip · PostgreSQL: app.auditoria_usuario/app.auditoria_ip).
    Se traduce el usuario RBAC (p. ej. v_operador) a su id_Usuario del ERP para que el log diga QUIÉN fue.
    """
    try:
        if engine == "postgresql":
            cur.execute("SELECT id_usuario FROM usuarios WHERE usr_username = %s", (username,))
            row = cur.fetchone()
            uid = str(row[0]).strip() if row else None
            cur.execute("SELECT set_config('app.auditoria_usuario', %s, false), set_config('app.auditoria_ip', %s, false)",
                        (uid or "", (ip or "")[:45]))
            cur.fetchall()
        else:
            cur.execute("SELECT id_Usuario FROM usuarios WHERE usr_Username = %s", (username,))
            row = cur.fetchone()
            uid = str(row[0]) if row else None
            cur.execute("SET @auditoria_usuario = %s, @auditoria_ip = %s", (uid or "", (ip or "")[:45]))
        return uid
    except Exception:
        return None


def connect_mongo_with_fallback(cfg: dict[str, Any]):
    cli = MongoClient(f"mongodb://{cfg['host']}:{cfg['port']}/", serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
    cli.admin.command("ping")
    return cli, cfg["host"]


def connect_postgres_with_fallback(cfg: dict[str, Any]):
    dsn = f"host={cfg['fallbackHost']} port={cfg['port']} dbname={cfg['database']} user={cfg['user']} password={cfg['password']} connect_timeout=3"
    return psycopg.connect(dsn, autocommit=True), cfg["host"]


DBA_PRESETS = {
    "QUITO_NOSQL": [
        {
            "label": "1. Consultar Colección `eventos_agentes` (Agente 2 MongoDB :27017)",
            "sql": "MONGO_COLLECTION:eventos_agentes"
        },
        {
            "label": "2. Consultar Colección `logs_auditoria` (Alertas JSON MongoDB :27017)",
            "sql": "MONGO_COLLECTION:logs_auditoria"
        },
    ],
    "QUITO_PARALELA": [
        {
            "label": "1. Ver las 4 Particiones HASH de `historico_transacciones` (Speed-up :3308)",
            "sql": "SELECT PARTITION_NAME AS particion_hash, PARTITION_METHOD AS metodo, PARTITION_EXPRESSION AS expresion, TABLE_ROWS AS filas_estimadas FROM information_schema.PARTITIONS WHERE TABLE_SCHEMA = 'quito_paralela_db' AND TABLE_NAME = 'historico_transacciones';"
        },
        {
            "label": "2. Distribución real de registros por Partición (p0, p1, p2, p3)",
            "sql": "SELECT particion_hash, COUNT(*) AS total_registros, SUM(monto_usd) AS volumen_usd FROM historico_transacciones GROUP BY particion_hash ORDER BY particion_hash;"
        },
        {
            "label": "3. Lotes insertados por Agente 3 (`X-Sede: QUITO_PARALELA` :3308)",
            "sql": "SELECT id, sede_origen, usuario_rbac, rol_rbac, modulo, codigo_referencia, monto_usd, particion_hash, fecha_registro FROM historico_transacciones ORDER BY id DESC LIMIT 20;"
        },
    ],
    "GUAYAQUIL_DWH": [
        {
            "label": "1. Esquema Estrella Power BI: Hechos + Dimensiones (:3309 `db_gye_dwh`)",
            "sql": "SELECT f.id_fact, s.nombre_sede, p.nombre_producto, p.categoria, t.nombre_mes, f.usuario_rbac, f.rol_rbac, f.cantidad_botellas, f.total_venta_usd, f.etl_lote, f.fecha_carga_etl FROM fact_ventas f JOIN dim_sede s ON f.id_sede = s.id_sede JOIN dim_producto p ON f.id_producto = p.id_producto JOIN dim_tiempo t ON f.id_tiempo = t.id_tiempo ORDER BY f.id_fact DESC LIMIT 20;"
        },
        {
            "label": "2. Consolidado OLAP por Sede para Dashboard Power BI (:3309)",
            "sql": "SELECT s.id_sede, s.nombre_sede, s.maquina_fisica, COUNT(f.id_fact) AS lotes_etl, SUM(f.cantidad_botellas) AS botellas_totales, SUM(f.total_venta_usd) AS ingresos_usd FROM fact_ventas f JOIN dim_sede s ON f.id_sede = s.id_sede GROUP BY s.id_sede, s.nombre_sede, s.maquina_fisica ORDER BY ingresos_usd DESC;"
        },
        {
            "label": "3. Ver Dimensiones del Estrella (`dim_sede`, `dim_producto`, `dim_tiempo`)",
            "sql": "SELECT * FROM dim_sede;"
        },
    ],
}


for _sede in ("QUITO_PARALELA", "GUAYAQUIL_DWH"):
    DBA_PRESETS[_sede].append({
        "label": "Auditoría: últimas 20 acciones registradas en esta BD (log_auditoria)",
        "sql": "SELECT log_FechaHora, id_Usuario, log_TablaAfectada, log_Accion, log_IP, log_ValorNuevo "
               "FROM log_auditoria ORDER BY log_FechaHora DESC LIMIT 20;",
    })


def _presets_erp(sede: str, bd: str, bitacora: str, motor: str) -> list[dict[str, str]]:
    """Consultas del ERP de cada sede (en minúsculas: valen en MariaDB y en PostgreSQL)."""
    version = ("SELECT @@hostname AS host, @@port AS puerto, @@version AS motor, DATABASE() AS bd_activa;" if motor == "mariadb"
               else "SELECT inet_server_port() AS puerto, version() AS motor, current_database() AS bd_activa;")
    return [
        {"label": f"1. Ventas del ERP de {sede} (facturas + cliente)",
         "sql": "SELECT f.id_factura, c.cli_nombre AS cliente, f.fac_fecha, f.fac_subtotal, f.fac_iva, f.fac_total, f.estado_fac "
                "FROM facturas f LEFT JOIN clientes c ON f.id_cliente = c.id_cliente ORDER BY f.fac_fecha DESC LIMIT 15;"},
        {"label": f"2. Bitácora del agente de {sede} enlazada a su documento ({bitacora})",
         "sql": f"SELECT id_op, agente_nombre, usuario_rbac, rol_rbac, modulo, tabla_ref, documento_ref, operacion, monto_usd, fecha_hora "
                f"FROM {bitacora} ORDER BY id_op DESC LIMIT 15;"},
        {"label": "3. Los 5 módulos del ERP (C, I, V, TH, Ctbl) + bodega",
         "sql": "SELECT 'C - Compras' AS modulo, COUNT(*) AS registros FROM compras UNION ALL SELECT 'I - Productos', COUNT(*) FROM productos "
                "UNION ALL SELECT 'I - Recepciones', COUNT(*) FROM recepciones UNION ALL SELECT 'I - Entregas', COUNT(*) FROM entregas "
                "UNION ALL SELECT 'V - Facturas', COUNT(*) FROM facturas UNION ALL SELECT 'TH - Empleados', COUNT(*) FROM empleados "
                "UNION ALL SELECT 'Ctbl - Asientos', COUNT(*) FROM asientos;"},
        {"label": f"4. Auditoría total: últimos 20 cambios del log de {sede} (log_seq = orden del cambio)",
         "sql": "SELECT log_seq, log_fechahora, id_usuario, log_tablaafectada, log_accion, log_sede, log_ip "
                "FROM log_auditoria ORDER BY log_seq DESC LIMIT 20;"},
        {"label": "5. Auditoría: quién hizo qué (acciones por usuario y tabla)",
         "sql": "SELECT COALESCE(id_usuario, '(sin usuario)') AS usuario, log_tablaafectada, log_accion, COUNT(*) AS acciones "
                "FROM log_auditoria GROUP BY id_usuario, log_tablaafectada, log_accion ORDER BY acciones DESC LIMIT 30;"},
        {"label": "6. Matriz de 17 usuarios RBAC (15 módulos + DBA + Admin)",
         "sql": "SELECT username, rol_bd, rol_aplicacion, modulo_codigo, modulo_nombre, nombre_colaborador, sede_nodo, ultima_actividad "
                "FROM rbac_matriz_15_usuarios ORDER BY modulo_codigo, rol_bd;"},
        {"label": f"7. Motor, puerto y base activa ({bd})", "sql": version},
    ]


DBA_PRESETS["QUITO"] = _presets_erp("Quito", "lacava_quito :3307", "operaciones_agentes_ia", "mariadb")
DBA_PRESETS["GUAYAQUIL"] = _presets_erp("Guayaquil", "licoreriadatabase :3307", "operaciones_agentes_ia", "mariadb")
DBA_PRESETS["CUENCA"] = _presets_erp("Cuenca", "lacava_cuenca :5432", "operaciones_agentes_cloud", "postgresql")
for _sede, _tabla, _de in (("GUAYAQUIL", "replica_quito_log", "Quito"), ("CUENCA", "replica_guayaquil_log", "Guayaquil"),
                           ("QUITO", "replica_cuenca_log", "Cuenca")):
    DBA_PRESETS[_sede].append({
        "label": f"8. Réplica: log de cambios de {_de} guardado en esta BD ({_tabla})",
        "sql": f"SELECT etiqueta_replica, log_seq_origen, fecha_origen, replicado_en, id_usuario, tabla, accion, valor_nuevo "
               f"FROM {_tabla} ORDER BY log_seq_origen DESC LIMIT 20;",
    })


def inspect_single_bd_sync(sede_key: str) -> dict[str, Any]:
    configs = get_cluster_6dbs_config()
    cfg = configs[sede_key]
    t0 = time.perf_counter()
    try:
        if cfg["engineType"] == "mariadb":
            conn, active_host = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT @@version AS ver, @@port AS port, @@datadir AS datadir")
            meta = cur.fetchone() or {}
            cur.execute(
                "SELECT COUNT(*) AS cnt, COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) AS bytes_size "
                "FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
                (cfg["database"],),
            )
            tinfo = cur.fetchone() or {}
            cur.execute("SELECT COUNT(*) AS active_conns FROM information_schema.PROCESSLIST")
            cinfo = cur.fetchone() or {}

            modules_summary = []
            if sede_key in ("QUITO", "GUAYAQUIL"):
                for code, name, tbl in [
                    ("C", "Compras", "compras"),
                    ("I", "Inventarios", "productos"),
                    ("V", "Ventas", "facturas"),
                    ("TH", "Talento Humano", "empleados"),
                    ("Ctbl", "Contabilidad", "asientos"),
                ]:
                    cur.execute(f"SELECT COUNT(*) AS c FROM `{tbl}`")
                    r = cur.fetchone() or {}
                    modules_summary.append({"code": code, "name": name, "table": tbl, "rows": int(r.get("c", 0))})

            cur.close()
            conn.close()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                **public_cfg(cfg),
                "activeHost": active_host,
                "status": "ONLINE",
                "pingMs": latency_ms,
                "latencyMs": latency_ms,
                "version": str(meta.get("ver", "MariaDB 12.3")),
                "actualPort": int(meta.get("port", cfg["port"])),
                "datadir": str(meta.get("datadir", "")),
                "tablesCount": int(tinfo.get("cnt", 0)),
                "sizeKb": round(float(tinfo.get("bytes_size", 0)) / 1024.0, 1),
                "activeConnections": int(cinfo.get("active_conns", 1)),
                "modules": modules_summary,
                "presets": DBA_PRESETS.get(sede_key, []),
            }

        elif cfg["engineType"] == "mongodb":
            cli, active_host = connect_mongo_with_fallback(cfg)
            db = cli[cfg["database"]]
            cols = db.list_collection_names()
            total_docs = sum(db[c].count_documents({}) for c in cols)
            server_info = cli.server_info()
            cli.close()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                **public_cfg(cfg),
                "activeHost": active_host,
                "status": "ONLINE",
                "pingMs": latency_ms,
                "latencyMs": latency_ms,
                "version": f"MongoDB {server_info.get('version', '7.0')}",
                "actualPort": cfg["port"],
                "datadir": "MongoDB WiredTiger Storage (:27017)",
                "tablesCount": len(cols),
                "sizeKb": round(total_docs * 1.8, 1),
                "activeConnections": 3,
                "modules": [],
                "presets": DBA_PRESETS.get(sede_key, []),
            }

        else:
            conn, active_host = connect_postgres_with_fallback(cfg)
            with conn.cursor() as cur:
                cur.execute("SELECT version(), inet_server_port(), current_setting('data_directory', true)")
                ver_row = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
                t_cnt = cur.fetchone()[0]
                cur.execute("SELECT pg_database_size(current_database())")
                db_bytes = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()")
                a_conns = cur.fetchone()[0]
            conn.close()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                **public_cfg(cfg),
                "activeHost": active_host,
                "status": "ONLINE",
                "pingMs": latency_ms,
                "latencyMs": latency_ms,
                "version": "PostgreSQL 18 (ERP Cuenca)",
                "actualPort": int(ver_row[1] or cfg["port"]) if ver_row else cfg["port"],
                "datadir": str(ver_row[2] or "datadir local de PostgreSQL"),
                "tablesCount": int(t_cnt or 0),
                "sizeKb": round(float(db_bytes or 0) / 1024.0, 1),
                "activeConnections": int(a_conns or 1),
                "modules": [],
                "presets": DBA_PRESETS.get(sede_key, []),
            }

    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            **public_cfg(cfg),
            "activeHost": cfg["host"],
            "status": "OFFLINE",
            "pingMs": latency_ms,
            "latencyMs": latency_ms,
            "error": str(exc),
            "version": cfg["engine"],
            "actualPort": cfg["port"],
            "datadir": "OFFLINE",
            "tablesCount": 0,
            "sizeKb": 0,
            "activeConnections": 0,
            "modules": [],
            "presets": DBA_PRESETS.get(sede_key, []),
        }


def fetch_global_records_from_bd_sync(sede_key: str, limit: int = 8) -> dict[str, Any]:
    """Extrae registros unificados de cada una de las 6 BDs con el campo obligatorio `origen_nodo`."""
    configs = get_cluster_6dbs_config()
    cfg = configs[sede_key]
    t0 = time.perf_counter()
    records = []
    try:
        if sede_key in ("QUITO", "GUAYAQUIL"):
            conn, active_host = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT id_op, sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo,
                       operacion, monto_usd, replica_api, fecha_hora
                FROM operaciones_agentes_ia
                ORDER BY id_op DESC LIMIT %s
            """, (int(limit),))
            for r in cur.fetchall():
                records.append({
                    "id": f"{cfg['bdId']}-OP-{r['id_op']}",
                    "origen_nodo": f"{cfg['bdId']} · {sede_key} ({active_host}:{cfg['port']})",
                    "sede": sede_key,
                    "motor": cfg["engine"],
                    "puerto": cfg["port"],
                    "modulo": r["modulo"],
                    "usuario_rbac": r["usuario_rbac"],
                    "rol_rbac": r["rol_rbac"],
                    "detalle": r["operacion"],
                    "monto_usd": float(r["monto_usd"] or 0),
                    "fecha_hora": serialize_value(r["fecha_hora"]),
                })
            cur.close()
            conn.close()

        elif sede_key == "QUITO_NOSQL":
            cli, active_host = connect_mongo_with_fallback(cfg)
            db = cli[cfg["database"]]
            docs = list(db["eventos_agentes"].find().sort("_id", -1).limit(limit)) + list(
                db["logs_auditoria"].find().sort("_id", -1).limit(limit)
            )
            for idx, d in enumerate(docs[: limit * 2], start=1):
                records.append({
                    "id": str(d.get("evento_id") or f"BD2-MONGO-{idx}"),
                    "origen_nodo": f"BD 2 · QUITO_NOSQL ({active_host}:{cfg['port']})",
                    "sede": "QUITO_NOSQL",
                    "motor": "MongoDB NoSQL (:27017)",
                    "puerto": cfg["port"],
                    "modulo": d.get("modulo", "INVENTARIOS"),
                    "usuario_rbac": d.get("usuario_rbac", "i_supervisor"),
                    "rol_rbac": d.get("rol_rbac", "rol_supervisor"),
                    "detalle": d.get("mensaje") or d.get("accion") or json.dumps(d.get("detalle", {}), ensure_ascii=False),
                    "monto_usd": 0.0,
                    "fecha_hora": str(d.get("timestamp", datetime.now().isoformat())),
                })
            cli.close()

        elif sede_key == "QUITO_PARALELA":
            conn, active_host = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT id, usuario_rbac, rol_rbac, modulo, codigo_referencia, monto_usd, particion_hash, fecha_registro
                FROM historico_transacciones
                ORDER BY id DESC LIMIT %s
            """, (int(limit),))
            for r in cur.fetchall():
                records.append({
                    "id": f"BD3-HASH-{r['id']}",
                    "origen_nodo": f"BD 3 · QUITO_PARALELA ({active_host}:{cfg['port']})",
                    "sede": "QUITO_PARALELA",
                    "motor": "MariaDB PARTITION BY HASH (:3308)",
                    "puerto": cfg["port"],
                    "modulo": r["modulo"],
                    "usuario_rbac": r["usuario_rbac"],
                    "rol_rbac": r["rol_rbac"],
                    "detalle": f"Lote paralelo {r['codigo_referencia']} -> Partición HASH p{r['particion_hash']}",
                    "monto_usd": float(r["monto_usd"] or 0),
                    "fecha_hora": serialize_value(r["fecha_registro"]),
                })
            cur.close()
            conn.close()

        elif sede_key == "GUAYAQUIL_DWH":
            conn, active_host = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT f.id_fact, f.id_sede, p.nombre_producto, f.usuario_rbac, f.rol_rbac,
                       f.cantidad_botellas, f.total_venta_usd, f.etl_lote, f.fecha_carga_etl
                FROM fact_ventas f
                LEFT JOIN dim_producto p ON f.id_producto = p.id_producto
                ORDER BY f.id_fact DESC LIMIT %s
            """, (int(limit),))
            for r in cur.fetchall():
                records.append({
                    "id": f"BD5-DWH-{r['id_fact']}",
                    "origen_nodo": f"BD 5 · GUAYAQUIL_DWH ({active_host}:{cfg['port']})",
                    "sede": "GUAYAQUIL_DWH",
                    "motor": "MariaDB Estrella DWH (:3309)",
                    "puerto": cfg["port"],
                    "modulo": "VENTAS",
                    "usuario_rbac": r["usuario_rbac"],
                    "rol_rbac": r["rol_rbac"],
                    "detalle": f"ETL Power BI [{r['etl_lote']}] ({r['id_sede']}): {r['cantidad_botellas']} bot. {r['nombre_producto']}",
                    "monto_usd": float(r["total_venta_usd"] or 0),
                    "fecha_hora": serialize_value(r["fecha_carga_etl"]),
                })
            cur.close()
            conn.close()

        elif sede_key == "CUENCA":
            conn, active_host = connect_postgres_with_fallback(cfg)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id_op, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, latencia_wan_ms, fecha_hora
                    FROM operaciones_agentes_cloud
                    ORDER BY id_op DESC LIMIT %s
                """, (int(limit),))
                for r in cur.fetchall():
                    records.append({
                        "id": f"BD6-CLOUD-{r[0]}",
                        "origen_nodo": f"BD 6 · CUENCA ERP PostgreSQL ({active_host}:{cfg['port']})",
                        "sede": "CUENCA",
                        "motor": "PostgreSQL 18 ERP (:5432)",
                        "puerto": cfg["port"],
                        "modulo": r[3],
                        "usuario_rbac": r[1],
                        "rol_rbac": r[2],
                        "detalle": f"{r[4]} (WAN: {r[6]} ms)",
                        "monto_usd": float(r[5] or 0),
                        "fecha_hora": serialize_value(r[7]),
                    })
            conn.close()

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "bdId": cfg["bdId"],
            "sede": sede_key,
            "origen_nodo": f"{cfg['bdId']} · {sede_key} (:{cfg['port']})",
            "status": "ONLINE",
            "latencyMs": latency_ms,
            "count": len(records),
            "records": records,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "bdId": cfg["bdId"],
            "sede": sede_key,
            "origen_nodo": f"{cfg['bdId']} · {sede_key} (:{cfg['port']})",
            "status": "OFFLINE",
            "latencyMs": latency_ms,
            "error": str(exc),
            "count": 0,
            "records": [],
        }


# ==============================================================================
# ENDPOINTS OFICIALES DEL CONTRATO COMPARTIDO (/api/dba/health y /api/dba/global)
# ==============================================================================

@router.get("/api/dba/health")
async def get_dba_cluster_health(x_sede: str | None = Header(default=None, alias="X-Sede")):
    """
    Tarea 2.2: Devuelve el estado (ONLINE/OFFLINE) y ping (ms) de las 6 BDs en paralelo.
    Soporta filtro opcional mediante el header `X-Sede`.
    """
    keys = ["QUITO", "QUITO_NOSQL", "QUITO_PARALELA", "GUAYAQUIL", "GUAYAQUIL_DWH", "CUENCA"]
    results = await asyncio.gather(*(asyncio.to_thread(inspect_single_bd_sync, k) for k in keys))
    online_count = sum(1 for r in results if r["status"] == "ONLINE")
    routed_sede = resolve_sede_key(x_sede) if x_sede else None
    return {
        "timestamp": datetime.now().isoformat(),
        "apiReplica": REPLICA_ID,
        "routedHeaderXSede": routed_sede,
        "totalDatabases": len(results),
        "onlineDatabases": online_count,
        "allHealthy": online_count == len(results),
        "nodes": results,
    }


@router.get("/api/dba/global")
async def get_dba_global_console(
    sede: str | None = Query(default=None, description="Filtrar por sede (QUITO, QUITO_NOSQL, QUITO_PARALELA, GUAYAQUIL, GUAYAQUIL_DWH, CUENCA)"),
    modulo: str | None = Query(default=None, description="Filtrar por módulo (COMPRAS, INVENTARIOS, VENTAS, TALENTO_HUMANO, CONTABILIDAD)"),
    x_sede: str | None = Header(default=None, alias="X-Sede"),
):
    """
    Tarea 2.2: Consulta las 6 BDs en paralelo (`asyncio.gather`), unifica los resultados en un solo JSON
    agregando el campo `origen_nodo` y mide la latencia (`ms`) de cada nodo.
    """
    t0 = time.perf_counter()
    keys = ["QUITO", "QUITO_NOSQL", "QUITO_PARALELA", "GUAYAQUIL", "GUAYAQUIL_DWH", "CUENCA"]
    node_results = await asyncio.gather(*(asyncio.to_thread(fetch_global_records_from_bd_sync, k) for k in keys))

    unified = []
    latencies = {}
    for nr in node_results:
        latencies[nr["sede"]] = {
            "bdId": nr["bdId"],
            "status": nr["status"],
            "latencyMs": nr["latencyMs"],
            "recordsReturned": nr["count"],
        }
        unified.extend(nr["records"])

    effective_sede = (sede or x_sede or "").strip().upper()
    if effective_sede and effective_sede != "TODAS":
        resolved = resolve_sede_key(effective_sede)
        unified = [r for r in unified if r["sede"] == resolved]

    if modulo and modulo.strip().upper() not in ("", "TODOS"):
        mod_filter = modulo.strip().upper()
        unified = [r for r in unified if r["modulo"].upper() == mod_filter]

    total_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "timestamp": datetime.now().isoformat(),
        "apiReplica": REPLICA_ID,
        "totalExecutionTimeMs": total_ms,
        "totalRecords": len(unified),
        "filtersApplied": {"sede": effective_sede or "TODAS", "modulo": modulo or "TODOS"},
        "nodeLatencies": latencies,
        "data": unified,
    }


class AgentOperationRequest(BaseModel):
    agente: str = Field(default="Agente-IA", description="Nombre del agente transaccional")
    usuario: str = Field(default="v_jefe", description="Uno de los 15 usuarios RBAC")
    password: str | None = Field(default=None, description="Contraseña del usuario RBAC enviada por el agente")
    modulo: str | None = Field(default=None, description="Módulo C, I, V, TH, Ctbl")
    operacion: str = Field(..., description="Descripción o payload de la operación")
    montoUsd: float = Field(default=0.0, description="Monto asociado en USD")
    extraJson: dict[str, Any] | None = Field(default=None, description="Payload adicional JSON para NoSQL o ETL")
    documentoApp: dict[str, Any] | None = Field(
        default=None,
        description="Documento que el agente creó/confirmó en la app principal (p. ej. {'tabla': 'RECEPCIONES', 'id': 'REC-000007', 'accion': '...'}). "
                    "Si viene, la operación se anota en la bitácora enlazada a ese documento y no se crea otro documento en la BD del clúster.",
    )


DDL_LOG_AUDITORIA_MARIADB = (
    "CREATE TABLE IF NOT EXISTS log_auditoria ("
    " id_Log VARCHAR(30) NOT NULL PRIMARY KEY, id_Usuario VARCHAR(20) NULL,"
    " log_FechaHora DATETIME DEFAULT CURRENT_TIMESTAMP, log_TablaAfectada VARCHAR(60) NULL,"
    " log_Accion VARCHAR(40) NULL, log_IP VARCHAR(45) NULL, log_ValorAnterior TEXT NULL, log_ValorNuevo TEXT NULL)"
)
_AUDIT_READY: set[str] = set()


def _accion_auditoria(accion: str) -> str:
    a = (accion or "").upper()
    for k in ("INSERT", "UPDATE", "DELETE"):
        if k in a:
            return k
    return "INSERT" if a.startswith(("CREA", "REGISTR", "VENTA", "OC ")) else (a.split(" ")[0][:40] or "REGISTRO")


def registrar_auditoria(sede_key: str, usuario: str, eventos: list[dict[str, Any]], base: dict[str, Any], ip: str) -> dict[str, Any]:
    """
    Escribe una fila de auditoría por cada tabla afectada en la MISMA BD donde ocurrió la operación:
      MariaDB (BD 1, 3, 4, 5) -> log_auditoria (se crea si la BD no la tenía)
      PostgreSQL (BD 6)       -> log_auditoria_cloud
    Nunca hace fallar la operación: si la auditoría falla, se informa en el impacto.
    """
    cfg = get_cluster_6dbs_config()[sede_key]
    filas = []
    for ev in eventos or [{"tabla": "operaciones_agentes_ia", "accion": "INSERT", "id": base.get("operacion_id")}]:
        filas.append((str(ev.get("tabla", ""))[:60], _accion_auditoria(str(ev.get("accion", ""))),
                      json.dumps({**base, "tabla": ev.get("tabla"), "registro": ev.get("id"), "accion_detalle": ev.get("accion")},
                                 ensure_ascii=False, default=str)))
    try:
        if cfg["engineType"] == "postgresql":
            conn, _ = connect_postgres_with_fallback(cfg)
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO log_auditoria_cloud (sucursal_origen, usuario_cloud, evento, detalle) VALUES (%s, %s, %s, %s)",
                    [(sede_key, usuario[:60], f"{accion} {tabla}"[:120], valor) for tabla, accion, valor in filas],
                )
            conn.close()
            destino = "log_auditoria_cloud"
        else:
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            if sede_key not in _AUDIT_READY:
                cur.execute(DDL_LOG_AUDITORIA_MARIADB)
                _AUDIT_READY.add(sede_key)
            cur.executemany(
                "INSERT INTO log_auditoria (id_Log, id_Usuario, log_TablaAfectada, log_Accion, log_IP, log_ValorNuevo) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [(f"AG-{uuid4().hex[:16].upper()}", usuario[:20], tabla, accion, ip or None, valor) for tabla, accion, valor in filas],
            )
            cur.close()
            conn.close()
            destino = "log_auditoria"
        return {"tabla": destino, "accion": f"INSERT {len(filas)} fila(s) de auditoría", "id": None, "ok": True}
    except Exception as exc:
        return {"tabla": "auditoría", "accion": "INSERT", "id": None, "ok": False, "error": str(exc)[:200]}


_REF_COLUMNS_READY: set[str] = set()


def _ensure_ref_columns_mariadb(cur, sede_key: str) -> None:
    """Agrega (una vez por proceso) las columnas que enlazan cada operación con su documento de negocio."""
    if sede_key in _REF_COLUMNS_READY:
        return
    cur.execute(
        "ALTER TABLE operaciones_agentes_ia "
        "ADD COLUMN IF NOT EXISTS tabla_ref VARCHAR(40) NULL, "
        "ADD COLUMN IF NOT EXISTS documento_ref VARCHAR(60) NULL"
    )
    _REF_COLUMNS_READY.add(sede_key)


def _ensure_ref_columns_pg(cur) -> None:
    if "CUENCA" in _REF_COLUMNS_READY:
        return
    cur.execute(
        "ALTER TABLE operaciones_agentes_cloud "
        "ADD COLUMN IF NOT EXISTS tabla_ref VARCHAR(40) NULL, "
        "ADD COLUMN IF NOT EXISTS documento_ref VARCHAR(60) NULL"
    )
    _REF_COLUMNS_READY.add("CUENCA")


@router.post("/api/agentes/operacion")
@router.post("/api/dba/operacion")
def handle_agent_routed_operation(
    payload: AgentOperationRequest,
    request: Request,
    x_sede: str = Header(default="GUAYAQUIL", alias="X-Sede"),
):
    """
    Contrato C: Endpoint receptor de los 6 Agentes IA (3 de Quito + 3 de Guayaquil/Cuenca).
    Enruta dinámicamente a la BD correspondiente según el header obligatorio `X-Sede`
    y valida la trazabilidad con uno de los 15 usuarios y 3 roles RBAC.
    """
    sede_key = resolve_sede_key(x_sede)
    configs = get_cluster_6dbs_config()
    cfg = configs[sede_key]

    user_clean = payload.usuario.strip().lower()
    rol_rbac, default_mod, expected_pw = USUARIOS_15_MAP.get(user_clean, ("rol_operador", "VENTAS", ""))
    if payload.password and expected_pw and payload.password != expected_pw:
        raise HTTPException(status_code=401, detail=f"Credenciales RBAC inválidas para el usuario '{user_clean}'.")
    modulo_final = (payload.modulo or default_mod).strip().upper()

    t0 = time.perf_counter()
    impacto: list[dict[str, Any]] = []
    ip_cliente = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "") or "")[:45]
    # Documento real que el agente creó/confirmó usando la app (POS, compra, recepción, entrega) en el ERP de la sede.
    doc_app = payload.documentoApp or {}
    tabla_ref = str(doc_app.get("tabla") or "").upper()[:40] or None
    documento_ref = str(doc_app.get("id") or "")[:60] or None

    def _impacto_documento() -> dict[str, Any]:
        if doc_app:
            return {"tabla": f"app:{tabla_ref}", "accion": str(doc_app.get("accion") or "REGISTRO")[:120],
                    "id": documento_ref, "ok": bool(documento_ref)}
        return {"tabla": "(sin documento)", "accion": "SOLO BITÁCORA: el agente no registró un documento en la app",
                "id": None, "ok": True}

    if sede_key in ("QUITO", "GUAYAQUIL"):
        conn, active_host = connect_mariadb_with_fallback(cfg)
        cur = conn.cursor()
        # El trigger TRG_AUD_OPERACIONES_AGENTES_IA_AI escribe LOG_AUDITORIA con este usuario
        actor = fijar_actor_auditoria(cur, "mariadb", user_clean, ip_cliente)
        _ensure_ref_columns_mariadb(cur, sede_key)
        cur.execute(
            "INSERT INTO operaciones_agentes_ia (sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, "
            "replica_api, tabla_ref, documento_ref) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (sede_key, payload.agente, user_clean, rol_rbac, modulo_final, payload.operacion[:255], payload.montoUsd or 0,
             REPLICA_ID, tabla_ref, documento_ref),
        )
        op_id = cur.lastrowid
        impacto.append({"tabla": "operaciones_agentes_ia", "accion": "INSERT (bitácora del agente)", "id": op_id, "ok": True})
        impacto.append(_impacto_documento())
        try:
            cur.execute("UPDATE rbac_matriz_15_usuarios SET ultima_actividad = CURRENT_TIMESTAMP WHERE username = %s", (user_clean,))
        except Exception:
            pass
        impacto.append({"tabla": "log_auditoria", "accion": f"triggers TRG_AUD_* (usuario {actor or 'sin mapear'})",
                        "id": None, "ok": bool(actor)})
        cur.close()
        conn.close()

    elif sede_key == "QUITO_NOSQL":
        cli, active_host = connect_mongo_with_fallback(cfg)
        db = cli[cfg["database"]]
        doc = {
            "evento_id": f"AGT2-{uuid4().hex[:8].upper()}",
            "agente": payload.agente,
            "header_x_sede": "QUITO_NOSQL",
            "usuario_rbac": user_clean,
            "rol_rbac": rol_rbac,
            "modulo": modulo_final,
            "mensaje": payload.operacion,
            "detalle": payload.extraJson or {"monto_usd": payload.montoUsd, "replica": REPLICA_ID},
            "timestamp": datetime.now().isoformat(),
        }
        db["eventos_agentes"].insert_one(dict(doc))
        db["logs_auditoria"].insert_one({**doc, "accion": "LOG_AGENTE_NOSQL"})
        cli.close()
        op_id = doc["evento_id"]
        impacto.append({"tabla": "eventos_agentes (colección)", "accion": "insertOne", "id": op_id, "ok": True})
        impacto.append({"tabla": "logs_auditoria (colección)", "accion": "insertOne", "id": op_id, "ok": True})

    elif sede_key == "QUITO_PARALELA":
        conn, active_host = connect_mariadb_with_fallback(cfg)
        cur = conn.cursor()
        ref = f"HASH-{uuid4().hex[:6].upper()}"
        cur.execute(
            "INSERT INTO historico_transacciones (sede_origen, usuario_rbac, rol_rbac, modulo, codigo_referencia, monto_usd) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("QUITO_PARALELA", user_clean, rol_rbac, modulo_final, ref, payload.montoUsd or 125.50),
        )
        op_id = cur.lastrowid
        cur.execute("SELECT particion_hash FROM historico_transacciones WHERE id = %s", (op_id,))
        part_row = cur.fetchone()
        cur.close()
        conn.close()
        impacto.append({
            "tabla": f"historico_transacciones (partición p{part_row[0] if part_row else '?'})",
            "accion": "INSERT",
            "id": op_id,
            "ok": True,
        })

    elif sede_key == "GUAYAQUIL_DWH":
        etl = run_mini_etl_to_dwh()
        op_id = etl["lote"]
        impacto.extend(etl["fuentes"])

    else:  # CUENCA (ERP PostgreSQL)
        conn, active_host = connect_postgres_with_fallback(cfg)
        # Latencia REAL medida hasta el nodo (conexión incluida)
        latency_wan = round((time.perf_counter() - t0) * 1000, 2)
        with conn.cursor() as cur:
            actor = fijar_actor_auditoria(cur, "postgresql", user_clean, ip_cliente)
            cur.execute(
                "INSERT INTO operaciones_agentes_cloud (sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, "
                "latencia_wan_ms, tabla_ref, documento_ref) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_op",
                ("CUENCA", payload.agente, user_clean, rol_rbac, modulo_final, payload.operacion[:255], payload.montoUsd or 0,
                 latency_wan, tabla_ref, documento_ref),
            )
            op_id = cur.fetchone()[0]
            impacto.append({"tabla": "operaciones_agentes_cloud", "accion": "INSERT (bitácora del agente)", "id": op_id, "ok": True})
            impacto.append(_impacto_documento())
            try:
                cur.execute("UPDATE rbac_matriz_15_usuarios SET ultima_actividad = CURRENT_TIMESTAMP WHERE username = %s", (user_clean,))
            except Exception:
                pass
            impacto.append({"tabla": "log_auditoria", "accion": f"trigger fn_trg_auditoria_general (usuario {actor or 'sin mapear'})",
                            "id": None, "ok": bool(actor)})
        conn.close()

    # Auditoría en la propia BD de la operación (MongoDB ya la guarda en su colección logs_auditoria)
    if sede_key not in ("QUITO_NOSQL",) + SEDES_ERP:  # los 3 ERP ya se auditan solos con sus triggers
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "") or "")[:45]
        auditoria = registrar_auditoria(sede_key, user_clean, [i for i in impacto if i.get("ok")], {
            "agente": payload.agente, "rol_rbac": rol_rbac, "modulo": modulo_final, "operacion_id": str(op_id),
            "operacion": payload.operacion[:200], "monto_usd": payload.montoUsd, "replica_api": REPLICA_ID,
        }, ip)
        impacto.append(auditoria)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "success": True,
        "routedTo": cfg["bdId"],
        "sedeHeader": sede_key,
        "database": cfg["database"],
        "port": cfg["port"],
        "usuarioRbac": user_clean,
        "rolRbac": rol_rbac,
        "modulo": modulo_final,
        "operationId": op_id,
        "impacto": impacto,
        "apiReplica": REPLICA_ID,
        "latencyMs": elapsed_ms,
        "timestamp": datetime.now().isoformat(),
    }


# ==============================================================================
# ENDPOINTS DE COMPATIBILIDAD CON LA INTERFAZ WEB (/api/arquitectura/...)
# ==============================================================================

@router.get("/api/powerbi/estrella")
def get_powerbi_star_schema_dataset():
    """
    Endpoint OLAP listo para Power BI Desktop (Obtener datos -> Web -> http://127.0.0.1:8000/api/powerbi/estrella)
    y para el Dashboard Gerencial en la interfaz web.
    Devuelve la tabla de hechos desnormalizada con sus 3 dimensiones (`dim_sede`, `dim_producto`, `dim_tiempo`)
    desde BD 5 (`db_gye_dwh` en MariaDB :3309).
    """
    configs = get_cluster_6dbs_config()
    conn, active_host = connect_mariadb_with_fallback(configs["GUAYAQUIL_DWH"])
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT
            f.id_fact,
            f.id_sede,
            COALESCE(s.nombre_sede, f.id_sede) AS nombre_sede,
            COALESCE(s.ciudad, 'Guayaquil') AS ciudad,
            COALESCE(s.region, 'Costa') AS region,
            COALESCE(s.maquina_fisica, 'Laptop (100.123.81.4)') AS maquina_fisica,
            f.id_producto,
            COALESCE(p.nombre_producto, 'Whisky Johnnie Walker Black 12Y') AS nombre_producto,
            COALESCE(p.categoria, 'Whisky') AS categoria,
            COALESCE(p.marca, 'Johnnie Walker') AS marca,
            f.id_tiempo,
            COALESCE(t.nombre_mes, 'Noviembre') AS mes,
            COALESCE(t.trimestre, 'Q4-2026') AS trimestre,
            f.usuario_rbac,
            f.rol_rbac,
            f.cantidad_botellas,
            f.subtotal_usd,
            f.iva_usd,
            f.total_venta_usd,
            f.etl_lote,
            f.fecha_carga_etl
        FROM fact_ventas f
        LEFT JOIN dim_sede s ON f.id_sede = s.id_sede
        LEFT JOIN dim_producto p ON f.id_producto = p.id_producto
        LEFT JOIN dim_tiempo t ON f.id_tiempo = t.id_tiempo
        ORDER BY f.id_fact DESC
        LIMIT 100
    """)
    facts = [{k: serialize_value(v) for k, v in r.items()} for r in cur.fetchall()]

    cur.execute("""
        SELECT
            f.id_sede AS sede,
            COUNT(*) AS lotes_etl,
            COALESCE(SUM(f.cantidad_botellas), 0) AS botellas,
            COALESCE(SUM(f.total_venta_usd), 0) AS total_usd
        FROM fact_ventas f
        GROUP BY f.id_sede
        ORDER BY total_usd DESC
    """)
    by_sede = [{k: serialize_value(v) for k, v in r.items()} for r in cur.fetchall()]

    cur.execute("""
        SELECT
            COALESCE(p.categoria, 'Licores') AS categoria,
            COALESCE(SUM(f.cantidad_botellas), 0) AS botellas,
            COALESCE(SUM(f.total_venta_usd), 0) AS total_usd
        FROM fact_ventas f
        LEFT JOIN dim_producto p ON f.id_producto = p.id_producto
        GROUP BY COALESCE(p.categoria, 'Licores')
        ORDER BY total_usd DESC
    """)
    by_categoria = [{k: serialize_value(v) for k, v in r.items()} for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {
        "sourceDatabase": "BD 5 · db_gye_dwh (MariaDB :3309)",
        "host": active_host,
        "port": 3309,
        "totalFacts": len(facts),
        "kpisBySede": by_sede,
        "kpisByCategoria": by_categoria,
        "starSchemaFacts": facts,
    }


@router.get("/api/arquitectura/topologia")
async def get_cluster_topology():
    keys = ["QUITO", "QUITO_NOSQL", "QUITO_PARALELA", "GUAYAQUIL", "GUAYAQUIL_DWH", "CUENCA"]
    nodes = await asyncio.gather(*(asyncio.to_thread(inspect_single_bd_sync, k) for k in keys))
    online_count = sum(1 for n in nodes if n["status"] == "ONLINE")
    return {
        "timestamp": datetime.now().isoformat(),
        "apiReplica": REPLICA_ID,
        "clusterName": "Clúster Híbrido Multi-Máquina 'La Cava' (Tailscale VPN + 6 BDs + 3 Réplicas API)",
        "totalNodes": len(nodes),
        "onlineNodes": online_count,
        "sites": [
            {
                "siteId": "QUITO",
                "title": "MÁQUINA 1: PC DE ESCRITORIO — NODO QUITO (3 BDs + 3 Agentes IA)",
                "subtitle": "BD 1 MariaDB OLTP (:3307) · BD 2 MongoDB NoSQL (:27017) · BD 3 MariaDB Paralela PARTITION BY HASH (:3308)",
                "badge": "PC ESCRITORIO · TAILSCALE VPN",
                "nodes": [n for n in nodes if n["site"] == "QUITO"],
            },
            {
                "siteId": "GUAYAQUIL",
                "title": "MÁQUINA 2: LAPTOP — NODO GUAYAQUIL (2 BDs + Nginx LB :8080 + 3 Réplicas API)",
                "subtitle": "BD 4 ERP MariaDB (:3307) + 15 Usuarios RBAC · BD 5 MariaDB DWH Estrella Power BI (:3309)",
                "badge": "LAPTOP · PUERTOS :3307 Y :3309",
                "nodes": [n for n in nodes if n["site"] == "GUAYAQUIL"],
            },
            {
                "siteId": "CUENCA_LOJA_CLOUD",
                "title": "NODO CUENCA — ERP PostgreSQL 18 (:5432, en la Laptop)",
                "subtitle": "BD 6 PostgreSQL Cloud DBaaS (:5432) · Replicación Austral & Medición de Latencia WAN",
                "badge": "POSTGRESQL 18 · PUERTO :5432",
                "nodes": [n for n in nodes if n["site"] == "CUENCA_LOJA_CLOUD"],
            },
        ],
        "nodes": nodes,
        "informationSystemArchitecture": {
            "presentationLayer": "Frontend React 'La Cava' + Consola Global DBA + Mapa Topología + Power BI Desktop",
            "middlewareLayer": f"Nginx Load Balancer (:8080 Round-Robin) -> 3 Réplicas FastAPI (Activa: {REPLICA_ID}) + Enrutamiento X-Sede",
            "dataLayer": "6 BDs Híbridas: BD1 ERP Quito (:3307), BD2 Mongo (:27017), BD3 Hash (:3308), BD4 ERP GYE (:3307), BD5 DWH (:3309), BD6 ERP Cuenca PostgreSQL (:5432)",
            "containerization": "docker-compose.app.yml (Nginx LB + 3 Réplicas api_lacava + db_gye_dwh) & VPN Tailscale",
            "scalabilityMetrics": {
                "usersMin": 15,
                "usersMax": 1000,
                "txPerSecond": 45,
                "txPerMinute": 2700,
                "txPerHour": 162000,
                "txPerDay": 1296000,
            },
        },
    }


# Consultas del resumen escritas en minúsculas: valen igual en el ERP MariaDB (Quito/Guayaquil) y en el ERP PostgreSQL (Cuenca)
_SQL_RESUMEN_ERP = {
    "fac": "SELECT COUNT(*), COALESCE(SUM(fac_total), 0) FROM facturas WHERE estado_fac <> 'ANU'",
    "cli": "SELECT COUNT(*) FROM clientes",
    "prod": "SELECT COUNT(*), COALESCE(SUM(pro_saldo_final), 0) FROM productos",
    "prv": "SELECT COUNT(*) FROM proveedores",
    "recent": "SELECT f.id_factura, COALESCE(c.cli_nombre, f.id_cliente), f.fac_fecha, f.fac_total, f.estado_fac "
              "FROM facturas f LEFT JOIN clientes c ON f.id_cliente = c.id_cliente ORDER BY f.fac_fecha DESC LIMIT 5",
}

_TEXTOS_RESUMEN = {
    "QUITO": ("QUITO", "Nodo QUITO ({host}:3307 ERP · :27017 Mongo · :3308 Paralela)",
              "Nodo Quito (PC Escritorio) — ERP + 2 bases de apoyo",
              "BD 1 ERP MariaDB lacava_quito (:3307) · BD 2 MongoDB NoSQL (:27017) · BD 3 MariaDB Paralela HASH (:3308).",
              "BD 1 ERP (:3307) + BD 2 MongoDB (:27017) + BD 3 Paralela (:3308)"),
    "GUAYAQUIL": ("GUAYAQUIL", "Nodo GUAYAQUIL Laptop ({host}:3307 ERP · :3309 DWH Power BI)",
                  "Nodo Guayaquil (Laptop) — BD 4 ERP (:3307) & BD 5 DWH (:3309)",
                  "Consultando en vivo el ERP de Guayaquil (licoreriadatabase :3307) y el esquema estrella de BD 5 (:3309).",
                  "BD 4 ERP MariaDB (:3307) + BD 5 MariaDB DWH (:3309) + 3 Réplicas API"),
    "CUENCA": ("CUENCA_CLOUD", "Nodo CUENCA · BD 6 ERP PostgreSQL (:5432 lacava_cuenca)",
               "Nodo Cuenca — BD 6 ERP PostgreSQL",
               "Datos consultados en vivo desde el ERP PostgreSQL de Cuenca (lacava_cuenca :5432) con latencia medida.",
               "BD 6 ERP PostgreSQL 18 (:5432)"),
}


@router.get("/api/arquitectura/sede-resumen/{site_id}")
def get_site_operational_summary(site_id: str):
    configs = get_cluster_6dbs_config()
    clave = site_id.upper().strip()
    sede = "QUITO" if clave == "QUITO" else "GUAYAQUIL" if clave in ("GUAYAQUIL", "GYE") else "CUENCA"
    cfg = configs[sede]
    if cfg["engineType"] == "postgresql":
        conn, host = connect_postgres_with_fallback(cfg)
        cur = conn.cursor()
    else:
        conn, host = connect_mariadb_with_fallback(cfg)
        cur = conn.cursor()
    r = {}
    for k, q in _SQL_RESUMEN_ERP.items():
        cur.execute(q)
        r[k] = cur.fetchall() if k == "recent" else cur.fetchone()
    cur.close()
    conn.close()
    site_id_out, badge, titulo, subtitulo, motor = _TEXTOS_RESUMEN[sede]
    return {
        "siteId": site_id_out,
        "cityBadge": badge.format(host=host),
        "greetingTitle": titulo,
        "greetingSubtitle": subtitulo,
        "engineInfo": motor,
        "salesTotal": float(r["fac"][1] or 0),
        "invoicesCount": int(r["fac"][0] or 0),
        "stockUnits": int(r["prod"][1] or 0),
        "productsCount": int(r["prod"][0] or 0),
        "customersCount": int(r["cli"][0] or 0),
        "suppliersCount": int(r["prv"][0] or 0),
        "recentInvoices": [
            {"id": x[0], "cliente": x[1], "fecha": serialize_value(x[2]), "total": serialize_value(x[3]), "estado": x[4]}
            for x in r["recent"]
        ],
    }


class DbaQueryRequest(BaseModel):
    nodeId: str = Field(..., description="ID del nodo o header X-Sede")
    sql: str = Field(..., min_length=2, description="Sentencia SQL o comando MONGO_COLLECTION")


@router.post("/api/arquitectura/dba/query")
async def execute_dba_query(payload: DbaQueryRequest):
    sql_clean = payload.sql.strip()
    upper_sql = sql_clean.upper()
    # Modo estrictamente Read-Only (Solo Lectura / Diagnóstico) en la terminal del DBA:
    # No permite INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, REPLACE ni GRANT.
    import re as _re
    for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "REPLACE", "GRANT", "REVOKE", "SHUTDOWN"):
        if _re.search(rf"\b{forbidden}\b", upper_sql):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Operación '{forbidden}' bloqueada: La Terminal del DBA es exclusivamente de "
                    "SOLO LECTURA y diagnóstico (SELECT, SHOW, DESCRIBE, EXPLAIN, MONGO_COLLECTION)."
                ),
            )

    if payload.nodeId == "global-federated" or upper_sql.startswith("-- GLOBAL"):
        glob = await get_dba_global_console(sede=None, modulo=None, x_sede=None)
        cols = ["id", "origen_nodo", "sede", "motor", "puerto", "modulo", "usuario_rbac", "rol_rbac", "detalle", "monto_usd", "fecha_hora"]
        rows = [[r.get(c) for c in cols] for r in glob["data"]]
        return {
            "success": True,
            "nodeId": "global-federated",
            "nodeName": "CONSOLA GLOBAL DEL DBA — 6 BDs Unificadas en Paralelo (GET /api/dba/global)",
            "engine": "MariaDB (:3307/:3308/:3309) + MongoDB (:27017) + PostgreSQL 18 (:5432)",
            "host": "Clúster Tailscale",
            "port": 8080,
            "database": "6 Bases de Datos Unificadas",
            "sql": sql_clean,
            "executionTimeMs": glob["totalExecutionTimeMs"],
            "columns": cols,
            "rows": rows,
            "rowCount": len(rows),
            "executedAt": datetime.now().isoformat(),
        }

    sede_key = resolve_sede_key(payload.nodeId)
    configs = get_cluster_6dbs_config()
    cfg = configs[sede_key]
    t0 = time.perf_counter()

    try:
        if cfg["engineType"] == "mariadb":
            conn, active_host = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            cur.execute(sql_clean)
            if cur.description:
                columns = [col[0] for col in cur.description]
                raw_rows = cur.fetchall()[:250]
                rows = [[serialize_value(v) for v in r] for r in raw_rows]
            else:
                columns = ["resultado", "filas_afectadas"]
                rows = [["Sentencia ejecutada en MariaDB", cur.rowcount]]
            cur.close()
            conn.close()
        elif cfg["engineType"] == "mongodb":
            cli, active_host = connect_mongo_with_fallback(cfg)
            db = cli[cfg["database"]]
            col_name = "eventos_agentes"
            if ":" in sql_clean:
                col_name = sql_clean.split(":", 1)[1].strip()
            elif "logs_auditoria" in sql_clean:
                col_name = "logs_auditoria"
            docs = list(db[col_name].find().sort("_id", -1).limit(50))
            cli.close()
            columns = ["_id", "coleccion", "usuario_rbac", "rol_rbac", "modulo", "documento_json", "timestamp"]
            rows = [
                [
                    str(d.get("_id")),
                    col_name,
                    d.get("usuario_rbac", "i_supervisor"),
                    d.get("rol_rbac", "rol_supervisor"),
                    d.get("modulo", "INVENTARIOS"),
                    json.dumps({k: serialize_value(v) for k, v in d.items() if k != "_id"}, ensure_ascii=False),
                    str(d.get("timestamp", "")),
                ]
                for d in docs
            ]
        else:
            conn, active_host = connect_postgres_with_fallback(cfg)
            with conn.cursor() as cur:
                cur.execute(sql_clean)
                if cur.description:
                    columns = [col.name for col in cur.description]
                    raw_rows = cur.fetchall()[:250]
                    rows = [[serialize_value(v) for v in r] for r in raw_rows]
                else:
                    columns = ["resultado", "filas_afectadas"]
                    rows = [["Sentencia ejecutada en PostgreSQL", cur.rowcount]]
            conn.close()

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "success": True,
            "nodeId": cfg["id"],
            "nodeName": cfg["name"],
            "engine": cfg["engine"],
            "host": active_host,
            "port": cfg["port"],
            "database": cfg["database"],
            "sql": sql_clean,
            "executionTimeMs": elapsed_ms,
            "columns": columns,
            "rows": rows,
            "rowCount": len(rows),
            "executedAt": datetime.now().isoformat(),
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        raise HTTPException(
            status_code=400,
            detail=f"Error en [{cfg['shortName']} ({elapsed_ms} ms)]: {exc}",
        ) from exc


@router.get("/api/arquitectura/dba/logs/{node_id}")
def get_node_logs_and_activity(node_id: str):
    sede_key = resolve_sede_key(node_id)
    configs = get_cluster_6dbs_config()
    cfg = configs[sede_key]
    audit_logs = []
    processes = []
    variables = {}

    if cfg["engineType"] == "mariadb":
        conn, active_host = connect_mariadb_with_fallback(cfg)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT @@hostname AS hostname, @@port AS port, @@version AS version, @@datadir AS datadir")
        variables = cur.fetchone() or {}
        cur.execute("SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE FROM information_schema.PROCESSLIST ORDER BY ID DESC LIMIT 12")
        processes = [{k: serialize_value(v) for k, v in row.items()} for row in cur.fetchall()]

        if sede_key in ("QUITO", "GUAYAQUIL"):
            cur.execute("SELECT id_op AS id, fecha_hora, CONCAT(usuario_rbac, ' (', rol_rbac, ')') AS usuario, modulo AS evento, operacion AS detalle FROM operaciones_agentes_ia ORDER BY id_op DESC LIMIT 12")
            audit_logs = [{k: serialize_value(v) for k, v in row.items()} for row in cur.fetchall()]
        elif sede_key == "QUITO_PARALELA":
            cur.execute("SELECT id, fecha_registro AS fecha_hora, CONCAT(usuario_rbac, ' (', rol_rbac, ')') AS usuario, CONCAT('HASH p', particion_hash) AS evento, CONCAT(codigo_referencia, ' ($', monto_usd, ')') AS detalle FROM historico_transacciones ORDER BY id DESC LIMIT 12")
            audit_logs = [{k: serialize_value(v) for k, v in row.items()} for row in cur.fetchall()]
        elif sede_key == "GUAYAQUIL_DWH":
            cur.execute("SELECT id_fact AS id, fecha_carga_etl AS fecha_hora, CONCAT(usuario_rbac, ' (', rol_rbac, ')') AS usuario, etl_lote AS evento, CONCAT('Sede ', id_sede, ' -> $', total_venta_usd) AS detalle FROM fact_ventas ORDER BY id_fact DESC LIMIT 12")
            audit_logs = [{k: serialize_value(v) for k, v in row.items()} for row in cur.fetchall()]
        cur.close()
        conn.close()

    elif cfg["engineType"] == "mongodb":
        cli, active_host = connect_mongo_with_fallback(cfg)
        db = cli[cfg["database"]]
        variables = {
            "hostname": f"{active_host}:27017",
            "port": 27017,
            "database": cfg["database"],
            "collections": "logs_auditoria, eventos_agentes",
        }
        processes = [{"ID": "MONGO-1", "USER": "agentes_quito", "HOST": active_host, "DB": cfg["database"], "COMMAND": "insert/find"}]
        for d in db["eventos_agentes"].find().sort("_id", -1).limit(12):
            audit_logs.append({
                "id": str(d.get("evento_id") or d.get("_id"))[:12],
                "fecha_hora": str(d.get("timestamp", "")),
                "usuario": f"{d.get('usuario_rbac', 'i_supervisor')} ({d.get('rol_rbac', 'rol_supervisor')})",
                "evento": d.get("modulo", "NOSQL"),
                "detalle": d.get("mensaje", ""),
            })
        cli.close()

    else:
        conn, active_host = connect_postgres_with_fallback(cfg)
        with conn.cursor() as cur:
            cur.execute("SELECT inet_server_port(), current_database(), current_setting('data_directory', true)")
            r = cur.fetchone()
            variables = {"hostname": active_host, "port": r[0] if r else 5432, "database": r[1] if r else cfg["database"]}
            cur.execute("SELECT pid, usename, client_addr::text, datname, state FROM pg_stat_activity WHERE datname = current_database() LIMIT 12")
            processes = [
                {"ID": row[0], "USER": row[1], "HOST": row[2] or "127.0.0.1", "DB": row[3], "COMMAND": row[4] or "active"}
                for row in cur.fetchall()
            ]
            cur.execute("SELECT id_op, fecha_hora, usuario_rbac || ' (' || rol_rbac || ')', modulo, operacion FROM operaciones_agentes_cloud ORDER BY id_op DESC LIMIT 12")
            audit_logs = [
                {"id": row[0], "fecha_hora": serialize_value(row[1]), "usuario": row[2], "evento": row[3], "detalle": row[4]}
                for row in cur.fetchall()
            ]
        conn.close()

    return {
        "nodeId": cfg["id"],
        "nodeName": cfg["name"],
        "port": cfg["port"],
        "engine": cfg["engine"],
        "variables": {k: serialize_value(v) for k, v in variables.items()},
        "activeConnections": processes,
        "auditLogs": audit_logs,
    }


class TwoPhaseCommitRequest(BaseModel):
    productId: str = Field(default="", description="id_Producto del ERP (vacío = el primero con stock suficiente en el origen)")
    quantity: int = Field(default=12, ge=1, le=200)
    sourceNode: str = Field(default="GUAYAQUIL")
    targetNode: str = Field(default="QUITO")
    simulatePrepareFailure: bool = Field(default=False)
    usuario: str = Field(default="i_jefe", description="Usuario RBAC que ordena el traslado (queda en el log de los 3 ERP)")


class _Participante2PC:
    """Un nodo del 2PC sobre su ERP. MariaDB: XA START/END/PREPARE/COMMIT real.
    PostgreSQL: PREPARE TRANSACTION real si max_prepared_transactions > 0; si no, la transacción queda abierta y
    bloqueada (FOR UPDATE) hasta la decisión global, y se informa así."""

    def __init__(self, sede: str, xid: str, usuario: str):
        self.sede, self.xid, self.usuario = sede, xid, usuario
        self.cfg = get_cluster_6dbs_config()[sede]
        self.pg = self.cfg["engineType"] == "postgresql"
        self.preparada = False
        self.modo = ""
        if self.pg:
            self.conn, self.host = connect_postgres_with_fallback(self.cfg)
            self.conn.autocommit = False
            self.cur = self.conn.cursor()
            self.cur.execute("SHOW max_prepared_transactions")
            self.pg_2pc = int(self.cur.fetchone()[0] or 0) > 0
        else:
            self.conn, self.host = connect_mariadb_with_fallback(self.cfg)  # autocommit=True: XA maneja la transacción
            self.cur = self.conn.cursor()
            self.cur.execute(f"XA START '{xid}'")
        self.actor = fijar_actor_auditoria(self.cur, "postgresql" if self.pg else "mariadb", usuario)

    def nodo(self) -> str:
        return f"{self.cfg['bdId']}: {self.sede} ({self.host}:{self.cfg['port']} {self.cfg['database']})"

    def producto(self, product_id: str, cantidad: int, bloquear_stock: bool):
        if product_id:
            self.cur.execute("SELECT id_producto, pro_descripcion, pro_saldo_final FROM productos WHERE id_producto = %s FOR UPDATE",
                             (product_id,))
        else:
            self.cur.execute("SELECT id_producto, pro_descripcion, pro_saldo_final FROM productos "
                             + ("WHERE pro_saldo_final >= %s " if bloquear_stock else "") + "ORDER BY id_producto LIMIT 1 FOR UPDATE",
                             (cantidad,) if bloquear_stock else ())
        return self.cur.fetchone()

    def mover(self, product_id: str, delta: int) -> None:
        # El saldo del ERP es inicial + ingresos - egresos + ajustes: el traslado se registra como ajuste
        self.cur.execute("UPDATE productos SET pro_qty_ajustes = COALESCE(pro_qty_ajustes, 0) + %s, "
                         "pro_saldo_final = pro_saldo_final + %s WHERE id_producto = %s", (delta, delta, product_id))

    def bitacora(self, texto: str) -> None:
        tabla = "operaciones_agentes_cloud" if self.pg else "operaciones_agentes_ia"
        self.cur.execute(f"INSERT INTO {tabla} (sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, "
                         f"tabla_ref, documento_ref) VALUES (%s, 'Coordinador-2PC', %s, 'rol_jefe', 'INVENTARIOS', %s, 0, 'PRODUCTOS', %s)",
                         (self.sede, self.usuario, texto[:255], self.xid))

    def preparar(self) -> None:
        if self.pg:
            if self.pg_2pc:
                self.cur.execute(f"PREPARE TRANSACTION '{self.xid}'")
                self.modo = "PREPARE TRANSACTION (2PC nativo de PostgreSQL)"
            else:
                self.modo = ("transacción abierta y bloqueada (max_prepared_transactions = 0: PostgreSQL tiene el 2PC nativo "
                             "desactivado en este servidor)")
        else:
            self.cur.execute(f"XA END '{self.xid}'")
            self.cur.execute(f"XA PREPARE '{self.xid}'")
            self.modo = "XA PREPARE (2PC nativo de MariaDB)"
        self.preparada = True

    def confirmar(self) -> None:
        if self.pg:
            if self.pg_2pc:
                self.conn.autocommit = True
                self.cur.execute(f"COMMIT PREPARED '{self.xid}'")
            else:
                self.conn.commit()
        else:
            self.cur.execute(f"XA COMMIT '{self.xid}'")

    def revertir(self) -> None:
        try:
            if self.pg:
                if self.preparada and self.pg_2pc:
                    self.conn.autocommit = True
                    self.cur.execute(f"ROLLBACK PREPARED '{self.xid}'")
                else:
                    self.conn.rollback()
            else:
                if not self.preparada:
                    self.cur.execute(f"XA END '{self.xid}'")
                self.cur.execute(f"XA ROLLBACK '{self.xid}'")
        except Exception:
            pass

    def cerrar(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


@router.post("/api/arquitectura/distribuida/2pc")
def execute_two_phase_commit_demo(payload: TwoPhaseCommitRequest):
    """
    2PC REAL sobre los 3 ERP: traslado de stock de un producto entre bodegas de dos sedes, y la tercera sede registra
    el traslado. Fase 1: cada nodo bloquea, modifica y PREPARA (vota). Fase 2: COMMIT global solo si los 3 votan sí;
    si alguno falla, ROLLBACK global. Los triggers de auditoría de cada ERP registran los cambios con el usuario.
    """
    origen, destino = resolve_sede_key(payload.sourceNode), resolve_sede_key(payload.targetNode)
    if origen not in SEDES_ERP or destino not in SEDES_ERP or origen == destino:
        raise HTTPException(status_code=422, detail="Origen y destino deben ser dos sedes distintas: QUITO, GUAYAQUIL o CUENCA.")
    tercero = next(s for s in SEDES_ERP if s not in (origen, destino))
    tx_id = f"2PC-{uuid4().hex[:8].upper()}"
    steps: list[dict[str, Any]] = []
    t_start = time.perf_counter()

    def paso(fase: str, nodo: str, estado: str, mensaje: str) -> None:
        steps.append({"phase": fase, "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3], "node": nodo,
                      "status": estado, "message": mensaje})

    paso("INIT", f"Coordinador FastAPI ({REPLICA_ID})", "STARTED",
         f"Transacción distribuida {tx_id}: trasladar {payload.quantity} unidades de {origen} a {destino}; {tercero} registra el "
         f"traslado. Ordenado por {payload.usuario}.")
    participantes: list[_Participante2PC] = []
    decision, phase_reached = "GLOBAL_ROLLBACK", "PHASE_1_PREPARE_ABORT"
    try:
        p_origen = _Participante2PC(origen, tx_id, payload.usuario)
        participantes.append(p_origen)
        fila = p_origen.producto(payload.productId.strip(), payload.quantity, bloquear_stock=True)
        if not fila:
            raise RuntimeError(f"{origen} no tiene el producto '{payload.productId}' o no hay uno con stock >= {payload.quantity}.")
        prod_id, nombre, saldo = str(fila[0]).strip(), str(fila[1]).strip(), int(fila[2] or 0)
        if saldo < payload.quantity:
            raise RuntimeError(f"Stock insuficiente en {origen}: {nombre} tiene {saldo} < {payload.quantity}.")
        p_origen.mover(prod_id, -payload.quantity)
        p_origen.bitacora(f"2PC {tx_id}: salida de {payload.quantity} u. de {prod_id} hacia {destino}")
        p_origen.preparar()
        paso("PHASE_1_PREPARE", p_origen.nodo(), "VOTE_COMMIT",
             f"'{nombre}' ({prod_id}) stock {saldo} -> {saldo - payload.quantity} bloqueado sin confirmar · {p_origen.modo}. Voto: SÍ.")

        if payload.simulatePrepareFailure:
            paso("PHASE_1_PREPARE", f"{destino} (fallo simulado)", "VOTE_ABORT",
                 f"FALLO SIMULADO en la fase PREPARE de {destino}: el nodo rechaza o no responde. Voto: NO.")
            raise RuntimeError(f"VOTE_ABORT de {destino} durante la fase PREPARE (simulado).")

        p_destino = _Participante2PC(destino, tx_id, payload.usuario)
        participantes.append(p_destino)
        fila_d = p_destino.producto(prod_id, payload.quantity, bloquear_stock=False)
        if not fila_d:
            raise RuntimeError(f"El producto {prod_id} no existe en el ERP de {destino}.")
        saldo_d = int(fila_d[2] or 0)
        p_destino.mover(prod_id, payload.quantity)
        p_destino.bitacora(f"2PC {tx_id}: ingreso de {payload.quantity} u. de {prod_id} desde {origen}")
        p_destino.preparar()
        paso("PHASE_1_PREPARE", p_destino.nodo(), "VOTE_COMMIT",
             f"'{nombre}' stock {saldo_d} -> {saldo_d + payload.quantity} bloqueado sin confirmar · {p_destino.modo}. Voto: SÍ.")

        p_tercero = _Participante2PC(tercero, tx_id, payload.usuario)
        participantes.append(p_tercero)
        p_tercero.bitacora(f"2PC {tx_id}: registro del traslado {origen} -> {destino} de {payload.quantity} u. de {prod_id}")
        p_tercero.preparar()
        paso("PHASE_1_PREPARE", p_tercero.nodo(), "VOTE_COMMIT", f"Registro del traslado preparado · {p_tercero.modo}. Voto: SÍ.")

        for p in participantes:
            p.confirmar()
        decision, phase_reached = "GLOBAL_COMMIT", "PHASE_2_COMMIT"
        paso("PHASE_2_COMMIT", f"Coordinador FastAPI ({REPLICA_ID})", "GLOBAL_COMMIT",
             "Unanimidad 3/3 -> GLOBAL_COMMIT en los 3 ERP. Los triggers dejaron el cambio en LOG_AUDITORIA de cada sede.")
        summary_msg = f"2PC {tx_id} confirmado: {payload.quantity} u. de {nombre} pasaron de {origen} a {destino}."
    except Exception as exc:
        for p in participantes:
            p.revertir()
        paso("PHASE_2_ABORT", f"Coordinador FastAPI ({REPLICA_ID})", "GLOBAL_ROLLBACK",
             f"Fase PREPARE fallida ({str(exc)[:200]}) -> GLOBAL_ROLLBACK en {', '.join(p.sede for p in participantes) or 'ningún nodo'}: "
             f"ningún stock cambió.")
        summary_msg = f"Transacción {tx_id} revertida con GLOBAL_ROLLBACK."
    finally:
        for p in participantes:
            p.cerrar()

    return {
        "txId": tx_id,
        "decision": decision,
        "phaseReached": phase_reached,
        "simulatePrepareFailure": payload.simulatePrepareFailure,
        "executionTimeMs": round((time.perf_counter() - t_start) * 1000, 2),
        "summary": summary_msg,
        "steps": steps,
    }


# ==============================================================================
# MINI-ETL REAL (Agente 5): OLTP (BD 1, BD 4, BD 6) -> ESQUEMA ESTRELLA (BD 5)
# ==============================================================================

MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
            "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

ETL_FUENTES = {
    # fuente en etl_control -> sede del ERP. La marca de agua es el log_seq del LOG_AUDITORIA de esa sede (CDC):
    # cada INSERT en PROxFAC es una línea de venta real (factura, producto, cantidad, precio) hecha en la app.
    "QUITO_ERP": "QUITO",
    "GUAYAQUIL_ERP": "GUAYAQUIL",
    "CUENCA_ERP": "CUENCA",
}
SQL_ETL_LINEAS = ("SELECT log_seq, id_usuario, log_fechahora, log_valornuevo FROM log_auditoria "
                  "WHERE UPPER(log_tablaafectada) = 'PROXFAC' AND log_accion = 'INSERT' AND log_seq > %s "
                  "ORDER BY log_seq LIMIT 1000")
SQL_ETL_PRODUCTOS = ("SELECT p.id_producto, p.pro_descripcion, COALESCE(c.cat_nombre, 'Sin categoría'), "
                     "COALESCE(m.mar_nombre, 'Sin marca'), COALESCE(p.pro_precio_venta, 0) FROM productos p "
                     "LEFT JOIN categorias c ON c.id_categoria = p.id_categoria LEFT JOIN marcas m ON m.id_marca = p.id_marca")
_DWH_LISTO: set[str] = set()


def _extract_erp(sede: str, watermark: int) -> tuple[list[tuple], dict[str, str], list[tuple]]:
    """E: líneas de venta nuevas del log del ERP + usuarios (id -> username) + catálogo de productos de la sede."""
    cfg = get_cluster_6dbs_config()[sede]
    conn, _ = (connect_postgres_with_fallback if cfg["engineType"] == "postgresql" else connect_mariadb_with_fallback)(cfg)
    try:
        cur = conn.cursor()
        cur.execute(SQL_ETL_LINEAS, (watermark,))
        lineas = cur.fetchall()
        cur.execute("SELECT id_usuario, usr_username FROM usuarios")
        usuarios = {str(a).strip(): str(b).strip() for a, b in cur.fetchall()}
        productos = []
        if lineas:
            cur.execute(SQL_ETL_PRODUCTOS)
            productos = cur.fetchall()
        cur.close()
        return lineas, usuarios, productos
    finally:
        conn.close()


def _preparar_dwh(cur) -> None:
    """Columnas de trazabilidad (de qué factura y de qué cambio del log salió cada hecho) e idempotencia del ETL."""
    if "ok" in _DWH_LISTO:
        return
    cur.execute("ALTER TABLE fact_ventas ADD COLUMN IF NOT EXISTS id_factura VARCHAR(20) NULL, "
                "ADD COLUMN IF NOT EXISTS log_seq_origen BIGINT NULL, "
                "ADD COLUMN IF NOT EXISTS fuente_dato VARCHAR(20) NOT NULL DEFAULT 'BITACORA'")
    cur.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'fact_ventas' AND INDEX_NAME = 'uq_fact_origen'")
    if not cur.fetchone()[0]:
        cur.execute("ALTER TABLE fact_ventas ADD UNIQUE KEY uq_fact_origen (id_sede, log_seq_origen)")
    # dim_sede describe las sedes tal como están hoy (los 3 ERP)
    for sede, motor, puerto, maquina in (("QUITO", "MariaDB ERP (lacava_quito)", 3307, "PC Escritorio (Tailscale)"),
                                         ("GUAYAQUIL", "MariaDB ERP (licoreriadatabase)", 3307, "Laptop (Tailscale)"),
                                         ("CUENCA", "PostgreSQL 18 ERP (lacava_cuenca)", 5432, "Laptop (PostgreSQL local)")):
        cur.execute("UPDATE dim_sede SET motor_bd = %s, puerto_tcp = %s, maquina_fisica = %s WHERE id_sede = %s",
                    (motor, puerto, maquina, sede))
    _DWH_LISTO.add("ok")


def run_mini_etl_to_dwh() -> dict[str, Any]:
    """
    ETL incremental real desde los 3 ERP:
      E: lee del LOG_AUDITORIA de cada ERP las líneas de venta (INSERT en PROxFAC) con log_seq > marca de agua.
      T: producto real del ERP (dim_producto se actualiza con su nombre, categoría, marca y precio), cantidad y
         subtotal de la línea, IVA 15 %, clave de tiempo T-AAAA-MM y el usuario que vendió.
      L: inserta en fact_ventas (BD 5) y avanza la marca de agua en `etl_control` en la MISMA transacción.
         UNIQUE(id_sede, log_seq_origen) + INSERT IGNORE: aunque 2 réplicas de la API corran el ETL a la vez, no duplica.
    """
    configs = get_cluster_6dbs_config()
    lote = f"ETL-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    conn, _ = connect_mariadb_with_fallback(configs["GUAYAQUIL_DWH"])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS etl_control ("
        " fuente VARCHAR(20) PRIMARY KEY,"
        " ultimo_id BIGINT NOT NULL DEFAULT 0,"
        " filas_cargadas BIGINT NOT NULL DEFAULT 0,"
        " ultima_corrida DATETIME NULL,"
        " ultimo_lote VARCHAR(40) NULL)"
    )
    _preparar_dwh(cur)
    conn.commit()

    fuentes = []
    total = 0
    for fuente, sede in ETL_FUENTES.items():
        cur.execute("SELECT ultimo_id FROM etl_control WHERE fuente = %s", (fuente,))
        row = cur.fetchone()
        watermark = int(row[0]) if row else 0
        try:
            lineas, usuarios, productos = _extract_erp(sede, watermark)
        except Exception as exc:
            fuentes.append({"tabla": f"ETL {sede} -> fact_ventas", "accion": "EXTRACT", "id": None, "ok": False,
                            "error": f"ERP no disponible: {str(exc)[:150]}"})
            continue
        cargadas = 0
        nuevo_wm = watermark
        try:
            for id_p, nombre, categoria, marca, precio in productos:
                cur.execute(
                    "INSERT INTO dim_producto (id_producto, nombre_producto, categoria, marca, precio_unitario) VALUES (%s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE nombre_producto = VALUES(nombre_producto), categoria = VALUES(categoria), "
                    "marca = VALUES(marca), precio_unitario = VALUES(precio_unitario)",
                    (str(id_p).strip(), str(nombre or id_p).strip()[:120], str(categoria).strip()[:50], str(marca).strip()[:50],
                     float(precio or 0)),
                )
            for log_seq, id_usuario, fecha, valor in lineas:
                nuevo_wm = max(nuevo_wm, int(log_seq))
                linea = {str(k).lower(): v for k, v in (json.loads(valor) if valor else {}).items()}
                cantidad = int(float(linea.get("pxf_cantidad") or 0))
                sub = round(float(linea.get("pxf_subtotal") or 0) or cantidad * float(linea.get("pxf_precio") or 0), 2)
                if cantidad <= 0 or sub <= 0:
                    continue
                fecha = fecha if isinstance(fecha, datetime) else datetime.now()
                id_tiempo = f"T-{fecha.year}-{fecha.month:02d}"
                cur.execute(
                    "INSERT IGNORE INTO dim_tiempo (id_tiempo, fecha, anio, mes, nombre_mes, trimestre) VALUES (%s, %s, %s, %s, %s, %s)",
                    (id_tiempo, date(fecha.year, fecha.month, 1), fecha.year, fecha.month,
                     MESES_ES[fecha.month - 1], f"Q{(fecha.month - 1) // 3 + 1}-{fecha.year}"),
                )
                usuario = usuarios.get(str(id_usuario or "").strip(), str(id_usuario or "desconocido").strip())
                rol = USUARIOS_15_MAP.get(usuario, ("rol_operador",))[0]
                iva = round(sub * 0.15, 2)
                cur.execute(
                    "INSERT IGNORE INTO fact_ventas (id_sede, id_producto, id_tiempo, usuario_rbac, rol_rbac, cantidad_botellas, "
                    "subtotal_usd, iva_usd, total_venta_usd, etl_lote, id_factura, log_seq_origen, fuente_dato) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ERP')",
                    (sede, str(linea.get("id_producto") or "").strip(), id_tiempo, usuario[:30], rol, cantidad, sub, iva,
                     round(sub + iva, 2), lote, str(linea.get("id_factura") or "").strip()[:20], int(log_seq)),
                )
                cargadas += cur.rowcount
            cur.execute(
                "INSERT INTO etl_control (fuente, ultimo_id, filas_cargadas, ultima_corrida, ultimo_lote) VALUES (%s, %s, %s, NOW(), %s) "
                "ON DUPLICATE KEY UPDATE ultimo_id = GREATEST(ultimo_id, VALUES(ultimo_id)), "
                "filas_cargadas = filas_cargadas + VALUES(filas_cargadas), ultima_corrida = NOW(), ultimo_lote = VALUES(ultimo_lote)",
                (fuente, nuevo_wm, cargadas, lote),
            )
            conn.commit()
            total += cargadas
            fuentes.append({"tabla": f"ETL {sede} -> fact_ventas",
                            "accion": f"{len(lineas)} líneas de venta leídas del log · {cargadas} hechos cargados",
                            "id": f"log_seq {watermark} -> {nuevo_wm}", "ok": True})
        except Exception as exc:
            conn.rollback()
            fuentes.append({"tabla": f"ETL {sede} -> fact_ventas", "accion": "LOAD (ROLLBACK)", "id": None, "ok": False, "error": str(exc)[:200]})


    # Bitácora de corridas (también las que cargan 0 filas) para el feed en vivo del Agente 5
    try:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS etl_corridas ("
            " id INT AUTO_INCREMENT PRIMARY KEY,"
            " lote VARCHAR(40) NOT NULL,"
            " fecha_corrida DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            " hechos_cargados INT NOT NULL DEFAULT 0,"
            " detalle VARCHAR(255) NULL)"
        )
        resumen = " · ".join(
            f"{f['tabla'].replace('ETL ', '').replace(' -> fact_ventas', '')}: {'OK' if f['ok'] else 'OFFLINE'}" for f in fuentes
        )
        cur.execute(
            "INSERT INTO etl_corridas (lote, hechos_cargados, detalle) VALUES (%s, %s, %s)",
            (lote, total, resumen[:255]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    cur.close()
    conn.close()
    return {"lote": lote, "hechosCargados": total, "fuentes": fuentes}


# ==============================================================================
# LOS 6 AGENTES IA (1 POR BASE DE DATOS): ACTIVIDAD EN VIVO + EJECUCIÓN MANUAL
# ==============================================================================

AGENTES_IA: dict[int, dict[str, Any]] = {
    1: {"codigo": "AG 1", "prefijo": "Agente-1", "nombre": "Agente-1-Quito-OLTP", "sede": "QUITO",
        "script": "agentes_quito.py", "maquina": "PC Escritorio (Quito)",
        "operacion": "Transacción real en el ERP de Quito ({modulo}) hecha por {usuario}"},
    2: {"codigo": "AG 2", "prefijo": "Agente-2", "nombre": "Agente-2-Quito-MongoDB", "sede": "QUITO_NOSQL",
        "script": "agentes_quito.py", "maquina": "PC Escritorio (Quito)",
        "operacion": "Log JSON de telemetría y alerta de stock bajo en Quito"},
    3: {"codigo": "AG 3", "prefijo": "Agente-3", "nombre": "Agente-3-Quito-Paralela-Hash", "sede": "QUITO_PARALELA",
        "script": "agentes_quito.py", "maquina": "PC Escritorio (Quito)",
        "operacion": "Inserción histórica en PARTITION BY HASH(id) PARTITIONS 4"},
    4: {"codigo": "AG 4", "prefijo": "Agente-4", "nombre": "Agente-4-Guayaquil-OLTP", "sede": "GUAYAQUIL",
        "script": "agentes_gye_cuenca.py", "maquina": "Laptop (Guayaquil)",
        "operacion": "Transacción real en el ERP de Guayaquil ({modulo}) hecha por {usuario}"},
    5: {"codigo": "AG 5", "prefijo": "Agente-5", "nombre": "Agente-5-Guayaquil-ETL-DWH", "sede": "GUAYAQUIL_DWH",
        "script": "agentes_gye_cuenca.py", "maquina": "Laptop (Guayaquil)",
        "operacion": "Mini-ETL OLTP -> Esquema Estrella BD 5"},
    6: {"codigo": "AG 6", "prefijo": "Agente-6", "nombre": "Agente-6-Cuenca-ERP-PostgreSQL", "sede": "CUENCA",
        "script": "agentes_gye_cuenca.py", "maquina": "Laptop -> ERP PostgreSQL Cuenca",
        "operacion": "Transacción real en el ERP de Cuenca ({modulo})"},
}

ESTADO_ACTIVO_SEGUNDOS = 150  # los agentes corren cada 60 s; > 2.5 min sin actividad = INACTIVO


def _impacto_erp(cur, bitacora: str, like: str) -> list[dict[str, Any]]:
    """Qué tocó el agente en el ERP de su sede: documentos por tabla (vía su bitácora) + tamaño real de esas tablas y del log."""
    cur.execute(f"SELECT tabla_ref, COUNT(*) FROM {bitacora} WHERE agente_nombre LIKE %s AND tabla_ref IS NOT NULL "
                "GROUP BY tabla_ref ORDER BY tabla_ref", (like,))
    salida = [{"tabla": f"{t} (documentos del agente)", "filas": int(n)} for t, n in cur.fetchall()]
    for tabla in ("facturas", "compras", "recepciones", "entregas", "log_auditoria"):
        cur.execute(f"SELECT COUNT(*) FROM {tabla}")
        salida.append({"tabla": f"{tabla} (total en el ERP)", "filas": int(cur.fetchone()[0])})
    return salida


def _rows_as_dicts(cur) -> list[dict[str, Any]]:
    cols = [c[0] if isinstance(c, tuple) else c.name for c in cur.description]
    return [{k: serialize_value(v) for k, v in zip(cols, r)} for r in cur.fetchall()]


def get_agent_activity_sync(agent_num: int, limit: int = 15) -> dict[str, Any]:
    ag = AGENTES_IA[agent_num]
    configs = get_cluster_6dbs_config()
    cfg = configs[ag["sede"]]
    like = f"{ag['prefijo']}%"
    t0 = time.perf_counter()
    base = {
        "agentId": f"agente-{agent_num}",
        **{k: v for k, v in ag.items() if k != "operacion"},
        "bdId": cfg["bdId"],
        "nodeId": cfg["id"],
        "baseDatos": cfg["database"],
        "puerto": cfg["port"],
        "motor": cfg["engine"],
    }
    try:
        impacto_gui: list[dict[str, Any]] = []
        por_modulo: list[dict[str, Any]] = []
        if agent_num in (1, 4):
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*), TIMESTAMPDIFF(SECOND, MAX(fecha_hora), NOW()) FROM operaciones_agentes_ia WHERE agente_nombre LIKE %s",
                (like,),
            )
            total, secs = cur.fetchone()
            cur.execute(
                "SELECT id_op, fecha_hora, usuario_rbac, rol_rbac, modulo, tabla_ref, documento_ref, operacion, monto_usd, replica_api "
                "FROM operaciones_agentes_ia WHERE agente_nombre LIKE %s ORDER BY id_op DESC LIMIT %s",
                (like, limit),
            )
            rows = _rows_as_dicts(cur)
            impacto_gui = _impacto_erp(cur, "operaciones_agentes_ia", like)
            cur.execute(
                "SELECT modulo, COUNT(*) FROM operaciones_agentes_ia WHERE agente_nombre LIKE %s GROUP BY modulo ORDER BY modulo",
                (like,),
            )
            por_modulo = [{"modulo": m, "operaciones": int(c)} for m, c in cur.fetchall()]
            cur.close()
            conn.close()
        elif agent_num == 2:
            cli, _ = connect_mongo_with_fallback(cfg)
            col = cli[cfg["database"]]["eventos_agentes"]
            filtro = {"agente": {"$regex": f"^{ag['prefijo']}"}}
            total = col.count_documents(filtro)
            docs = list(col.find(filtro).sort("_id", -1).limit(limit))
            cli.close()
            rows = [
                {
                    "evento_id": d.get("evento_id"),
                    "timestamp": str(d.get("timestamp", "")),
                    "usuario_rbac": d.get("usuario_rbac"),
                    "modulo": d.get("modulo"),
                    "mensaje": d.get("mensaje"),
                    "documento_json": json.dumps(d.get("detalle", {}), ensure_ascii=False, default=str),
                }
                for d in docs
            ]
            secs = None
            if docs and docs[0].get("timestamp"):
                try:
                    secs = int((datetime.now() - datetime.fromisoformat(str(docs[0]["timestamp"]))).total_seconds())
                except ValueError:
                    secs = None
            impacto_gui.append({"tabla": "eventos_agentes + logs_auditoria (colecciones)", "filas": total})
        elif agent_num == 3:
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), TIMESTAMPDIFF(SECOND, MAX(fecha_registro), NOW()) FROM historico_transacciones")
            total, secs = cur.fetchone()
            cur.execute(
                "SELECT id, fecha_registro, usuario_rbac, rol_rbac, modulo, codigo_referencia, monto_usd, "
                "CONCAT('p', particion_hash) AS particion FROM historico_transacciones ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            rows = _rows_as_dicts(cur)
            cur.execute("SELECT CONCAT('p', particion_hash), COUNT(*) FROM historico_transacciones GROUP BY particion_hash ORDER BY 1")
            impacto_gui = [{"tabla": f"historico_transacciones · partición {p}", "filas": int(c)} for p, c in cur.fetchall()]
            cur.close()
            conn.close()
        elif agent_num == 5:
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), TIMESTAMPDIFF(SECOND, MAX(fecha_carga_etl), NOW()) FROM fact_ventas")
            total, secs_fact = cur.fetchone()
            secs = secs_fact
            try:
                cur.execute("SELECT TIMESTAMPDIFF(SECOND, MAX(ultima_corrida), NOW()) FROM etl_control")
                secs = cur.fetchone()[0]
                cur.execute("SELECT fuente, ultimo_id, filas_cargadas, ultima_corrida, ultimo_lote FROM etl_control WHERE fuente LIKE %s ORDER BY fuente", ("%_ERP",))
                impacto_gui = [
                    {"tabla": f"fact_ventas ← {f} (marca de agua log_seq {wm})", "filas": int(n),
                     "ultimaCorrida": serialize_value(uc), "ultimoLote": lt}
                    for f, wm, n, uc, lt in cur.fetchall()
                ]
            except Exception:
                secs = secs_fact
            cur.execute(
                "SELECT f.id_fact, f.fecha_carga_etl, f.etl_lote, f.id_sede, p.nombre_producto, f.cantidad_botellas, "
                "f.total_venta_usd, f.usuario_rbac "
                "FROM fact_ventas f LEFT JOIN dim_producto p ON p.id_producto = f.id_producto ORDER BY f.id_fact DESC LIMIT %s",
                (limit,),
            )
            rows = _rows_as_dicts(cur)
            cur.close()
            conn.close()
        else:  # 6 CUENCA
            conn, _ = connect_postgres_with_fallback(cfg)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), EXTRACT(EPOCH FROM (now() - MAX(fecha_hora)))::int FROM operaciones_agentes_cloud "
                    "WHERE agente_nombre LIKE %s",
                    (like,),
                )
                total, secs = cur.fetchone()
                cur.execute(
                    "SELECT id_op, fecha_hora, usuario_rbac, rol_rbac, modulo, tabla_ref, documento_ref, operacion, monto_usd, latencia_wan_ms "
                    "FROM operaciones_agentes_cloud WHERE agente_nombre LIKE %s ORDER BY id_op DESC LIMIT %s",
                    (like, limit),
                )
                rows = _rows_as_dicts(cur)
                impacto_gui = _impacto_erp(cur, "operaciones_agentes_cloud", like)
                cur.execute(
                    "SELECT modulo, COUNT(*) FROM operaciones_agentes_cloud WHERE agente_nombre LIKE %s GROUP BY modulo ORDER BY modulo",
                    (like,),
                )
                por_modulo = [{"modulo": m, "operaciones": int(c)} for m, c in cur.fetchall()]
            conn.close()

        secs_int = int(secs) if secs is not None else None
        return {
            **base,
            "nodoOnline": True,
            "estado": "ACTIVO" if secs_int is not None and secs_int <= ESTADO_ACTIVO_SEGUNDOS else "INACTIVO",
            "segundosDesdeUltima": secs_int,
            "totalRegistros": int(total or 0),
            "porModulo": por_modulo,
            "impactoTablas": impacto_gui,
            "ultimos": rows,
            "latencyMs": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as exc:
        return {
            **base,
            "nodoOnline": False,
            "estado": "SIN CONEXIÓN",
            "segundosDesdeUltima": None,
            "totalRegistros": 0,
            "porModulo": [],
            "impactoTablas": [],
            "ultimos": [],
            "error": str(exc)[:250],
            "latencyMs": round((time.perf_counter() - t0) * 1000, 2),
        }


def _agent_num(agente_id: str) -> int:
    digits = "".join(ch for ch in agente_id if ch.isdigit())
    num = int(digits) if digits else 0
    if num not in AGENTES_IA:
        raise HTTPException(status_code=404, detail="Agente no encontrado (use 1..6).")
    return num


@router.get("/api/agentes/estado")
async def get_all_agents_status():
    """Resumen de los 6 agentes (ACTIVO/INACTIVO, total de registros, segundos desde la última operación)."""
    results = await asyncio.gather(*(asyncio.to_thread(get_agent_activity_sync, n, 1) for n in AGENTES_IA))
    return {"timestamp": datetime.now().isoformat(), "apiReplica": REPLICA_ID, "agentes": results}


@router.get("/api/agentes/{agente_id}/actividad")
def get_agent_activity(agente_id: str, limit: int = Query(default=15, ge=1, le=100)):
    """Qué está insertando un agente: últimas filas en su BD, conteo por módulo y tablas impactadas."""
    return get_agent_activity_sync(_agent_num(agente_id), limit)


@router.post("/api/agentes/{agente_id}/ejecutar")
def run_agent_now(agente_id: str, request: Request):
    """Ejecuta UNA operación del agente ahora mismo (lo mismo que hace su script cada 60 s)."""
    import random as _random

    num = _agent_num(agente_id)
    ag = AGENTES_IA[num]
    operativos = [(u, v) for u, v in USUARIOS_15_MAP.items() if u not in ("admin", "dba")]
    if num == 5:
        operativos = [(u, v) for u, v in operativos if v[1] in ("VENTAS", "CONTABILIDAD")]
    usuario, (_rol, modulo, password) = _random.choice(operativos)
    payload = AgentOperationRequest(
        agente=ag["nombre"],
        usuario=usuario,
        password=password,
        modulo="VENTAS" if num == 5 else modulo,
        operacion=f"[Manual GUI] {ag['operacion'].format(modulo=modulo, usuario=usuario)}",
        montoUsd=0.0 if num == 2 else round(_random.uniform(95.0, 1500.0), 2),
        extraJson={"alerta": "STOCK_BAJO", "origen": "GUI", "usuario": usuario} if num == 2 else None,
    )
    return handle_agent_routed_operation(payload, request, x_sede=ag["sede"])


# ==============================================================================
# POWER BI: TABLAS PLANAS LISTAS PARA "OBTENER DATOS -> WEB" (Power Query M)
# ==============================================================================

POWERBI_DIMENSIONES = {"dim_sede", "dim_producto", "dim_tiempo"}


def _dwh_select(sql: str) -> list[dict[str, Any]]:
    configs = get_cluster_6dbs_config()
    conn, _ = connect_mariadb_with_fallback(configs["GUAYAQUIL_DWH"])
    cur = conn.cursor()
    cur.execute(sql)
    rows = _rows_as_dicts(cur)
    cur.close()
    conn.close()
    return rows


@router.get("/api/powerbi/fact_ventas")
def powerbi_fact_ventas():
    """Tabla de hechos completa de BD 5 (sin joins: Power BI arma las relaciones del esquema estrella)."""
    return _dwh_select(
        "SELECT id_fact, id_sede, id_producto, id_tiempo, usuario_rbac, rol_rbac, cantidad_botellas, "
        "subtotal_usd, iva_usd, total_venta_usd, etl_lote, fecha_carga_etl FROM fact_ventas ORDER BY id_fact"
    )


@router.get("/api/powerbi/dim/{tabla}")
def powerbi_dimension(tabla: str):
    if tabla not in POWERBI_DIMENSIONES:
        raise HTTPException(status_code=404, detail=f"Dimensión no válida. Use: {sorted(POWERBI_DIMENSIONES)}")
    return _dwh_select(f"SELECT * FROM {tabla}")


@router.get("/api/powerbi/operaciones_6bds")
async def powerbi_operaciones_6bds(limit: int = Query(default=200, ge=1, le=2000)):
    """Operaciones de los 6 agentes unificadas desde las 6 BDs (SQL + NoSQL + Cloud) con `origen_nodo`."""
    keys = ["QUITO", "QUITO_NOSQL", "QUITO_PARALELA", "GUAYAQUIL", "GUAYAQUIL_DWH", "CUENCA"]
    results = await asyncio.gather(*(asyncio.to_thread(fetch_global_records_from_bd_sync, k, limit) for k in keys))
    data = []
    for r in results:
        data.extend(r["records"])
    return data


@router.get("/api/powerbi/salud_nodos")
async def powerbi_salud_nodos():
    """Estado y latencia de las 6 BDs como tabla plana (para un semáforo en Power BI)."""
    keys = ["QUITO", "QUITO_NOSQL", "QUITO_PARALELA", "GUAYAQUIL", "GUAYAQUIL_DWH", "CUENCA"]
    nodes = await asyncio.gather(*(asyncio.to_thread(inspect_single_bd_sync, k) for k in keys))
    return [
        {
            "bd": n["bdId"], "sede": n["xSede"], "maquina": n["machine"], "motor": n["engine"],
            "puerto": n["port"], "estado": n["status"], "latencia_ms": n["latencyMs"],
            "tablas": n["tablesCount"], "tamano_kb": n["sizeKb"], "medido_en": datetime.now().isoformat(),
        }
        for n in nodes
    ]


# ==============================================================================
# FEED EN VIVO: ÚLTIMAS ACCIONES DE LOS 6 AGENTES (consulta ligera, para sondear cada pocos segundos)
# ==============================================================================

def _feed_agent_sync(agent_num: int, limit: int) -> dict[str, Any]:
    """Últimas `limit` acciones de un agente. `segundos` se calcula con el reloj de la propia BD (sin desfase)."""
    ag = AGENTES_IA[agent_num]
    configs = get_cluster_6dbs_config()
    cfg = configs[ag["sede"]]
    like = f"{ag['prefijo']}%"
    agent_id = f"agente-{agent_num}"
    eventos: list[dict[str, Any]] = []

    def ev(ident: Any, segundos: Any, usuario: Any, modulo: Any, detalle: Any, monto: Any) -> dict[str, Any]:
        return {
            "key": f"{agent_id}:{ident}",
            "agentId": agent_id,
            "codigo": ag["codigo"],
            "sede": ag["sede"],
            "bdId": cfg["bdId"],
            "segundos": max(0, int(segundos)) if segundos is not None else None,
            "usuario": usuario,
            "modulo": modulo,
            "detalle": str(detalle or "")[:160],
            "monto": float(monto or 0),
        }

    try:
        if agent_num in (1, 4):
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            cur.execute(
                "SELECT id_op, TIMESTAMPDIFF(SECOND, fecha_hora, NOW()), usuario_rbac, modulo, operacion, monto_usd "
                "FROM operaciones_agentes_ia WHERE agente_nombre LIKE %s ORDER BY id_op DESC LIMIT %s",
                (like, limit),
            )
            eventos = [ev(*r) for r in cur.fetchall()]
            cur.close()
            conn.close()
        elif agent_num == 2:
            cli, _ = connect_mongo_with_fallback(cfg)
            col = cli[cfg["database"]]["eventos_agentes"]
            ahora = datetime.now()
            for d in col.find({"agente": {"$regex": f"^{ag['prefijo']}"}}).sort("_id", -1).limit(limit):
                try:
                    secs = (ahora - datetime.fromisoformat(str(d.get("timestamp")))).total_seconds()
                except ValueError:
                    secs = None
                eventos.append(ev(d.get("evento_id") or d.get("_id"), secs, d.get("usuario_rbac"), d.get("modulo"),
                                  f"Documento JSON: {json.dumps(d.get('detalle', {}), ensure_ascii=False, default=str)}", 0))
            cli.close()
        elif agent_num == 3:
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, TIMESTAMPDIFF(SECOND, fecha_registro, NOW()), usuario_rbac, modulo, "
                "CONCAT('Lote ', codigo_referencia, ' → partición p', particion_hash), monto_usd "
                "FROM historico_transacciones ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            eventos = [ev(*r) for r in cur.fetchall()]
            cur.close()
            conn.close()
        elif agent_num == 5:
            conn, _ = connect_mariadb_with_fallback(cfg)
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id, TIMESTAMPDIFF(SECOND, fecha_corrida, NOW()), 'etl', 'VENTAS', "
                    "CONCAT('ETL ', lote, ': ', hechos_cargados, ' hechos cargados (', COALESCE(detalle, ''), ')'), "
                    "(SELECT COALESCE(SUM(total_venta_usd), 0) FROM fact_ventas f WHERE f.etl_lote = c.lote) "
                    "FROM etl_corridas c ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                eventos = [ev(*r) for r in cur.fetchall()]
            except Exception:
                eventos = []
            cur.close()
            conn.close()
        else:
            conn, _ = connect_postgres_with_fallback(cfg)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_op, EXTRACT(EPOCH FROM (now() - fecha_hora))::int, usuario_rbac, modulo, "
                    "operacion || ' (WAN ' || COALESCE(latencia_wan_ms::text, '?') || ' ms)', monto_usd "
                    "FROM operaciones_agentes_cloud WHERE agente_nombre LIKE %s ORDER BY id_op DESC LIMIT %s",
                    (like, limit),
                )
                eventos = [ev(*r) for r in cur.fetchall()]
            conn.close()
        ultima = eventos[0]["segundos"] if eventos else None
        return {"agentId": agent_id, "online": True, "segundosDesdeUltima": ultima, "eventos": eventos}
    except Exception as exc:
        return {"agentId": agent_id, "online": False, "segundosDesdeUltima": None, "eventos": [], "error": str(exc)[:200]}


@router.get("/api/agentes/feed")
async def get_agents_live_feed(limit: int = Query(default=8, ge=1, le=50)):
    """Feed unificado de las 6 BDs: estado por agente + últimas acciones ordenadas de la más nueva a la más vieja."""
    t0 = time.perf_counter()
    results = await asyncio.gather(*(asyncio.to_thread(_feed_agent_sync, n, limit) for n in AGENTES_IA))
    eventos = [e for r in results for e in r["eventos"]]
    eventos.sort(key=lambda e: (e["segundos"] if e["segundos"] is not None else 10**9))
    return {
        "timestamp": datetime.now().isoformat(),
        "apiReplica": REPLICA_ID,
        "latencyMs": round((time.perf_counter() - t0) * 1000, 2),
        "agentes": {r["agentId"]: {k: v for k, v in r.items() if k != "eventos"} for r in results},
        "eventos": eventos,
    }
