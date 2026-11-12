import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import postgres_comerciales
import main


class PostgresDocumentTests(unittest.TestCase):
    def test_purchase_headers_group_details_and_preserve_document_tax_rate(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [
                {"id": "COM-1", "subtotal": Decimal("100.00"), "iva": Decimal("15.00"), "tasaIVA": Decimal("15")},
                {"id": "COM-2", "subtotal": Decimal("0"), "iva": Decimal("0"), "tasaIVA": Decimal("12.5")},
            ],
            [
                {"compraId": "COM-1", "productoId": "PRO-1", "cantidad": 2},
                {"compraId": "COM-1", "productoId": "PRO-2", "cantidad": 3},
            ],
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with patch("postgres_comerciales.connect_postgres") as connect:
            connect.return_value.__enter__.return_value = connection
            result = postgres_comerciales.listar_documentos("compras")
        self.assertEqual(result[0]["tasaIVA"], Decimal("15.00"))
        self.assertEqual(result[1]["tasaIVA"], Decimal("12.5"))
        self.assertEqual(result[1]["items"], [])
        self.assertEqual(result[0]["items"], [
            {"productoId": "PRO-1", "cantidad": 2},
            {"productoId": "PRO-2", "cantidad": 3},
        ])

    def test_each_document_type_uses_its_own_detail_key(self):
        for kind, key in (
            ("ventas", "facturaId"), ("recepciones", "reciboId"), ("entregas", "entregaId")
        ):
            with self.subTest(kind=kind):
                cursor = MagicMock()
                cursor.fetchall.side_effect = [[{"id": "1"}], [{key: "1", "productId": "P1"}]]
                connection = MagicMock()
                connection.cursor.return_value.__enter__.return_value = cursor
                with patch("postgres_comerciales.connect_postgres") as connect:
                    connect.return_value.__enter__.return_value = connection
                    result = postgres_comerciales.listar_documentos(kind)
                self.assertEqual(result, [{"id": "1", "items": [{"productId": "P1"}]}])

    def test_endpoints_apply_module_authorization(self):
        roles = [{"id_rol": "R1", "rol_nombre": "Operativo_VENTAS"}]
        headers = {"Authorization": f"Bearer {main.create_auth_token('USR-TEST')}"}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=roles), \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             patch("postgres_ventas.listar_ventas", return_value=[{"id": "FAC1"}]) as documents, \
             TestClient(main.app, headers=headers) as client:
            response = client.get("/api/ventas")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [{"id": "FAC1"}])
            documents.assert_called_once_with()
            self.assertEqual(client.get("/api/compras").status_code, 403)
            self.assertEqual(client.get("/api/recepciones").status_code, 403)


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL aislado.")
class PostgresRealSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Las pruebas PostgreSQL requieren un servidor local.")
        if config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Las pruebas requieren la base licoreria_api_test.")

    def test_all_queries_match_restored_schema_and_expected_aliases(self):
        aliases = {
            "compras": ({"id", "proveedorId", "fechaEntrega", "subtotal", "iva", "tasaIVA"}, {"compraId", "productoId", "costoUnitario"}),
            "ventas": ({"id", "customerId", "customerName", "taxRate", "paymentMethod"}, {"facturaId", "productId", "productName"}),
            "recepciones": ({"id", "poId", "status"}, {"reciboId", "productId", "expectedQty", "receivedQty"}),
            "entregas": ({"id", "invoiceId", "status"}, {"entregaId", "productId", "expectedQty", "deliveredQty"}),
        }
        with psycopg.connect(DSN) as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("BEGIN READ ONLY")
                for query in postgres_comerciales.PURCHASE_CATALOG_QUERIES.values():
                    cursor.execute("SELECT * FROM (" + query + ") AS q LIMIT 0")
                for kind, (header, detail, _) in postgres_comerciales.DOCUMENT_QUERIES.items():
                    for query, required in zip((header, detail), aliases[kind]):
                        with self.subTest(kind=kind, columns=required):
                            cursor.execute("SELECT * FROM (" + query + ") AS q LIMIT 0")
                            self.assertTrue(required.issubset({column.name for column in cursor.description}))
            conn.rollback()

    def test_document_queries_return_header_and_details_from_postgres(self):
        schema = "api_docs_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            with psycopg.connect(DSN, options=f"-c search_path={schema}") as conn:
                conn.execute("""
                    CREATE TABLE proveedores (id_proveedor text, prv_nombre text, prv_ruc_ced text, estado_prv text);
                    CREATE TABLE productos (id_producto text, pro_descripcion text, pro_valor_compra numeric,
                                            pro_precio_venta numeric, pro_saldo_final integer, estado_prod text);
                    CREATE TABLE clientes (id_cliente text, cli_nombre text);
                    CREATE TABLE compras (id_compra text, id_proveedor text, oc_fecha timestamp, oc_fechaentrega timestamp,
                                          oc_subtotal numeric, oc_iva numeric, oc_total numeric, estado_oc text, oc_tasaiva numeric);
                    CREATE TABLE proxoc (id_compra text, id_producto text, pxo_cantidad integer,
                                         pxo_valor numeric, pxo_subtotal numeric, estado_pxoc text);
                    CREATE TABLE facturas (id_factura text, id_cliente text, fac_fecha timestamp, fac_subtotal numeric,
                                           fac_descuento numeric, fac_iva numeric, fac_total numeric,
                                           fac_formapago text, estado_fac text);
                    CREATE TABLE proxfac (id_factura text, id_producto text, pxf_cantidad integer,
                                          pxf_precio numeric, pxf_subtotal numeric);
                    CREATE TABLE recepciones (id_recibo text, id_compra text, rec_fechahora timestamp,
                                              estado_rec text, rec_descripcion text);
                    CREATE TABLE proxrec (id_recibo text, id_producto text, pxr_cantidad integer,
                                          pxr_qty_recibida integer, pxr_motivo text);
                    CREATE TABLE entregas (id_entrega text, id_factura text, ent_fechahora timestamp,
                                           estado_ent text, ent_descripcion text);
                    CREATE TABLE proxent (id_entrega text, id_producto text, pxe_cantidad integer,
                                          pxe_qty_entregada integer, pxe_motivo text);
                    INSERT INTO proveedores VALUES ('S1', 'Proveedor', '123', 'ACT');
                    INSERT INTO productos VALUES ('P1', 'Producto', 10, 20, 7, 'ACT');
                    INSERT INTO clientes VALUES ('C1', 'Cliente');
                    INSERT INTO compras VALUES ('OC1', 'S1', NOW(), NOW(), 20, 3, 23, 'ABI', 15);
                    INSERT INTO proxoc VALUES ('OC1', 'P1', 2, 10, 20, 'ABI');
                    INSERT INTO facturas VALUES ('F1', 'C1', NOW(), 40, 0, 6, 46, 'EFE', 'ABI');
                    INSERT INTO proxfac VALUES ('F1', 'P1', 2, 20, 40);
                    INSERT INTO recepciones VALUES ('R1', 'OC1', NOW(), 'PEN', 'Recepción');
                    INSERT INTO proxrec VALUES ('R1', 'P1', 2, 1, 'Faltante');
                    INSERT INTO entregas VALUES ('E1', 'F1', NOW(), 'PEN', 'Entrega');
                    INSERT INTO proxent VALUES ('E1', 'P1', 2, 2, NULL);
                """)
            def connect():
                return psycopg.connect(DSN, options=f"-c search_path={schema}")
            with patch("postgres_comerciales.connect_postgres", connect):
                catalogs = postgres_comerciales.listar_catalogos_compras()
                purchase = postgres_comerciales.listar_documentos("compras")[0]
                sale = postgres_comerciales.listar_documentos("ventas")[0]
                receipt = postgres_comerciales.listar_documentos("recepciones")[0]
                delivery = postgres_comerciales.listar_documentos("entregas")[0]
            self.assertEqual(catalogs["proveedores"][0]["id"], "S1")
            self.assertEqual(catalogs["productos"][0]["stock"], 7)
            self.assertEqual(purchase["items"][0]["productoId"], "P1")
            self.assertEqual(purchase["tasaIVA"], Decimal("15.00"))
            self.assertEqual(sale["customerId"], "C1")
            self.assertEqual(sale["items"][0]["productId"], "P1")
            self.assertEqual(receipt["items"][0]["diff"], -1)
            self.assertEqual(delivery["items"][0]["diff"], 0)
        finally:
            with psycopg.connect(DSN, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
