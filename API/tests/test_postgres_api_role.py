import os
import re
import sys
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres_connection import _validate_database_role

DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "20261108_api_role_rls_postgresql.sql"
)


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL local aislado.")
class PostgresApiRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")

    def test_api_role_migration_grants_only_declared_access(self):
        schema_name = "api_role_test_" + uuid4().hex[:12]
        role_name = "api_access_test_" + uuid4().hex[:12]
        login_role_name = "api_login_test_" + uuid4().hex[:12]
        script = MIGRATION.read_text(encoding="utf-8")
        table_lists = re.findall(
            r"FOREACH table_name IN ARRAY ARRAY\[(.*?)\] LOOP", script, re.DOTALL
        )
        self.assertEqual(len(table_lists), 2)
        tables = sorted(set(re.findall(r"'([a-z_]+)'", table_lists[0])))
        writable_tables = set(re.findall(r"'([a-z_]+)'", table_lists[1]))
        procedure_names = re.findall(
            r"'(sp_(?:compra_[a-z_]+|registrar_log))'", script
        )
        self.assertEqual(len(tables), 43)
        self.assertTrue(writable_tables.issubset(tables))
        self.assertEqual(len(procedure_names), 5)
        script = re.sub(r"\blicoreria_api_access\b", role_name, script)
        script = re.sub(r"\bpublic\b", schema_name, script)

        try:
            with psycopg.connect(DSN, autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
                for table_name in tables + ["api_ungranted"]:
                    admin.execute(
                        sql.SQL("CREATE TABLE {}.{} (id integer PRIMARY KEY)").format(
                            sql.Identifier(schema_name), sql.Identifier(table_name)
                        )
                    )
                for procedure_name in procedure_names:
                    admin.execute(
                        sql.SQL(
                            "CREATE PROCEDURE {}.{}() LANGUAGE plpgsql "
                            "AS 'BEGIN NULL; END'"
                        ).format(sql.Identifier(schema_name), sql.Identifier(procedure_name))
                    )
                admin.execute(script, prepare=False)
                admin.execute(
                    sql.SQL(
                        "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(login_role_name))
                )
                admin.execute(
                    sql.SQL("GRANT {} TO {}").format(
                        sql.Identifier(role_name), sql.Identifier(login_role_name)
                    )
                )

            with psycopg.connect(DSN) as connection:
                connection.execute(
                    sql.SQL("SET ROLE {}").format(sql.Identifier(login_role_name))
                )
                _validate_database_role(connection)
                connection.execute(
                    sql.SQL("INSERT INTO {}.productos (id) VALUES (1)").format(
                        sql.Identifier(schema_name)
                    )
                )
                connection.execute(
                    sql.SQL("UPDATE {}.productos SET id = 2 WHERE id = 1").format(
                        sql.Identifier(schema_name)
                    )
                )
                self.assertEqual(
                    connection.execute(
                        sql.SQL("SELECT id FROM {}.productos").format(
                            sql.Identifier(schema_name)
                        )
                    ).fetchone(),
                    (2,),
                )
                connection.execute(
                    sql.SQL("CALL {}.sp_compra_crear()").format(
                        sql.Identifier(schema_name)
                    )
                )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        connection.execute(
                            sql.SQL("DELETE FROM {}.productos WHERE id = 2").format(
                                sql.Identifier(schema_name)
                            )
                        )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        connection.execute(
                            sql.SQL("SELECT id FROM {}.api_ungranted").format(
                                sql.Identifier(schema_name)
                            )
                        )
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        connection.execute(
                            sql.SQL("CREATE TABLE {}.api_forbidden (id integer)").format(
                                sql.Identifier(schema_name)
                            )
                        )
        finally:
            with psycopg.connect(DSN, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )
                role_exists = admin.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                    (role_name,),
                ).fetchone()[0]
                if role_exists:
                    login_exists = admin.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                        (login_role_name,),
                    ).fetchone()[0]
                    if login_exists:
                        admin.execute(
                            sql.SQL("REVOKE {} FROM {}").format(
                                sql.Identifier(role_name),
                                sql.Identifier(login_role_name),
                            )
                        )
                        admin.execute(
                            sql.SQL("DROP OWNED BY {}").format(
                                sql.Identifier(login_role_name)
                            )
                        )
                        admin.execute(
                            sql.SQL("DROP ROLE {}").format(
                                sql.Identifier(login_role_name)
                            )
                        )
                    admin.execute(
                        sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name))
                    )
                    admin.execute(
                        sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name))
                    )


if __name__ == "__main__":
    unittest.main()
