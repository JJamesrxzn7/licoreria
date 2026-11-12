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
import postgres_nomina_catalogos


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class CatalogosNominaRealSchemaTests(unittest.TestCase):
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
        self.schema = "api_catalogos_nomina_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            try:
                conn.execute(re.sub(r"\bpublic\b", self.schema, self.dump), prepare=False)
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
        patcher = patch("postgres_nomina_catalogos.connect_postgres", self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def item(self, name="Concepto prueba", status="ACT"):
        return main.PayrollCatalogInput(nombre=name, valor="12.34", estado=status)

    def test_create_disable_and_audit_for_both_catalogs(self):
        for kind, prefix in (("bonificaciones", "BON"), ("descuentos", "DES")):
            result = postgres_nomina_catalogos.crear(kind, self.item(), "U1", "127.0.0.1")
            self.assertEqual(result["id"], f"{prefix}-000001")
            with self.assertRaises(HTTPException) as error:
                postgres_nomina_catalogos.crear(kind, self.item(" concepto prueba "), "U1", None)
            self.assertEqual(error.exception.status_code, 409)
            postgres_nomina_catalogos.desactivar(kind, result["id"], "U1", None)
            with self.assertRaises(HTTPException) as error:
                postgres_nomina_catalogos.desactivar(kind, result["id"], "U1", None)
            self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(estado_bon) FROM bonificaciones").fetchone()[0], "INA")
            self.assertEqual(conn.execute("SELECT trim(estado_des) FROM descuentos").fetchone()[0], "INA")
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE id_usuario='U1' "
                "AND log_tablaafectada IN ('BONIFICACIONES','DESCUENTOS')"
            ).fetchone()[0], 4)

    def test_validation_and_concurrent_creation_and_disable(self):
        for item in (self.item("x" * 41), self.item(status="INA")):
            with self.assertRaises(HTTPException) as error:
                postgres_nomina_catalogos.crear("bonificaciones", item, "U1", None)
            self.assertEqual(error.exception.status_code, 422)

        def create(name):
            try:
                return postgres_nomina_catalogos.crear("bonificaciones", self.item(name), "U1", None)["id"]
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(create, ["Bono prueba", "bono prueba"])), ["BON-000001", 409])

        def disable(_):
            try:
                postgres_nomina_catalogos.desactivar("bonificaciones", "BON-000001", "U1", None)
                return 200
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(disable, range(2))), [200, 409])

    def test_audit_failure_rolls_back(self):
        created = postgres_nomina_catalogos.crear("bonificaciones", self.item(), "U1", None)
        with self.connect() as conn:
            conn.execute("DROP TABLE log_auditoria CASCADE")
        with self.assertRaises(psycopg.Error):
            postgres_nomina_catalogos.crear("descuentos", self.item(), "U1", None)
        with self.assertRaises(psycopg.Error):
            postgres_nomina_catalogos.desactivar("bonificaciones", created["id"], "U1", None)
        with self.assertRaises(psycopg.Error):
            postgres_nomina_catalogos.actualizar("bonificaciones", created["id"], self.item("Cambio"), "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM descuentos").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT trim(estado_bon) FROM bonificaciones").fetchone()[0], "ACT")
            self.assertEqual(conn.execute("SELECT trim(bon_descripcion) FROM bonificaciones").fetchone()[0], "Concepto prueba")

    def test_update_duplicate_reactivate_and_concurrent_names(self):
        for kind in ("bonificaciones", "descuentos"):
            first = postgres_nomina_catalogos.crear(kind, self.item("Primero"), "U1", None)["id"]
            second = postgres_nomina_catalogos.crear(kind, self.item("Segundo"), "U1", None)["id"]
            with self.assertRaises(HTTPException) as duplicate:
                postgres_nomina_catalogos.actualizar(kind, second, self.item(" primero "), "U1", None)
            self.assertEqual(duplicate.exception.status_code, 409)
            with self.assertRaises(HTTPException) as missing:
                postgres_nomina_catalogos.actualizar(kind, "MISSING", self.item(), "U1", None)
            self.assertEqual(missing.exception.status_code, 404)
            with self.assertRaises(HTTPException) as too_long:
                postgres_nomina_catalogos.actualizar(kind, first, self.item("x" * 41), "U1", None)
            self.assertEqual(too_long.exception.status_code, 422)
            postgres_nomina_catalogos.desactivar(kind, first, "U1", None)
            postgres_nomina_catalogos.actualizar(kind, first, self.item("Reactivado"), "U1", None)
            def rename(catalog_id):
                try:
                    postgres_nomina_catalogos.actualizar(kind, catalog_id, self.item("Mismo nombre"), "U1", None)
                    return 200
                except HTTPException as error:
                    return error.status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertCountEqual(list(pool.map(rename, (first, second))), [200, 409])

    def test_exact_name_limit_missing_and_exhaustion(self):
        result = postgres_nomina_catalogos.crear("descuentos", self.item("x" * 40), "U1", None)
        self.assertEqual(result["id"], "DES-000001")
        with self.assertRaises(HTTPException) as error:
            postgres_nomina_catalogos.desactivar("descuentos", "DES-999998", "U1", None)
        self.assertEqual(error.exception.status_code, 404)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO descuentos (id_descuento, des_descripcion, des_valor, estado_des) "
                "VALUES ('DES-999999', 'Ultimo concepto', 0, 'ACT')"
            )
        with self.assertRaises(HTTPException) as error:
            postgres_nomina_catalogos.crear("descuentos", self.item("Nuevo concepto"), "U1", None)
        self.assertEqual(error.exception.status_code, 409)

    def test_http_permissions_for_edit_deactivate_and_reactivate(self):
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_TALENTO_HUMANO"}]) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            for kind in ("bonificaciones", "descuentos"):
                path = f"/api/nomina/{kind}"
                payload = {"nombre": "Concepto prueba", "valor": 12.34}
                response = client.post(path, json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                item_id = response.json()["id"]
                self.assertTrue(client.get("/api/capabilities").json()["payrollCatalogUpdates"])
                self.assertEqual(client.put(f"{path}/{item_id}", json=payload).status_code, 200)
                self.assertEqual(client.put(f"{path}/{item_id}", json={**payload, "estado": "INA"}).status_code, 403)
                self.assertEqual(client.delete(f"{path}/{item_id}").status_code, 403)
                for role in ("Auxiliar_TALENTO_HUMANO", "Jefe_TALENTO_HUMANO", "Operativo_VENTAS"):
                    active.return_value = [{"rol_nombre": role}]
                    self.assertEqual(client.post(path, json=payload).status_code, 403)
                    self.assertEqual(client.put(f"{path}/{item_id}", json=payload).status_code, 403)
                active.return_value = [{"rol_nombre": "Jefe_TALENTO_HUMANO"}]
                self.assertEqual(client.delete(f"{path}/{item_id}").status_code, 200)
                active.return_value = [{"rol_nombre": "Operativo_TALENTO_HUMANO"}]
                self.assertEqual(client.put(f"{path}/{item_id}", json=payload).status_code, 200)
            active.return_value = [{"rol_nombre": "Administrador"}]
            self.assertEqual(client.post("/api/nomina/bonificaciones", json={"nombre": "Otro concepto", "valor": 0}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
