import os
import re
import shutil
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import postgres_cuentas


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class CuentasRealSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")
        pg_dump = os.getenv("LICORERIA_TEST_PG_DUMP") or shutil.which("pg_dump")
        if not pg_dump:
            raise unittest.SkipTest("pg_dump no está disponible.")
        dump = subprocess.run(
            [pg_dump, "--schema-only", "--no-owner", "--no-acl", "--schema=public", "--dbname", DSN],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", timeout=30,
        ).stdout
        cls.dump = re.sub(r"(?m)^\\(?:un)?restrict[^\n]*\n", "", dump)

    def setUp(self):
        self.schema = "api_cuentas_" + uuid4().hex
        clone = re.sub(r"\bpublic\b", self.schema, self.dump)
        with psycopg.connect(DSN, autocommit=True) as conn:
            try:
                conn.execute(clone, prepare=False)
            except psycopg.Error:
                conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
                raise
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO departamentos (id_departamento,dep_nombre,estado_dep) VALUES ('D1','Prueba','ACT');
                INSERT INTO empleados (id_empleado,id_departamento,emp_cedula,emp_apellido1,
                    emp_nombre1,emp_fechanacimiento,emp_sueldo,estado_emp)
                    VALUES ('E1','D1','1234567890','Prueba','Ana','1990-01-01',500,'ACT');
                INSERT INTO usuarios (id_usuario,id_empleado,usr_username,usr_passwordhash,estado_usr)
                    VALUES ('U1','E1','prueba','x','ACT');
                INSERT INTO tipo_cuenta (id_tipo_cta,tip_descripcion) VALUES ('MAY','Mayor'),('DET','Detalle');
            """)
        patcher = patch("postgres_cuentas.connect_postgres", self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def account(self, code="1.1", name="Caja Principal", kind="DET"):
        return main.AccountInput(idCuenta=code, nombre=name, tipo=kind)

    def test_creation_audit_and_no_overwrite(self):
        postgres_cuentas.crear_cuenta(self.account(), "U1", "127.0.0.1")
        postgres_cuentas.crear_cuenta(self.account("2", "Pasivo", "MAY"), "U1", None)
        with self.connect() as conn:
            conn.execute("UPDATE cuentas SET cue_debe00=99 WHERE id_cuenta='1.1'")
        with self.assertRaises(HTTPException) as error:
            postgres_cuentas.crear_cuenta(self.account(name="Otra Cuenta", kind="MAY"), "U1", None)
        self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT trim(cue_descripcion), trim(cue_tipo), cue_debe00, cue_haber00, trim(estado_cue) "
                "FROM cuentas WHERE id_cuenta='1.1'"
            ).fetchone(), ("Caja Principal", "DET", 99, 0, "ACT"))
            self.assertEqual(conn.execute(
                "SELECT trim(id_usuario), log_ip FROM log_auditoria "
                "WHERE log_tablaafectada='CUENTAS' AND log_accion='INSERT' AND log_ip='127.0.0.1'"
            ).fetchone(), ("U1", "127.0.0.1"))

    def test_concurrent_duplicate(self):
        def create(name):
            try:
                return postgres_cuentas.crear_cuenta(self.account(name=name), "U1", None)["id"]
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(create, ["Caja Uno", "Caja Dos"]))
        self.assertCountEqual(result, ["1.1", 409])
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cuentas").fetchone()[0], 1)

    def test_missing_type_and_audit_failure(self):
        with self.connect() as conn:
            conn.execute("DELETE FROM tipo_cuenta WHERE id_tipo_cta='DET'")
        with self.assertRaises(HTTPException) as error:
            postgres_cuentas.crear_cuenta(self.account(), "U1", None)
        self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            conn.execute("DROP TABLE log_auditoria CASCADE")
        with self.assertRaises(psycopg.Error):
            postgres_cuentas.crear_cuenta(self.account("2", "Pasivo", "MAY"), "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cuentas").fetchone()[0], 0)

    def test_http_permissions(self):
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_CONTABILIDAD"}]) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            payload = {"idCuenta": "1.1", "nombre": "Caja Principal", "tipo": "DET"}
            self.assertEqual(client.post("/api/contabilidad/cuentas", json=payload).status_code, 200)
            self.assertEqual(client.post("/api/contabilidad/cuentas", json=payload).status_code, 409)
            payload["idCuenta"] = "2"
            for role in ("Auxiliar_CONTABILIDAD", "Jefe_CONTABILIDAD", "Operativo_VENTAS"):
                active.return_value = [{"rol_nombre": role}]
                self.assertEqual(client.post("/api/contabilidad/cuentas", json=payload).status_code, 403)
            active.return_value = [{"rol_nombre": "Administrador"}]
            self.assertEqual(client.post("/api/contabilidad/cuentas", json=payload).status_code, 200)


if __name__ == "__main__":
    unittest.main()
