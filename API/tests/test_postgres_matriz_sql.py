import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")
SCRIPT = Path(__file__).resolve().parents[1] / "migrations" / "20261108_matriz_permisos_postgresql.sql"


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL aislado.")
class PostgresMatrixScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")

    def setUp(self):
        self.schema = "api_matrix_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE roles (id_rol char(10) PRIMARY KEY, rol_nombre text, estado_rol char(3));
                CREATE TABLE permisos (id_permiso char(10) PRIMARY KEY, prm_modulo text,
                                       prm_accion text, estado_prm char(3));
                CREATE TABLE rolesxpermisos (id_rol char(10), id_permiso char(10),
                                              estado_rxp char(3), PRIMARY KEY (id_rol, id_permiso));
            """)
            modules = ("COMPRAS", "INVENTARIOS", "VENTAS", "TALENTO_HUMANO", "CONTABILIDAD")
            for index, name in enumerate(
                ["Administrador"] + [f"{role}_{module}" for module in modules for role in ("Jefe", "Auxiliar", "Operativo")]
            ):
                conn.execute("INSERT INTO roles VALUES (%s, %s, 'ACT')", (f"R{index}", name))
            for index, (module, action) in enumerate(
                (module, action) for module in modules for action in ("CREAR", "VER", "APROBAR", "ANULAR")
            ):
                conn.execute("INSERT INTO permisos VALUES (%s, %s, %s, 'ACT')", (f"P{index}", module, action))
            conn.execute("INSERT INTO permisos VALUES ('EXTRA', 'OTRO', 'VER', 'ACT')")
            conn.execute("INSERT INTO rolesxpermisos VALUES ('R0', 'EXTRA', 'ACT'), ('R1', 'EXTRA', 'ACT')")

    def connect(self, **kwargs):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema}", **kwargs)

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def run_script(self):
        source = SCRIPT.read_text(encoding="utf-8").replace("public.", self.schema + ".")
        with self.connect(autocommit=True) as conn:
            conn.execute(source, prepare=False)

    def test_exact_matrix_and_administrator_extra(self):
        self.run_script()
        self.run_script()
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT r.rol_nombre, p.prm_modulo, p.prm_accion
                FROM rolesxpermisos rp JOIN roles r USING (id_rol)
                JOIN permisos p USING (id_permiso) WHERE rp.estado_rxp = 'ACT'
            """).fetchall()
            status = conn.execute("""
                SELECT trim(id_rol), estado_rxp FROM rolesxpermisos
                WHERE id_permiso = 'EXTRA' ORDER BY id_rol
            """).fetchall()
        self.assertEqual(len(rows), 51)
        self.assertEqual(status, [("R0", "ACT"), ("R1", "INA")])
        for name, module, action in rows:
            if name == "Administrador":
                continue
            prefix, expected_module = name.split("_", 1)
            self.assertEqual(module, expected_module)
            self.assertIn(action, {"VER", {"Jefe": "ANULAR", "Auxiliar": "APROBAR", "Operativo": "CREAR"}[prefix]})

    def test_duplicate_permission_aborts_without_changing_assignments(self):
        with self.connect() as conn:
            conn.execute("INSERT INTO permisos VALUES ('DUP', 'COMPRAS', 'VER', 'ACT')")
        with self.assertRaises(psycopg.Error):
            self.run_script()
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM rolesxpermisos").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
