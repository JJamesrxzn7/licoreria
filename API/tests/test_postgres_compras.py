import os
import sys
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import postgres_compras


class PostgresPurchasesTests(unittest.TestCase):
    def setUp(self):
        self.cursor = MagicMock()
        self.connection = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connector = patch("postgres_compras.connect_postgres")
        self.connect = self.connector.start()
        self.connect.return_value.__enter__.return_value = self.connection
        self.addCleanup(self.connector.stop)

    def create(self):
        return postgres_compras.crear_compra(
            "P1", datetime(2027, 1, 1), Decimal("12.5"),
            [("PRO1", 2, Decimal("10"))], Decimal("20.00"),
            Decimal("2.50"), Decimal("22.50"), "U1", "127.0.0.1",
        )

    def test_creation_uses_requested_rate_and_verifies_totals(self):
        self.cursor.fetchall.side_effect = [[("COM-000001",)], [("PRO1",)]]
        self.cursor.fetchone.side_effect = [(1,), (Decimal("20.00"), Decimal("2.50"), Decimal("22.50"))]
        result = self.create()
        self.assertEqual(result["id"], "COM-000002")
        self.assertEqual(result["total"], "22.50")
        calls = self.cursor.execute.call_args_list
        self.assertTrue(any("pg_advisory_xact_lock" in str(call) for call in calls))
        self.assertTrue(any("oc_tasaiva" in str(call) and "12.5" in str(call) for call in calls))

    def test_total_mismatch_fails_transaction(self):
        self.cursor.fetchall.side_effect = [[], [("PRO1",)]]
        self.cursor.fetchone.side_effect = [(1,), (Decimal("40"), Decimal("5"), Decimal("45"))]
        with self.assertRaises(HTTPException) as raised:
            self.create()
        self.assertEqual(raised.exception.status_code, 500)
        self.connect.return_value.__exit__.assert_called_once()

    def test_incomplete_receipt_does_not_change_data(self):
        self.cursor.fetchone.return_value = ("PEN",)
        self.cursor.fetchall.return_value = [("PRO1", 2, 0), ("PRO2", 1, 0)]
        with self.assertRaises(HTTPException) as raised:
            postgres_compras.confirmar_recepcion("R1", [("PRO1", 2, "")], "U1", None)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertFalse(any("UPDATE productos" in str(call) for call in self.cursor.execute.call_args_list))

    def test_http_action_matrix_is_enforced(self):
        token = main.create_auth_token("U1")
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "idProveedor": "P1", "fechaEntrega": "2027-01-01", "tasaIVA": 12.5,
            "items": [{"idProducto": "PRO1", "cantidad": 2, "costoUnitario": 10}],
        }
        roles = [{"id_rol": "R1", "rol_nombre": "Operativo_COMPRAS"}]
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=roles), \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             patch("postgres_compras.crear_compra", return_value={"id": "COM-1"}) as create, \
             TestClient(main.app, headers=headers) as client:
            response = client.post("/api/compras", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"id": "COM-1"})
            create.assert_called_once()
            self.assertEqual(client.post("/api/compras/COM-1/aprobar").status_code, 403)
            self.assertEqual(client.post("/api/compras/COM-1/anular").status_code, 403)

    def test_http_purchase_approval_and_cancellation_follow_role_matrix(self):
        token = main.create_auth_token("U1")
        headers = {"Authorization": "Bearer " + token}
        approve_result = {"id": "COM-1", "estado": "APR"}
        cancel_result = {"id": "COM-2", "estado": "ANU"}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles") as active_roles, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_compras.cambiar_estado_compra", side_effect=[approve_result, cancel_result]) as change_state, \
             TestClient(main.app, headers=headers) as client:
            active_roles.return_value = [{"id_rol": "R1", "rol_nombre": "Auxiliar_COMPRAS"}]
            approved = client.post("/api/compras/COM-1/aprobar")
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json(), approve_result)
            change_state.assert_called_once_with("COM-1", True, "U1", "testclient")

            active_roles.return_value = [{"id_rol": "R2", "rol_nombre": "Jefe_COMPRAS"}]
            cancelled = client.post("/api/compras/COM-2/anular")
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json(), cancel_result)
            change_state.assert_called_with("COM-2", False, "U1", "testclient")

            active_roles.return_value = [{"id_rol": "R3", "rol_nombre": "Operativo_COMPRAS"}]
            self.assertEqual(client.post("/api/compras/COM-3/aprobar").status_code, 403)
            self.assertEqual(client.post("/api/compras/COM-3/anular").status_code, 403)


if __name__ == "__main__":
    unittest.main()
