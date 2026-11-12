import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import postgres_maestros


class MaestrosTests(unittest.TestCase):
    def test_http_module_isolation(self):
        headers = {"Authorization": f"Bearer {main.create_auth_token('U1')}"}
        roles = [{"id_rol": "R1", "rol_nombre": "Operativo_VENTAS"}]
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=roles), \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             patch("postgres_maestros.listar", return_value=[{"id": "C1"}]) as listar, \
             TestClient(main.app, headers=headers) as client:
            response = client.get("/api/clientes")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [{"id": "C1"}])
            listar.assert_called_once_with("clientes")
            self.assertEqual(client.get("/api/proveedores").status_code, 403)
            self.assertEqual(client.get("/api/productos").status_code, 200)
            listar.assert_called_with("productos", include_cost=False)


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL aislado.")
class MaestrosRealSchemaTests(unittest.TestCase):
    def test_query_columns_match_cloned_schema(self):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")
        expected = {
            "productos": {"id", "name", "sku", "minStock", "buyUnitId", "sellUnitId", "purchaseFactor", "sellFactor", "factorConversion", "shelfId"},
            "clientes": {"id", "ciRuc", "creditLimit", "creditUsed", "discountRate"},
            "proveedores": {"id", "ruc", "name", "cityId"},
        }
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cursor:
                cursor.execute("BEGIN READ ONLY")
                for name, query in postgres_maestros.QUERIES.items():
                    with self.subTest(name=name):
                        cursor.execute("SELECT * FROM (" + query + ") AS q LIMIT 0")
                        self.assertTrue(expected[name].issubset({column.name for column in cursor.description}))
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
