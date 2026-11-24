"""
Construye el ERP completo de CUENCA en PostgreSQL (base `lacava_cuenca`, Laptop :5432):

  1. Estructura + lógica desde la versión PostgreSQL del ERP (`licoreria_api_test`): tablas, vistas,
     funciones y 129 triggers (pg_dump --schema-only, sin dueños ni privilegios).
  2. Tablas del clúster: bitácora de agentes (operaciones_agentes_cloud) y matriz RBAC.
  3. Catálogos copiados desde Guayaquil (MariaDB) con los triggers desactivados durante la carga.
  4. Auditoría total: log_seq (orden de cambios), log_sede = 'CUENCA' y trigger de auditoría en TODA tabla.

No toca `licoreria_api_test` ni `cloud_cuenca_loja`. Si `lacava_cuenca` existe, se detiene (salvo --reemplazar).
Uso:  python API/erp_construir_sede_pg.py [--reemplazar]
"""

import os
import subprocess
import sys
from pathlib import Path

import mysql.connector
import psycopg

import erp_sedes

PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
PG_PASS = os.getenv("PGPASSWORD") or os.getenv("PG_PASS") or "147852369.MyPost"
PG = {"host": "127.0.0.1", "port": 5432, "user": "postgres", "password": PG_PASS}
FUENTE_PG = "licoreria_api_test"
DESTINO = "lacava_cuenca"
NO_AUDITAR_PG = {"log_auditoria"}

DDL_CLUSTER = [
    """CREATE TABLE IF NOT EXISTS operaciones_agentes_cloud (
        id_op BIGSERIAL PRIMARY KEY, sede_header VARCHAR(30) NOT NULL, agente_nombre VARCHAR(60) NOT NULL,
        usuario_rbac VARCHAR(30) NOT NULL, rol_rbac VARCHAR(30) NOT NULL, modulo VARCHAR(30) NOT NULL,
        operacion VARCHAR(255) NOT NULL, monto_usd NUMERIC(12,2) NOT NULL DEFAULT 0, latencia_wan_ms NUMERIC(10,2),
        tabla_ref VARCHAR(40), documento_ref VARCHAR(60), fecha_hora TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS rbac_matriz_15_usuarios (
        username VARCHAR(30) PRIMARY KEY, password_plano VARCHAR(60), rol_bd VARCHAR(30), rol_aplicacion VARCHAR(60),
        modulo_codigo VARCHAR(10), modulo_nombre VARCHAR(60), nombre_colaborador VARCHAR(120), descripcion_cargo VARCHAR(160),
        sede_nodo VARCHAR(30), estado VARCHAR(10), ultima_actividad TIMESTAMP)""",
]


def pg(db: str, autocommit: bool = True):
    return psycopg.connect(dbname=db, autocommit=autocommit, **PG)


def construir(reemplazar: bool) -> None:
    env = {**os.environ, "PGPASSWORD": PG_PASS}
    with pg("postgres") as c, c.cursor() as k:
        k.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DESTINO,))
        if k.fetchone():
            if not reemplazar:
                raise SystemExit(f"{DESTINO} ya existe. Usa --reemplazar para recrearla.")
            k.execute(f"DROP DATABASE {DESTINO} WITH (FORCE)")
        k.execute(f"CREATE DATABASE {DESTINO} ENCODING 'UTF8' TEMPLATE template0")
    print(f"Base {DESTINO} creada")

    dump = subprocess.run([str(PG_BIN / "pg_dump.exe"), "-h", PG["host"], "-p", str(PG["port"]), "-U", "postgres",
                           "--schema-only", "--no-owner", "--no-privileges", FUENTE_PG],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    if dump.returncode != 0:
        raise SystemExit(f"pg_dump falló: {dump.stderr[:400]}")
    carga = subprocess.run([str(PG_BIN / "psql.exe"), "-h", PG["host"], "-p", str(PG["port"]), "-U", "postgres", "-d", DESTINO,
                            "-v", "ON_ERROR_STOP=1", "-q"], input=dump.stdout, capture_output=True, text=True,
                           encoding="utf-8", env=env)
    if carga.returncode != 0:
        raise SystemExit(f"psql falló: {carga.stderr[:600]}")
    print("  [OK] estructura, vistas, funciones y triggers (desde la versión PostgreSQL del ERP)")

    with pg(DESTINO) as c, c.cursor() as k:
        for ddl in DDL_CLUSTER:
            k.execute(ddl)
    print("  [OK] tablas del clúster (bitácora de agentes y matriz RBAC)")

    # Catálogos: de MariaDB (Guayaquil) a PostgreSQL, por nombre de columna, sin disparar auditoría
    origen = erp_sedes.conectar_mariadb("GUAYAQUIL")
    co = origen.cursor()
    total = 0
    with pg(DESTINO, autocommit=False) as c:
        with c.cursor() as k:
            k.execute("SET session_replication_role = replica")  # no dispara triggers ni valida FKs durante la carga
            for tabla in erp_sedes.CATALOGOS:
                k.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                          (tabla,))
                tipos_pg = {r[0]: r[1] for r in k.fetchall()}
                cols_pg = set(tipos_pg)
                if not cols_pg:
                    print(f"  [aviso] {tabla} no existe en PostgreSQL: se omite")
                    continue
                co.execute(f"SELECT * FROM `{tabla}`")
                cols_my = [d[0] for d in co.description]
                comunes = [i for i, col in enumerate(cols_my) if col.lower() in cols_pg]
                filas = co.fetchall()
                if not filas:
                    continue
                nombres = ", ".join(cols_my[i].lower() for i in comunes)
                marcas = ", ".join(["%s"] * len(comunes))
                def convertir(valor, columna):
                    # MariaDB guarda los booleanos como 0/1; PostgreSQL los exige como boolean
                    if valor is not None and tipos_pg.get(columna) == "boolean":
                        return bool(valor)
                    return valor

                k.executemany(f"INSERT INTO {tabla} ({nombres}) VALUES ({marcas}) ON CONFLICT DO NOTHING",
                              [tuple(convertir(f[i], cols_my[i].lower()) for i in comunes) for f in filas])
                total += len(filas)
            # La política de la API PostgreSQL solo reconoce "Administrador" (rechaza nombres ambiguos a propósito)
            k.execute("UPDATE roles SET rol_nombre = 'Administrador' WHERE lower(trim(rol_nombre)) = 'superadministrador'")
        c.commit()
    co.close()
    origen.close()
    print(f"  [OK] catálogos copiados desde Guayaquil ({total} filas)")

    with pg(DESTINO) as c, c.cursor() as k:
        k.execute("ALTER TABLE log_auditoria ADD COLUMN IF NOT EXISTS log_seq BIGSERIAL")
        k.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_log_seq ON log_auditoria (log_seq)")
        k.execute("ALTER TABLE log_auditoria ADD COLUMN IF NOT EXISTS log_sede VARCHAR(20) NOT NULL DEFAULT 'CUENCA'")
        k.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")
        tablas = [r[0] for r in k.fetchall()]
        k.execute("SELECT DISTINCT event_object_table FROM information_schema.triggers WHERE trigger_schema = 'public' "
                  "AND action_statement ILIKE '%fn_trg_auditoria_general%'")
        auditadas = {r[0] for r in k.fetchall()}
        nuevas = []
        for t in tablas:
            if t in NO_AUDITAR_PG or t in auditadas:
                continue
            k.execute(f"CREATE TRIGGER trg_aud_{t} AFTER INSERT OR UPDATE OR DELETE ON {t} "
                      f"FOR EACH ROW EXECUTE FUNCTION fn_trg_auditoria_general()")
            nuevas.append(t)
    print(f"  [OK] auditoría total: log_seq, log_sede='CUENCA' y trigger en {len(nuevas)} tablas más {nuevas}")


ROL_API = "lacava_cuenca_api"


def preparar_rol_api() -> None:
    """
    Usuario de conexión de la API para Cuenca, con MÍNIMO PRIVILEGIO (lo exige postgres_connection.py):
    LOGIN, sin superusuario ni BYPASSRLS, miembro del grupo licoreria_api_access, con los mismos GRANT que
    define la migración 20261108_api_role_rls_postgresql.sql. La contraseña se genera y se guarda en API/.env.
    """
    import secrets

    env_path = Path(__file__).with_name(".env")
    contenido = env_path.read_text(encoding="utf-8")
    if "CUENCA_DATABASE_URL=" in contenido:
        url = next(l.split("=", 1)[1] for l in contenido.splitlines() if l.startswith("CUENCA_DATABASE_URL="))
        clave = url.split(":", 2)[2].split("@", 1)[0]
    else:
        clave = secrets.token_urlsafe(24)
        with env_path.open("a", encoding="utf-8") as f:
            f.write("\n# Conexión de la API a la sede Cuenca (rol de mínimo privilegio, BD local)\n"
                    f"CUENCA_DATABASE_URL=postgresql://{ROL_API}:{clave}@127.0.0.1:5432/{DESTINO}\n")

    with pg("postgres") as c, c.cursor() as k:
        k.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROL_API,))
        from psycopg import sql as pgsql
        if k.fetchone():
            k.execute(pgsql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(pgsql.Identifier(ROL_API), pgsql.Literal(clave)))
        else:
            k.execute(pgsql.SQL("CREATE ROLE {} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                                "PASSWORD {} IN ROLE licoreria_api_access").format(pgsql.Identifier(ROL_API), pgsql.Literal(clave)))
        k.execute(f"GRANT CONNECT ON DATABASE {DESTINO} TO {ROL_API}")

    # GRANT del ERP leídos de la migración oficial (mismas listas, sin recrear rol ni políticas: ya vienen en el esquema)
    import re
    migracion = (Path(__file__).parent / "migrations" / "20261108_api_role_rls_postgresql.sql").read_text(encoding="utf-8")
    listas = [re.findall(r"'([a-z_]+)'", bloque) for bloque in re.findall(r"ARRAY\[(.*?)\]", migracion, re.S)]
    solo_lectura, lectura_escritura, procedimientos = listas[0], listas[1], listas[2]
    with pg(DESTINO) as c, c.cursor() as k:
        for t in solo_lectura:
            k.execute(f"GRANT SELECT ON TABLE public.{t} TO licoreria_api_access")
        for t in lectura_escritura:
            k.execute(f"GRANT INSERT, UPDATE ON TABLE public.{t} TO licoreria_api_access")
        k.execute("SELECT p.proname, pg_get_function_identity_arguments(p.oid) FROM pg_proc p JOIN pg_namespace n "
                  "ON n.oid = p.pronamespace WHERE n.nspname = 'public' AND p.prokind = 'p' AND p.proname = ANY(%s)", (procedimientos,))
        procs = k.fetchall()
        for nombre, args in procs:
            k.execute(f"GRANT EXECUTE ON PROCEDURE public.{nombre}({args}) TO licoreria_api_access")
        # Agregados por el clúster y la auditoría total (la migración original no los conocía)
        k.execute("GRANT SELECT, INSERT, UPDATE ON operaciones_agentes_cloud TO licoreria_api_access")
        k.execute("GRANT SELECT, UPDATE ON rbac_matriz_15_usuarios TO licoreria_api_access")
        k.execute("GRANT USAGE ON SEQUENCE log_auditoria_log_seq_seq, operaciones_agentes_cloud_id_op_seq TO licoreria_api_access")
    print(f"  [OK] rol {ROL_API} (mínimo privilegio): SELECT en {len(solo_lectura)} tablas, INSERT/UPDATE en "
          f"{len(lectura_escritura)}, EXECUTE en {len(procs)} procedimientos + clúster y secuencia del log")


if __name__ == "__main__":
    if "--rol" in sys.argv:
        preparar_rol_api()
    else:
        construir("--reemplazar" in sys.argv)
        preparar_rol_api()
