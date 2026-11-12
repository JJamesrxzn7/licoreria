import os
import re
import shutil
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import postgres_asientos


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class AsientosRealSchemaTests(unittest.TestCase):
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
        self.schema = "api_asientos_" + uuid4().hex
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
                INSERT INTO cuentas (id_cuenta,cue_descripcion,cue_tipo,cue_debe00,cue_haber00,estado_cue)
                    VALUES ('1.1','Caja','DET',5,0,'ACT'), ('1.2','Banco','DET',0,8,'ACT'),
                           ('2','Mayor','MAY',0,0,'ACT'), ('3','Inactiva','DET',0,0,'INA');
            """)
        patcher = patch("postgres_asientos.connect_postgres", self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def payload(self):
        return {"descripcion": "Traspaso prueba", "fecha": "2025-01-02", "lines": [
            {"idCuenta": "1.1", "debe": "12.34", "haber": 0},
            {"idCuenta": "1.2", "debe": 0, "haber": "12.34"},
        ]}

    def client_context(self):
        return (
            patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}),
            patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_CONTABILIDAD"}]),
            patch("postgres_auth.session_revoked", return_value=False),
            patch("postgres_catalogos.registrar_auditoria"),
        )

    def test_create_header_details_audit_and_unchanged_balances(self):
        environment, roles, revoked, audit = self.client_context()
        with environment, roles, revoked, audit, TestClient(
            main.app, headers={"Authorization": "Bearer " + main.create_auth_token("U1")}
        ) as client:
            response = client.post("/api/contabilidad/asientos", json=self.payload())
            self.assertEqual(response.status_code, 200, response.text)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT trim(user_id), trim(estado_asi), asi_total_debe, asi_total_haber, asi_fechahora "
                "FROM asientos WHERE id_asiento=%s", (response.json()["id"],)
            ).fetchone()
            self.assertEqual(tuple(row[:4]), ("U1", "ABI", Decimal("12.34"), Decimal("12.34")))
            self.assertEqual(str(row[4]), "2025-01-02 12:00:00")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ctaxasi WHERE estado_cxa='ABI'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT cue_debe00,cue_haber00 FROM cuentas WHERE id_cuenta='1.1'").fetchone(), (5, 0))
            self.assertEqual(conn.execute("SELECT cue_debe00,cue_haber00 FROM cuentas WHERE id_cuenta='1.2'").fetchone(), (0, 8))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE id_usuario='U1' AND log_accion='INSERT' "
                "AND log_tablaafectada IN ('ASIENTOS','CTAXASI')"
            ).fetchone()[0], 3)

    def test_invalid_lines_accounts_and_limits(self):
        cases = []
        for account in ("2", "3", "9", "1.1"):
            payload = self.payload()
            payload["lines"][1]["idCuenta"] = account
            cases.append(payload)
        payload = self.payload()
        payload["lines"][1]["haber"] = "12.33"
        cases.append(payload)
        payload = self.payload()
        payload["lines"][0]["debe"] = "100000.00"
        payload["lines"][1]["haber"] = "100000.00"
        cases.append(payload)
        environment, roles, revoked, audit = self.client_context()
        with environment, roles, revoked, audit, TestClient(
            main.app, headers={"Authorization": "Bearer " + main.create_auth_token("U1")}
        ) as client:
            for payload in cases:
                response = client.post("/api/contabilidad/asientos", json=payload)
                self.assertEqual(response.status_code, 422, response.text)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)

    def test_maximum_amount_without_explicit_date(self):
        payload = self.payload()
        del payload["fecha"]
        payload["lines"][0]["debe"] = "99999.99"
        payload["lines"][1]["haber"] = "99999.99"
        environment, roles, revoked, audit = self.client_context()
        with environment, roles, revoked, audit, TestClient(
            main.app, headers={"Authorization": "Bearer " + main.create_auth_token("U1")}
        ) as client:
            response = client.post("/api/contabilidad/asientos", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
        with self.connect() as conn:
            total, date_is_current = conn.execute(
                "SELECT asi_total_debe, asi_fechahora::date = CURRENT_DATE FROM asientos WHERE id_asiento=%s",
                (response.json()["id"],),
            ).fetchone()
            self.assertEqual(total, Decimal("99999.99"))
            self.assertTrue(date_is_current)

    def test_audit_failure_rolls_back(self):
        with self.connect() as conn:
            conn.execute("DROP TABLE log_auditoria CASCADE")
        environment, roles, revoked, audit = self.client_context()
        with environment, roles, revoked, audit, TestClient(
            main.app, headers={"Authorization": "Bearer " + main.create_auth_token("U1")}
        ) as client:
            self.assertEqual(client.post("/api/contabilidad/asientos", json=self.payload()).status_code, 500)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ctaxasi").fetchone()[0], 0)

    def test_detail_failure_rolls_back_header_and_audit(self):
        with self.connect() as conn:
            conn.execute("ALTER TABLE ctaxasi ADD CONSTRAINT test_rechazar_detalle CHECK (id_cuenta <> '1.2')")
        environment, roles, revoked, audit = self.client_context()
        with environment, roles, revoked, audit, TestClient(
            main.app, headers={"Authorization": "Bearer " + main.create_auth_token("U1")}
        ) as client:
            self.assertEqual(client.post("/api/contabilidad/asientos", json=self.payload()).status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ctaxasi").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE log_tablaafectada IN ('ASIENTOS','CTAXASI')"
            ).fetchone()[0], 0)

    def test_permissions_and_workflow_blocked(self):
        environment, roles, revoked, audit = self.client_context()
        with environment, roles as active, revoked, audit, TestClient(
            main.app, headers={"Authorization": "Bearer " + main.create_auth_token("U1")}
        ) as client:
            response = client.post("/api/contabilidad/asientos", json=self.payload())
            self.assertEqual(response.status_code, 200, response.text)
            entry_id = response.json()["id"]
            for role in ("Auxiliar_CONTABILIDAD", "Jefe_CONTABILIDAD", "Operativo_VENTAS"):
                active.return_value = [{"rol_nombre": role}]
                self.assertEqual(client.post("/api/contabilidad/asientos", json=self.payload()).status_code, 403)
            active.return_value = [{"rol_nombre": "Auxiliar_CONTABILIDAD"}]
            self.assertEqual(client.post(f"/api/contabilidad/asientos/{entry_id}/aprobar").status_code, 503)
            active.return_value = [{"rol_nombre": "Jefe_CONTABILIDAD"}]
            self.assertEqual(client.post(f"/api/contabilidad/asientos/{entry_id}/anular").status_code, 503)
            active.return_value = [{"rol_nombre": "Administrador"}]
            self.assertEqual(client.post("/api/contabilidad/asientos", json=self.payload()).status_code, 200)


if __name__ == "__main__":
    unittest.main()
