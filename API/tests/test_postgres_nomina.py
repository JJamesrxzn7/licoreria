import os
import re
import shutil
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
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
import postgres_nomina


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class NominaRealSchemaTests(unittest.TestCase):
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
        self.schema = "api_nomina_" + uuid4().hex
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
                    VALUES ('E1','D1','1234567890','Prueba','Ana','1990-01-01',500,'ACT'),
                           ('E2','D1','1234567891','Prueba','Inactiva','1990-01-01',500,'INA');
                INSERT INTO usuarios (id_usuario,id_empleado,usr_username,usr_passwordhash,estado_usr)
                    VALUES ('U1','E1','prueba','x','ACT');
                INSERT INTO bonificaciones (id_bonificacion,bon_descripcion,bon_valor,estado_bon)
                    VALUES ('BON-000001','Bono',10,'ACT'),('BON-000002','Bono inactivo',10,'INA');
                INSERT INTO descuentos (id_descuento,des_descripcion,des_valor,estado_des)
                    VALUES ('DES-000001','Descuento',5,'ACT'),('DES-000002','Descuento inactivo',5,'INA');
            """)
        patcher = patch("postgres_nomina.connect_postgres", self.connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def payroll(self, employee="E1"):
        return main.PayrollInput(
            descripcion="Nomina de prueba",
            fechaInicio="2026-01-01",
            fechaFin="2026-01-31",
            idEmpleado=employee,
            sueldoBase="100.00",
            lineasBonos=[
                {"idBonificacion": "BON-000001", "fecha": "2026-01-31", "valor": "10.00"},
                {"idBonificacion": "BON-000001", "fecha": "2026-01-31", "valor": "5.00"},
            ],
            lineasDescuentos=[
                {"idDescuento": "DES-000001", "fecha": "2026-01-31", "valor": "7.00"},
            ],
        )

    def install_approval_migration(self):
        migration = (Path(__file__).resolve().parents[1] / "migrations" /
                     "20261111_nomina_aprobacion_postgresql.sql").read_text(encoding="utf-8")
        with psycopg.connect(DSN, autocommit=True, options=f"-c search_path={self.schema}") as conn:
            conn.execute(re.sub(r"\bpublic\b", self.schema, migration), prepare=False)

    def configure_accounts(self):
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO centros_costos (id_centrocosto,id_departamento,cco_nombre,estado_cco)
                VALUES ('CC1','D1','Prueba','ACT');
                INSERT INTO cuentas (id_cuenta,cue_descripcion,cue_tipo,estado_cue)
                VALUES ('5.1.04.01','Gasto nomina','DET','ACT'),
                       ('2.1.04.01','Obligacion laboral','DET','ACT');
            """)

    def test_approval_migration_builds_balanced_gross_journal_once(self):
        self.install_approval_migration()
        self.configure_accounts()
        payment_id = postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        def approve(_):
            try:
                postgres_nomina.aprobar(payment_id, "U1", "127.0.0.1")
                return 200
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(approve, range(2))), [200, 409])
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(estado_pag) FROM pagos").fetchone()[0], "APR")
            self.assertEqual(conn.execute("SELECT trim(estado_pxe) FROM pagxemp").fetchone()[0], "APR")
            self.assertEqual(conn.execute(
                "SELECT trim(estado_asi), asi_total_debe, asi_total_haber FROM asientos"
            ).fetchone(), ("PEN", Decimal("115.00"), Decimal("115.00")))
            self.assertEqual(conn.execute(
                "SELECT trim(id_cuenta), trim(id_centrocosto), cxa_debe, cxa_haber FROM ctaxasi ORDER BY id_cuenta"
            ).fetchall(), [
                ("2.1.04.01", "CC1", Decimal("0.00"), Decimal("115.00")),
                ("5.1.04.01", "CC1", Decimal("115.00"), Decimal("0.00")),
            ])

    def test_approval_missing_configuration_rolls_back(self):
        self.install_approval_migration()
        payment_id = postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        with self.assertRaises(HTTPException) as missing_center:
            postgres_nomina.aprobar(payment_id, "U1", None)
        self.assertEqual(missing_center.exception.status_code, 409)
        with self.connect() as conn:
            conn.execute("INSERT INTO centros_costos (id_centrocosto,id_departamento,cco_nombre,estado_cco) "
                         "VALUES ('CC1','D1','Prueba','ACT')")
        with self.assertRaises(HTTPException) as missing_account:
            postgres_nomina.aprobar(payment_id, "U1", None)
        self.assertEqual(missing_account.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(estado_pag) FROM pagos").fetchone()[0], "ABI")
            self.assertEqual(conn.execute("SELECT trim(estado_pxe) FROM pagxemp").fetchone()[0], "ABI")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)

    def test_approval_with_restricted_api_grants_and_rls(self):
        self.install_approval_migration()
        self.configure_accounts()
        payment_id = postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        role = "api_payroll_" + uuid4().hex[:12]
        tables = ("pagos", "pagxemp", "asientos", "ctaxasi", "cuentas",
                  "centros_costos", "empleados", "log_auditoria")
        writable = {"pagos", "pagxemp", "asientos", "ctaxasi", "cuentas", "log_auditoria"}
        try:
            with self.connect() as conn:
                conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOBYPASSRLS").format(sql.Identifier(role)))
                conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(self.schema), sql.Identifier(role)))
                for table in tables:
                    name = sql.Identifier(table)
                    role_id = sql.Identifier(role)
                    conn.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(name))
                    conn.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(name, role_id))
                    conn.execute(sql.SQL("CREATE POLICY test_payroll_select ON {} FOR SELECT TO {} USING (true)").format(
                        name, role_id))
                    if table in writable:
                        conn.execute(sql.SQL("GRANT INSERT, UPDATE ON {} TO {}").format(name, role_id))
                        conn.execute(sql.SQL("CREATE POLICY test_payroll_insert ON {} FOR INSERT TO {} WITH CHECK (true)").format(
                            name, role_id))
                        conn.execute(sql.SQL("CREATE POLICY test_payroll_update ON {} FOR UPDATE TO {} "
                                             "USING (true) WITH CHECK (true)").format(name, role_id))

            def restricted_connection():
                conn = self.connect()
                conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
                return conn

            with patch("postgres_nomina.connect_postgres", restricted_connection):
                result = postgres_nomina.aprobar(payment_id, "U1", None)
            self.assertEqual(result["estado"], "APR")
        finally:
            with psycopg.connect(DSN, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
                conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

    def test_approval_requires_safe_migration_and_http_permission(self):
        payment_id = postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        with self.assertRaises(HTTPException) as missing:
            postgres_nomina.aprobar(payment_id, "U1", None)
        self.assertEqual(missing.exception.status_code, 503)
        self.install_approval_migration()
        self.configure_accounts()
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql", "PAYROLL_APPROVAL_ENABLED": "true"}), \
             patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_TALENTO_HUMANO"}]) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            self.assertTrue(client.get("/api/capabilities").json()["payrollApproval"])
            self.assertEqual(client.post(f"/api/nomina/{payment_id}/aprobar").status_code, 403)
            active.return_value = [{"rol_nombre": "Auxiliar_TALENTO_HUMANO"}]
            response = client.post(f"/api/nomina/{payment_id}/aprobar")
            self.assertEqual(response.status_code, 200, response.text)

    def test_create_header_details_aggregated_and_audited(self):
        result = postgres_nomina.crear(self.payroll(), "U1", "127.0.0.1")
        self.assertEqual((result["id"], result["estado"], result["neto"]), ("PAG-000001", "ABI", "108.00"))
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT trim(user_id),trim(estado_pag),pag_fecha_inicio,pag_fecha_fin FROM pagos"
            ).fetchone(), ("U1", "ABI", date(2026, 1, 1), date(2026, 1, 31)))
            self.assertEqual(conn.execute(
                "SELECT trim(id_empleado),pxe_sueldo,pxe_bonificaciones,pxe_descuentos,pxe_valor_neto,trim(estado_pxe) "
                "FROM pagxemp"
            ).fetchone(), ("E1", Decimal("100.00"), Decimal("15.00"), Decimal("7.00"), Decimal("108.00"), "ABI"))
            self.assertEqual(conn.execute(
                "SELECT trim(id_bonificacion),bxe_fecha,bxe_valor FROM bonxempxpag"
            ).fetchone(), ("BON-000001", date(2026, 1, 31), Decimal("15.00")))
            self.assertEqual(conn.execute(
                "SELECT trim(id_descuento),dxe_fecha,dxe_valor FROM desxempxpag"
            ).fetchone(), ("DES-000001", date(2026, 1, 31), Decimal("7.00")))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE id_usuario='U1' "
                "AND log_tablaafectada IN ('PAGOS','PAGXEMP','BONXEMPXPAG','DESXEMPXPAG') "
                "AND log_ip='127.0.0.1'"
            ).fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)

    def test_concurrent_id_generation(self):
        def create(_):
            return postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(create, range(2))), ["PAG-000001", "PAG-000002"])

    def test_invalid_employee_totals_catalogs_and_numeric_bounds(self):
        cases = [
            (self.payroll(employee="E2"), 404),
            (self.payroll(employee="NOEXISTE"), 404),
        ]
        negative = self.payroll()
        negative.deduction_lines = [main.PayrollDeductionLineInput(idDescuento="DES-000001", valor="200.00")]
        cases.append((negative, 422))
        invalid_bonus = self.payroll()
        invalid_bonus.bonus_lines = [main.PayrollBonusLineInput(idBonificacion="BON-000002", valor="1.00")]
        cases.append((invalid_bonus, 422))
        invalid_deduction = self.payroll()
        invalid_deduction.deduction_lines = [main.PayrollDeductionLineInput(idDescuento="DES-000002", valor="1.00")]
        cases.append((invalid_deduction, 422))
        oversized = self.payroll()
        oversized.base_salary = Decimal("50000.01")
        cases.append((oversized, 422))
        total_overflow = self.payroll()
        total_overflow.base_salary = Decimal("50000")
        total_overflow.bonus_lines = [main.PayrollBonusLineInput(idBonificacion="BON-000001", valor="50000")]
        total_overflow.deduction_lines = []
        cases.append((total_overflow, 422))
        for item, status in cases:
            with self.subTest(status=status, employee=item.employee_id):
                with self.assertRaises(HTTPException) as error:
                    postgres_nomina.crear(item, "U1", None)
                self.assertEqual(error.exception.status_code, status)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pagos").fetchone()[0], 0)

    def test_audit_and_detail_failure_roll_back_everything(self):
        with self.connect() as conn:
            conn.execute("ALTER TABLE bonxempxpag ADD CONSTRAINT test_rechazar_bono CHECK (id_bonificacion <> 'BON-000001')")
        with self.assertRaises(psycopg.Error):
            postgres_nomina.crear(self.payroll(), "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pagos").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pagxemp").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM log_auditoria WHERE log_tablaafectada='PAGOS'").fetchone()[0], 0)

    def test_annul_open_payroll_is_atomic_and_serialized(self):
        payment_id = postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        def annul(_):
            try:
                postgres_nomina.anular(payment_id, "U1", "127.0.0.1")
                return 200
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(annul, range(2))), [200, 409])
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(estado_pag) FROM pagos").fetchone()[0], "ANU")
            self.assertEqual(conn.execute("SELECT trim(estado_pxe) FROM pagxemp").fetchone()[0], "ANU")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE log_tablaafectada IN ('PAGOS', 'PAGXEMP') "
                "AND log_accion = 'UPDATE' AND log_ip = '127.0.0.1'"
            ).fetchone()[0], 2)
        with self.assertRaises(HTTPException) as missing:
            postgres_nomina.anular("PAG-999999", "U1", None)
        self.assertEqual(missing.exception.status_code, 404)

    def test_annul_audit_failure_rolls_back(self):
        payment_id = postgres_nomina.crear(self.payroll(), "U1", None)["id"]
        with self.connect() as conn:
            conn.execute("ALTER TABLE pagxemp ADD CONSTRAINT test_no_anular CHECK (estado_pxe <> 'ANU')")
        with self.assertRaises(psycopg.Error):
            postgres_nomina.anular(payment_id, "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT trim(estado_pag) FROM pagos").fetchone()[0], "ABI")
            self.assertEqual(conn.execute("SELECT trim(estado_pxe) FROM pagxemp").fetchone()[0], "ABI")
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM log_auditoria WHERE log_tablaafectada='PAGOS' AND log_accion='UPDATE'"
            ).fetchone()[0], 0)

    def test_http_permissions_and_unmigrated_workflow(self):
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=[{"rol_nombre": "Operativo_TALENTO_HUMANO"}]) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            payload = self.payroll().model_dump(by_alias=True, mode="json")
            response = client.post("/api/nomina", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            payment_id = response.json()["id"]
            active.return_value = [{"rol_nombre": "Auxiliar_TALENTO_HUMANO"}]
            self.assertEqual(client.post("/api/nomina", json=payload).status_code, 403)
            self.assertEqual(client.post(f"/api/nomina/{payment_id}/aprobar").status_code, 503)
            self.assertEqual(client.post(f"/api/nomina/{payment_id}/anular").status_code, 403)
            active.return_value = [{"rol_nombre": "Jefe_TALENTO_HUMANO"}]
            self.assertEqual(client.post(f"/api/nomina/{payment_id}/anular").status_code, 200)
            self.assertEqual(client.post(f"/api/nomina/{payment_id}/anular").status_code, 409)
            active.return_value = [{"rol_nombre": "Operativo_TALENTO_HUMANO"}]
            self.assertEqual(client.put(f"/api/nomina/{payment_id}", json=payload).status_code, 503)
            self.assertEqual(client.delete(f"/api/nomina/{payment_id}").status_code, 403)


if __name__ == "__main__":
    unittest.main()
