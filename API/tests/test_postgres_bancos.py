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
import postgres_bancos


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class BancosRealSchemaTests(unittest.TestCase):
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
        self.schema = "api_bancos_" + uuid4().hex
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
            """)
        self.patch = patch("postgres_bancos.connect_postgres", self.connect)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def test_creation_duplicates_and_audit(self):
        first = postgres_bancos.crear_banco(main.BancoInput(nombre="Banco Uno"), "U1", "127.0.0.1")
        self.assertEqual(first["id"], "BAN-000001")
        postgres_bancos.crear_banco(main.BancoInput(idBanco="banco-2", nombre="Banco Dos", estado="INA"), "U1", None)
        for banco in (main.BancoInput(idBanco="ban-000001", nombre="Otro Banco"),
                      main.BancoInput(nombre=" banco uno ")):
            with self.assertRaises(HTTPException) as error:
                postgres_bancos.crear_banco(banco, "U1", None)
            self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM bancos").fetchone()[0], 2)
            self.assertEqual(conn.execute(
                "SELECT trim(id_usuario), log_ip FROM log_auditoria "
                "WHERE log_tablaafectada='BANCOS' AND log_accion='INSERT' AND log_ip='127.0.0.1'"
            ).fetchone(), ("U1", "127.0.0.1"))

    def test_concurrent_names_and_ids(self):
        def create(name):
            try:
                return postgres_bancos.crear_banco(main.BancoInput(nombre=name), "U1", None)["id"]
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, ["Banco Igual", "banco igual"]))
        self.assertEqual(outcomes.count(409), 1)
        self.assertEqual(outcomes.count("BAN-000001"), 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, ["Banco A", "Banco B"]))
        self.assertEqual(set(outcomes), {"BAN-000002", "BAN-000003"})

    def test_audit_failure_rolls_back(self):
        created = postgres_bancos.crear_banco(main.BancoInput(nombre="Banco Uno"), "U1", None)
        with self.connect() as conn:
            conn.execute("DROP TABLE log_auditoria CASCADE")
        with self.assertRaises(psycopg.Error):
            postgres_bancos.crear_banco(main.BancoInput(nombre="Banco Dos"), "U1", None)
        with self.assertRaises(psycopg.Error):
            postgres_bancos.actualizar_banco(created["id"], main.BancoInput(nombre="Banco Cambio"), "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(ban_nombre) FROM bancos").fetchone()[0], "Banco Uno")

    def test_update_duplicate_status_and_concurrency(self):
        first = postgres_bancos.crear_banco(main.BancoInput(nombre="Banco Uno"), "U1", None)["id"]
        second = postgres_bancos.crear_banco(main.BancoInput(nombre="Banco Dos"), "U1", None)["id"]
        with self.assertRaises(HTTPException) as duplicate:
            postgres_bancos.actualizar_banco(second, main.BancoInput(nombre=" banco uno "), "U1", None)
        self.assertEqual(duplicate.exception.status_code, 409)
        with self.assertRaises(HTTPException) as missing:
            postgres_bancos.actualizar_banco("MISSING", main.BancoInput(nombre="Banco Tres"), "U1", None)
        self.assertEqual(missing.exception.status_code, 404)
        postgres_bancos.actualizar_banco(first.lower(), main.BancoInput(nombre="Banco Uno", estado="INA"), "U1", "127.0.0.1")
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(estado_ban) FROM bancos WHERE id_banco=%s", (first,)).fetchone()[0], "INA")
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE log_tablaafectada='BANCOS' "
                "AND log_accion='UPDATE' AND log_ip='127.0.0.1'"
            ).fetchone()[0], 1)
        def rename(bank_id):
            try:
                postgres_bancos.actualizar_banco(bank_id, main.BancoInput(nombre="Banco Común"), "U1", None)
                return 200
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(rename, (first, second))), [200, 409])

    def test_invalid_code_and_exhausted_sequence(self):
        with self.assertRaises(HTTPException) as error:
            postgres_bancos.crear_banco(main.BancoInput(idBanco="BAN 1", nombre="Banco Uno"), "U1", None)
        self.assertEqual(error.exception.status_code, 422)
        postgres_bancos.crear_banco(main.BancoInput(idBanco="BAN-999999", nombre="Banco Final"), "U1", None)
        with self.assertRaises(HTTPException) as error:
            postgres_bancos.crear_banco(main.BancoInput(nombre="Banco Otro"), "U1", None)
        self.assertEqual(error.exception.status_code, 409)

    def test_http_permissions_for_create_and_update(self):
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_CONTABILIDAD"}]) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            response = client.post("/api/contabilidad/bancos", json={"nombre": "Banco Uno"})
            self.assertEqual(response.status_code, 200, response.text)
            response = client.put("/api/contabilidad/bancos/BAN-000001", json={"nombre": "Banco Uno", "estado": "INA"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(client.get("/api/capabilities").json()["bankUpdates"])
            for role in ("Auxiliar_CONTABILIDAD", "Jefe_CONTABILIDAD", "Operativo_VENTAS"):
                active.return_value = [{"rol_nombre": role}]
                self.assertEqual(client.post("/api/contabilidad/bancos", json={"nombre": "Banco Dos"}).status_code, 403)
                self.assertEqual(client.put("/api/contabilidad/bancos/BAN-000001", json={"nombre": "Banco Uno"}).status_code, 403)
            active.return_value = [{"rol_nombre": "Administrador"}]
            self.assertEqual(client.post("/api/contabilidad/bancos", json={"nombre": "Banco Dos"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
