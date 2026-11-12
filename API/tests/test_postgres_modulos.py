import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import postgres_modulos


class ModuleHttpTests(unittest.TestCase):
    def test_payroll_lines_are_grouped_by_payment_and_employee(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [{"id": "P1", "employeeId": "E1"}, {"id": "P1", "employeeId": "E2"}],
            [{"pagoId": "P1", "employeeId": "E1", "bonusId": "B1", "amount": 10},
             {"pagoId": "P1", "employeeId": "E2", "bonusId": "B2", "amount": 20}],
            [{"pagoId": "P1", "employeeId": "E2", "deductionId": "D1", "amount": 5}],
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with patch("postgres_modulos.connect_postgres") as connect:
            connect.return_value.__enter__.return_value = connection
            payrolls = postgres_modulos.listar("nomina")
        self.assertEqual(payrolls[0]["bonusLines"], [{"bonusId": "B1", "amount": 10}])
        self.assertEqual(payrolls[0]["deductionLines"], [])
        self.assertEqual(payrolls[1]["bonusLines"], [{"bonusId": "B2", "amount": 20}])
        self.assertEqual(payrolls[1]["deductionLines"], [{"deductionId": "D1", "amount": 5}])

    def test_read_permissions_and_unmigrated_writes(self):
        roles = [{"rol_nombre": "Operativo_INVENTARIOS"}]
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=roles) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             patch("postgres_modulos.listar", return_value=[]) as listar, \
             TestClient(main.app, headers=headers) as client:
            self.assertEqual(client.get("/api/ajustes").status_code, 200)
            listar.assert_called_with("ajustes")
            self.assertEqual(client.get("/api/empleados").status_code, 403)
            self.assertEqual(client.get("/api/contabilidad/cuentas").status_code, 403)
            active.return_value = [{"rol_nombre": "Auxiliar_TALENTO_HUMANO"}]
            self.assertEqual(client.get("/api/empleados/E1/cargas").status_code, 200)
            listar.assert_called_with("cargas", "E1")
            self.assertEqual(client.get("/api/nomina/descuentos").status_code, 200)
            self.assertEqual(client.get("/api/nomina").status_code, 200)
            self.assertEqual(client.get("/api/contabilidad/bancos").status_code, 403)
            active.return_value = [{"rol_nombre": "Auxiliar_CONTABILIDAD"}]
            self.assertEqual(client.get("/api/contabilidad/asientos").status_code, 200)
            self.assertEqual(client.get("/api/empleados").status_code, 403)


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL local aislado.")
class SchemaQueriesTests(unittest.TestCase):
    def test_queries_execute_against_cloned_schema_and_expected_shapes(self):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")
        expected = {
            "ajustes": {"id", "productId", "productName", "type"},
            "empleados": {"id", "departmentId", "cargoId", "birthDate", "familyDependents"},
            "historial_cargos": {"cargoId", "cargoNombre", "fechaInicio", "fechaFin"},
            "cargas": {"id", "fechaNacimiento", "estadoCivil"},
            "centros_costos": {"id", "idDepartamento", "presupuestoMensual"},
            "cuentas": {"id", "accountTypeLabel", "balance"},
            "asiento_lineas": {"asientoId", "accountId", "debit", "credit"},
            "nomina": {"id", "employeeId", "employeeName", "baseSalary", "status"},
            "nomina_bonos": {"pagoId", "employeeId", "bonusId", "amount"},
            "nomina_descuentos": {"pagoId", "employeeId", "deductionId", "amount"},
        }
        with psycopg.connect(DSN) as conn:
            conn.execute("BEGIN READ ONLY")
            with conn.cursor(row_factory=dict_row) as cursor:
                for kind, query in postgres_modulos.QUERIES.items():
                    with self.subTest(kind=kind):
                        params = ("EMP-TEST",) if kind in {"historial_cargos", "cargas"} else ()
                        cursor.execute(query, params)
                        names = {column.name for column in cursor.description}
                        self.assertTrue(expected.get(kind, {"id"}) <= names, (kind, names))
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
