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
import postgres_empleados


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class EmpleadosRealSchemaTests(unittest.TestCase):
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
        self.schema = "api_empleados_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            try:
                conn.execute(re.sub(r"\bpublic\b", self.schema, self.dump), prepare=False)
            except psycopg.Error:
                conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
                raise
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO departamentos (id_departamento, dep_nombre, estado_dep)
                    VALUES ('D1', 'Ventas', 'ACT'), ('D2', 'Inactivo', 'INA');
                INSERT INTO cargos (id_cargo, cgo_descripcion, estado_cgo)
                    VALUES ('C1', 'Vendedor', 'ACT'), ('C2', 'Inactivo', 'INA');
                INSERT INTO empleados (id_empleado, id_departamento, emp_cedula, emp_apellido1,
                    emp_nombre1, emp_fechanacimiento, emp_sueldo, estado_emp)
                    VALUES ('E1', 'D1', '1234567890', 'Prueba', 'Usuario', '1990-01-01', 500, 'ACT');
                INSERT INTO usuarios (id_usuario, id_empleado, usr_username, usr_passwordhash, estado_usr)
                    VALUES ('U1', 'E1', 'prueba', 'x', 'ACT');
            """)
        patcher = patch("postgres_empleados.connect_postgres", self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def employee(self, ci="1710000017", **overrides):
        values = {
            "ci": ci, "nombre1": "Ana", "apellido1": "Prueba", "sexo": "F",
            "fechaNacimiento": "1990-01-01", "sueldo": "500.00",
            "idDepartamento": "D1", "idCargo": "C1", "email": "ana@example.com",
        }
        values.update(overrides)
        return main.EmployeeInput(**values)

    def test_create_employee_and_optional_job_history_audited(self):
        result = postgres_empleados.crear_empleado(self.employee(), "U1", "127.0.0.1")
        self.assertEqual(result["id"], "EMP-000001")
        with self.connect() as conn:
            row = conn.execute(
                """SELECT TRIM(id_empleado), TRIM(id_departamento), TRIM(emp_cedula),
                          TRIM(emp_nombre1), TRIM(emp_apellido1), emp_sueldo,
                          TRIM(user_id), TRIM(estado_emp)
                   FROM empleados WHERE id_empleado = %s""",
                (result["id"],),
            ).fetchone()
            self.assertEqual(row, ("EMP-000001", "D1", "1710000017", "Ana", "Prueba", 500, "U1", "ACT"))
            self.assertEqual(conn.execute(
                "SELECT TRIM(id_cargo), TRIM(estado_cxe), TRIM(user_id) FROM cargosxempleado"
            ).fetchone(), ("C1", "ACT", "U1"))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE id_usuario='U1' "
                "AND log_tablaafectada IN ('EMPLEADOS','CARGOSXEMPLEADO') AND log_ip='127.0.0.1'"
            ).fetchone()[0], 2)

    def test_concurrent_ids_and_duplicate_identity(self):
        def create(index):
            ci = "1710000017" if index == 0 else "1710000025"
            return postgres_empleados.crear_empleado(self.employee(ci), "U1", None)["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(create, range(2))), ["EMP-000001", "EMP-000002"])
        with self.assertRaises(HTTPException) as error:
            postgres_empleados.crear_empleado(self.employee(), "U1", None)
        self.assertEqual(error.exception.status_code, 409)

    def test_reject_invalid_department_cargo_and_code_without_partial_insert(self):
        cases = [
            (self.employee(ci="1710000017", idDepartamento="MISSING"), 422),
            (self.employee(ci="1710000017", idCargo="C2"), 422),
            (self.employee(ci="1710000017", id="BAD CODE"), 422),
        ]
        for employee, status in cases:
            with self.subTest(status=status):
                with self.assertRaises(HTTPException) as error:
                    postgres_empleados.crear_empleado(employee, "U1", None)
                self.assertEqual(error.exception.status_code, status)
        with self.assertRaises(HTTPException) as error:
            postgres_empleados.crear_empleado(self.employee(ci="1710000017", id="E1"), "U1", None)
        self.assertEqual(error.exception.status_code, 409)
        result = postgres_empleados.crear_empleado(self.employee(idCargo=None), "U1", None)
        self.assertEqual(result["id"], "EMP-000001")
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM empleados").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cargosxempleado").fetchone()[0], 0)

    def test_audit_failure_rolls_back_employee_and_job(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE FUNCTION reject_audit_insert() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'test audit failure';
                END;
                $$;
                CREATE TRIGGER reject_audit_insert BEFORE INSERT ON log_auditoria
                    FOR EACH ROW EXECUTE FUNCTION reject_audit_insert();
            """, prepare=False)
        with self.assertRaises(psycopg.Error):
            postgres_empleados.crear_empleado(self.employee(), "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM empleados").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cargosxempleado").fetchone()[0], 0)

    def test_http_permissions_and_update_stays_unavailable(self):
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_TALENTO_HUMANO"}]) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            response = client.post("/api/empleados", json=self.employee().model_dump(by_alias=True, mode="json"))
            self.assertEqual(response.status_code, 200, response.text)
            employee_id = response.json()["id"]
            payload = self.employee("1710000025").model_dump(by_alias=True, mode="json")
            self.assertEqual(client.put(f"/api/empleados/{employee_id}", json=payload).status_code, 503)
            active.return_value = [{"rol_nombre": "Auxiliar_TALENTO_HUMANO"}]
            self.assertEqual(client.post("/api/empleados", json=payload).status_code, 403)
            active.return_value = [{"rol_nombre": "Jefe_TALENTO_HUMANO"}]
            self.assertEqual(client.post("/api/empleados", json=payload).status_code, 403)


if __name__ == "__main__":
    unittest.main()
