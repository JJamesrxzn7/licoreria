import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres_connection import _validate_database_role, connect_postgres

DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


class PostgresConnectionTests(unittest.TestCase):
    def test_requires_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
                connect_postgres()

    def test_requires_existing_ca(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True):
            with self.assertRaisesRegex(ValueError, "certificado"):
                connect_postgres()

    def test_enforces_full_tls_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.crt"
            ca.write_text("test", encoding="utf-8")
            with patch.dict(os.environ, {
                "DATABASE_URL": "postgresql://example?sslmode=disable",
                "POSTGRES_SSL_ROOT_CERT": str(ca),
            }, clear=True), patch("postgres_connection.psycopg.connect") as connect:
                connect.return_value.execute.return_value.fetchone.return_value = (
                    False, False, False, False, False, False, False,
                )
                connect_postgres()
        connect.assert_called_once_with(
            "postgresql://example?sslmode=disable",
            sslmode="verify-full",
            sslrootcert=str(ca),
            connect_timeout=15,
        )

    def test_rejects_privileged_or_owning_database_roles(self):
        cases = (
            (True, False, False, False, False, False, False),
            (False, True, False, False, False, False, False),
            (False, False, True, False, False, False, False),
            (False, False, False, True, False, False, False),
            (False, False, False, False, True, False, False),
            (False, False, False, False, False, True, False),
            (False, False, False, False, False, False, True),
        )
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.crt"
            ca.write_text("test", encoding="utf-8")
            for role_flags in cases:
                with self.subTest(role_flags=role_flags), \
                     patch.dict(os.environ, {
                         "DATABASE_URL": "postgresql://example",
                         "POSTGRES_SSL_ROOT_CERT": str(ca),
                     }, clear=True), \
                     patch("postgres_connection.psycopg.connect") as connect:
                    connect.return_value.execute.return_value.fetchone.return_value = role_flags
                    with self.assertRaisesRegex(ValueError, "sin BYPASSRLS"):
                        connect_postgres()
                    connect.return_value.close.assert_called_once()

    def test_rejects_missing_database_role_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.crt"
            ca.write_text("test", encoding="utf-8")
            with patch.dict(os.environ, {
                "DATABASE_URL": "postgresql://example",
                "POSTGRES_SSL_ROOT_CERT": str(ca),
            }, clear=True), patch("postgres_connection.psycopg.connect") as connect:
                connect.return_value.execute.return_value.fetchone.return_value = None
                with self.assertRaisesRegex(ValueError, "No se pudo verificar"):
                    connect_postgres()
                connect.return_value.close.assert_called_once()


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL local aislado.")
class PostgresConnectionDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")

    def test_role_guard_against_real_postgres_attributes_and_ownership(self):
        suffix = uuid4().hex[:12]
        accepted_role = "api_guard_ok_" + suffix
        bypass_role = "api_guard_bypass_" + suffix
        member_bypass_role = "api_guard_member_bypass_" + suffix
        schema_role = "api_guard_schema_" + suffix
        owner_role = "api_guard_owner_" + suffix
        member_owner_role = "api_guard_member_owner_" + suffix
        table_name = "api_guard_table_" + suffix
        roles = (
            accepted_role, bypass_role, member_bypass_role, schema_role,
            owner_role, member_owner_role,
        )
        try:
            with psycopg.connect(DSN, autocommit=True) as admin:
                for role_name, attributes in (
                    (accepted_role, "NOBYPASSRLS"),
                    (bypass_role, "BYPASSRLS"),
                    (member_bypass_role, "NOBYPASSRLS"),
                    (schema_role, "NOBYPASSRLS"),
                    (owner_role, "NOBYPASSRLS"),
                    (member_owner_role, "NOBYPASSRLS"),
                ):
                    admin.execute(
                        sql.SQL(
                            "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB "
                            "NOCREATEROLE NOREPLICATION {}"
                        ).format(
                            sql.Identifier(role_name), sql.SQL(attributes)
                        )
                    )
                admin.execute(
                    sql.SQL("GRANT {} TO {}").format(
                        sql.Identifier(bypass_role), sql.Identifier(member_bypass_role)
                    )
                )
                admin.execute(
                    sql.SQL("GRANT {} TO {}").format(
                        sql.Identifier(owner_role), sql.Identifier(member_owner_role)
                    )
                )
                admin.execute(
                    sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(
                        sql.Identifier(schema_role)
                    )
                )
                admin.execute(
                    sql.SQL("CREATE TABLE public.{} (id integer)").format(
                        sql.Identifier(table_name)
                    )
                )
                admin.execute(
                    sql.SQL("ALTER TABLE public.{} OWNER TO {}").format(
                        sql.Identifier(table_name), sql.Identifier(owner_role)
                    )
                )
            for role_name, should_pass in (
                (accepted_role, True),
                (bypass_role, False),
                (member_bypass_role, False),
                (schema_role, False),
                (owner_role, False),
                (member_owner_role, False),
            ):
                with self.subTest(role=role_name), psycopg.connect(DSN) as connection:
                    connection.execute(
                        sql.SQL("SET ROLE {}").format(sql.Identifier(role_name))
                    )
                    if should_pass:
                        _validate_database_role(connection)
                    else:
                        with self.assertRaisesRegex(ValueError, "sin BYPASSRLS"):
                            _validate_database_role(connection)
        finally:
            with psycopg.connect(DSN, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP TABLE IF EXISTS public.{}").format(sql.Identifier(table_name))
                )
                for role_name in roles:
                    admin.execute(
                        sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name))
                    )
                    admin.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role_name))
                    )


if __name__ == "__main__":
    unittest.main()
