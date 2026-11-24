"""
ERP transaccional en las TRES sedes (Quito, Guayaquil, Cuenca) con auditoría total.

- Guayaquil (BD 4) = tu ERP original "La Cava" (Laptop, MariaDB :3307, licoreriadatabase).
- Quito (BD 1)     = el mismo modelo en la PC de Escritorio (MariaDB :3307, base `lacava_quito`).
- Cuenca (BD 6)    = el mismo modelo en PostgreSQL (Laptop :5432, base `lacava_cuenca`),
                     a partir de la versión PostgreSQL del ERP (`licoreria_api_test`).

Este módulo:
  * genera y aplica la migración de AUDITORÍA TOTAL (MariaDB): log_Seq secuencial, log_Sede y
    triggers INSERT/UPDATE/DELETE en toda tabla de negocio que no los tuviera;
  * construye las sedes nuevas: esquema completo (tablas, vistas, triggers, procedimientos, funciones)
    + catálogos copiados; las transacciones empiezan vacías.

Uso:
    python API/erp_sedes.py auditoria GUAYAQUIL      # aplica la auditoría total en una sede MariaDB
    python API/erp_sedes.py migracion                # escribe migrations/20261123_auditoria_total_mariadb.sql
"""

import os
import sys
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parent
load_dotenv(API_DIR / ".env")

MARIADB_PASS = os.getenv("MARIADB_PASSWORD", "")
IP_QUITO = os.getenv("IP_TS_QUITO", "100.77.220.102")

SEDES_MARIADB = {
    "GUAYAQUIL": {"host": "127.0.0.1", "port": 3307, "database": "licoreriadatabase"},
    "QUITO": {"host": IP_QUITO, "port": 3307, "database": "lacava_quito"},
}

# Tablas de prueba/análisis que solo existen en la central (no son transacciones de negocio)
SOLO_CENTRAL = {"demo_ventas_hash", "demo_ventas_rango", "demo_ventas_rotativo",
                "dwh_dim_cliente", "dwh_dim_producto", "dwh_dim_tiempo", "dwh_fact_ventas"}
# Catálogos que se copian a cada sede nueva (las transacciones empiezan vacías)
CATALOGOS = ["ciudades", "tipo_cuenta", "cuentas", "bancos", "unidades_medidas", "categorias", "marcas", "perchas",
             "departamentos", "cargos", "empleados", "cargosxempleado", "cargas", "centros_costos", "bonificaciones",
             "descuentos", "proveedores", "clientes", "productos", "roles", "permisos", "rolesxpermisos",
             "usuarios", "usuariosxroles", "rbac_matriz_15_usuarios"]
# Las tablas réplica no se auditan: su copia ya se registra como una corrida de replicación en el log
NO_AUDITAR = {"log_auditoria", "demo_ventas_hash", "demo_ventas_rango", "demo_ventas_rotativo",
              "replica_quito_log", "replica_guayaquil_log", "replica_cuenca_log"}


def conectar_mariadb(sede: str, database: str | None = None):
    cfg = SEDES_MARIADB[sede]
    return mysql.connector.connect(host=cfg["host"], port=cfg["port"], user=os.getenv("MARIADB_USER", "root"),
                                   password=MARIADB_PASS, database=database or cfg["database"], use_pure=True,
                                   connection_timeout=10, autocommit=True)


def _trigger_auditoria(tabla: str, columnas: list[str]) -> list[str]:
    """Tres triggers AFTER (INSERT/UPDATE/DELETE) con el mismo formato que Script-Triggers.sql."""
    def obj(alias: str) -> str:
        return "JSON_OBJECT(" + ", ".join(f"'{c}', {alias}.`{c}`" for c in columnas) + ")"
    sentencias = []
    for sufijo, evento, antes, despues in (("AI", "INSERT", "NULL", obj("NEW")),
                                           ("AU", "UPDATE", obj("OLD"), obj("NEW")),
                                           ("AD", "DELETE", obj("OLD"), "NULL")):
        nombre = f"TRG_AUD_{tabla.upper()}_{sufijo}"
        sentencias.append(f"DROP TRIGGER IF EXISTS {nombre}")
        sentencias.append(
            f"CREATE TRIGGER {nombre} AFTER {evento} ON `{tabla}` FOR EACH ROW "
            f"INSERT INTO LOG_AUDITORIA (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_IP, "
            f"log_ValorAnterior, log_ValorNuevo) VALUES (LEFT(REPLACE(UUID(), '-', ''), 15), "
            f"NULLIF(@auditoria_usuario, ''), NOW(), '{tabla.upper()}', '{evento}', NULLIF(@auditoria_ip, ''), {antes}, {despues})"
        )
    return sentencias


def sentencias_auditoria_total(cur, sede: str) -> list[str]:
    """Calcula la migración para la BD a la que apunta `cur`."""
    sql = []
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'log_auditoria'")
    cols_log = {r[0].lower() for r in cur.fetchall()}
    if "log_seq" not in cols_log:
        # Orden total de los cambios (como la posición de un binlog): base de la replicación por log
        sql.append("ALTER TABLE LOG_AUDITORIA ADD COLUMN log_Seq BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, ADD UNIQUE KEY UQ_LOG_SEQ (log_Seq)")
    if "log_sede" not in cols_log:
        sql.append(f"ALTER TABLE LOG_AUDITORIA ADD COLUMN log_Sede VARCHAR(20) NOT NULL DEFAULT '{sede}'")
    else:
        sql.append(f"ALTER TABLE LOG_AUDITORIA ALTER COLUMN log_Sede SET DEFAULT '{sede}'")

    cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'")
    tablas = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT EVENT_OBJECT_TABLE, EVENT_MANIPULATION FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME LIKE 'TRG\\_AUD\\_%'")
    auditadas: dict[str, set] = {}
    for t, ev in cur.fetchall():
        auditadas.setdefault(t.lower(), set()).add(ev)
    for t in sorted(tablas):
        if t.lower() in NO_AUDITAR or auditadas.get(t.lower()) == {"INSERT", "UPDATE", "DELETE"}:
            continue
        cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                    "ORDER BY ORDINAL_POSITION", (t,))
        sql.extend(_trigger_auditoria(t, [r[0] for r in cur.fetchall()]))
    return sql


def reauditar_tabla(cur, tabla: str) -> None:
    """Regenera los 3 triggers de auditoría de una tabla con sus columnas ACTUALES (tras un ALTER TABLE)."""
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                "ORDER BY ORDINAL_POSITION", (tabla,))
    for s in _trigger_auditoria(tabla, [r[0] for r in cur.fetchall()]):
        cur.execute(s)


def aplicar_auditoria(sede: str) -> list[str]:
    conn = conectar_mariadb(sede)
    cur = conn.cursor()
    sentencias = sentencias_auditoria_total(cur, sede)
    for s in sentencias:
        cur.execute(s)
    cur.close()
    conn.close()
    return sentencias


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else ""
    if accion == "auditoria":
        hechas = aplicar_auditoria(sys.argv[2])
        print(f"{len(hechas)} sentencias aplicadas en {sys.argv[2]}")
        for s in hechas:
            print("  " + s[:110])
    elif accion == "migracion":
        conn = conectar_mariadb("GUAYAQUIL")
        cur = conn.cursor()
        sql = sentencias_auditoria_total(cur, "<SEDE>")
        destino = API_DIR / "migrations" / "20261123_auditoria_total_mariadb.sql"
        destino.write_text(
            "-- AUDITORÍA TOTAL (generada por API/erp_sedes.py a partir de las columnas reales).\n"
            "-- Reemplazar <SEDE> por QUITO / GUAYAQUIL. Agrega log_Seq (orden de cambios), log_Sede y\n"
            "-- triggers INSERT/UPDATE/DELETE en toda tabla de negocio que no los tenía.\n"
            "DELIMITER //\n" + "//\n".join(sql) + "//\nDELIMITER ;\n", encoding="utf-8")
        print(f"escrito {destino} ({len(sql)} sentencias)")
    else:
        print(__doc__)
