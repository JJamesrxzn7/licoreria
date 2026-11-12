import os
from pathlib import Path

import psycopg


def _validate_database_role(connection: psycopg.Connection) -> None:
    role = connection.execute(
        """
        SELECT r.rolsuper, r.rolbypassrls, r.rolcreatedb, r.rolcreaterole,
               r.rolreplication,
               has_schema_privilege(current_user, 'public', 'CREATE'),
               EXISTS (
                   SELECT 1
                   FROM pg_namespace n
                   WHERE n.nspname = 'public'
                     AND (n.nspowner = r.oid OR pg_has_role(r.oid, n.nspowner, 'MEMBER'))
               )
               OR EXISTS (
                   SELECT 1
                   FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public'
                     AND c.relkind IN ('r', 'p', 'f', 'S', 'v', 'm')
                     AND (c.relowner = r.oid OR pg_has_role(r.oid, c.relowner, 'MEMBER'))
               )
               OR EXISTS (
                   SELECT 1
                   FROM pg_proc p
                   JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'public'
                     AND (p.proowner = r.oid OR pg_has_role(r.oid, p.proowner, 'MEMBER'))
               )
               OR EXISTS (
                   SELECT 1
                   FROM pg_database d
                   WHERE d.datname = current_database()
                     AND (d.datdba = r.oid OR pg_has_role(r.oid, d.datdba, 'MEMBER'))
               )
               OR EXISTS (
                   SELECT 1
                   FROM pg_roles privileged
                   WHERE (privileged.rolsuper OR privileged.rolbypassrls
                          OR privileged.rolcreatedb OR privileged.rolcreaterole
                          OR privileged.rolreplication)
                     AND pg_has_role(r.oid, privileged.oid, 'MEMBER')
               )
        FROM pg_roles r
        WHERE r.rolname = current_user
        """
    ).fetchone()
    if role is None:
        raise ValueError("No se pudo verificar el rol de conexión PostgreSQL.")
    if any(role):
        raise ValueError(
            "DATABASE_URL debe usar un rol no administrativo, sin BYPASSRLS, "
            "CREATE en public ni propiedad de objetos en ese esquema."
        )


def connect_postgres() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL", "").strip()
    ca_path = os.getenv("POSTGRES_SSL_ROOT_CERT", "").strip()
    if not database_url:
        raise ValueError("Falta configurar DATABASE_URL para PostgreSQL.")
    if not ca_path or not Path(ca_path).is_file():
        raise ValueError("Falta un certificado CA válido para PostgreSQL.")
    connection = psycopg.connect(
        database_url,
        sslmode="verify-full",
        sslrootcert=ca_path,
        connect_timeout=15,
    )
    try:
        _validate_database_role(connection)
    except (psycopg.Error, ValueError):
        connection.close()
        raise
    return connection
