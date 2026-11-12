import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import postgres_ventas as ventas
import main

DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")
MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "20261108_ventas_postgresql.sql"


def sale(qty=2, rate="12.50", discount="0.01", items=None):
    return SimpleNamespace(
        customer_id="C1", tax_rate=Decimal(rate), discount_amount=Decimal(discount),
        payment_method="CASH", description="Venta prueba", installments=1,
        items=items if items is not None else [
            SimpleNamespace(product_id="P1", quantity=qty, unit_price=Decimal("3.33"))
        ],
    )


def delivery(qty, reason="", pid="P1"):
    return SimpleNamespace(items=[SimpleNamespace(product_id=pid, delivered_qty=qty, reason=reason)])


def create(order, key=None):
    return ventas.crear_venta(order, "U1", "127.0.0.1", request_id=key or uuid4().hex)


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL local aislado.")
class VentasRealSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")
        pg_dump = os.getenv("LICORERIA_TEST_PG_DUMP") or shutil.which("pg_dump")
        if not pg_dump:
            raise unittest.SkipTest("pg_dump no está disponible para clonar el esquema.")
        result = subprocess.run(
            [pg_dump, "--schema-only", "--no-owner", "--no-acl", "--schema=public", "--dbname", DSN],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            timeout=30,
        )
        cls.dump = re.sub(r"(?m)^\\(?:un)?restrict[^\n]*\n", "", result.stdout)

    def setUp(self):
        self.schema = "api_ventas_" + uuid4().hex
        # Sólo metadatos: pg_dump --schema-only. Se sustituyen calificadores public
        # antes de ejecutar el DDL y se elimina exclusivamente este esquema.
        clone = re.sub(r"\bpublic\b", self.schema, self.dump)
        with psycopg.connect(DSN, autocommit=True) as conn:
            try:
                conn.execute(clone, prepare=False)
            except Exception:
                conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
                raise
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            migration_applied = conn.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'facturas'
                      AND column_name = 'fac_tasa_iva'
                ) AND to_regclass('ventas_control') IS NOT NULL
            """).fetchone()[0]
            if not migration_applied:
                conn.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)
            conn.execute("""
                INSERT INTO ciudades (id_ciudad,ciu_descripcion) VALUES ('CIT','Quito');
                INSERT INTO clientes (id_cliente,cli_nombre,cli_ruc_ced,id_ciudad,estado_cli)
                    VALUES ('C1','Cliente prueba','1234567890','CIT','ACT');
                INSERT INTO departamentos (id_departamento,dep_nombre,estado_dep) VALUES ('D1','Ventas','ACT');
                INSERT INTO empleados (id_empleado,id_departamento,emp_cedula,emp_apellido1,
                    emp_nombre1,emp_fechanacimiento,emp_sueldo,estado_emp)
                    VALUES ('E1','D1','1234567890','Prueba','Ana','1990-01-01',500,'ACT');
                INSERT INTO usuarios (id_usuario,id_empleado,usr_username,usr_passwordhash,estado_usr)
                    VALUES ('U1','E1','prueba','x','ACT');
                INSERT INTO unidades_medidas (id_unidad_medida,um_descripcion,um_factorconversion)
                    VALUES ('UND','Unidad',1);
                INSERT INTO categorias (id_categoria,cat_nombre,estado_cat) VALUES ('CA','Categoria','ACT');
                INSERT INTO marcas (id_marca,mar_nombre,estado_mar) VALUES ('MA','Marca','ACT');
                INSERT INTO productos (id_producto,id_categoria,id_marca,pro_descripcion,pro_um_compra,
                    pro_um_venta,pro_valor_compra,pro_precio_venta,pro_saldo_inicial,pro_qty_ingresos,
                    pro_qty_egresos,pro_qty_ajustes,pro_saldo_final,estado_prod)
                    VALUES ('P1','CA','MA','Producto','UND','UND',1,3.33,10,0,0,0,10,'ACT'),
                           ('P2','CA','MA','Producto 2','UND','UND',1,3.33,1,0,0,0,1,'ACT');
            """)
        self.connection_patch = patch("postgres_ventas.connect_postgres", self.connect)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def connect(self):
        return psycopg.connect(
            DSN, connect_timeout=5,
            options=f"-c search_path={self.schema} -c lock_timeout=5000 -c statement_timeout=15000",
        )

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def test_create_approve_partial_then_complete_no_double_stock(self):
        result = create(sale())
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT fac_subtotal,fac_descuento,fac_tasa_iva,fac_iva,fac_total FROM facturas"
            ).fetchone(), (Decimal("6.66"), Decimal("0.01"), Decimal("12.50"), Decimal("0.83"), Decimal("7.48")))
            self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (8, 2))
        invoice = ventas.listar_ventas()[0]
        self.assertEqual(invoice["taxRate"], Decimal("12.50"))
        self.assertEqual(invoice["tax"], Decimal("0.83"))
        with self.assertRaises(ventas.VentaError) as error:
            ventas.confirmar_entrega(result["deliveryId"], delivery(1, "Pendiente"), "U1")
        self.assertEqual(error.exception.status_code, 409)
        ventas.aprobar_factura(result["id"], "U1")
        partial = ventas.confirmar_entrega(result["deliveryId"], delivery(1, "Pendiente"), "U1")
        self.assertEqual(partial["estado"], "PEN")
        with self.assertRaises(ventas.VentaError):
            ventas.anular_factura(result["id"], "U1")
        with self.assertRaises(ventas.VentaError):
            ventas.confirmar_entrega(result["deliveryId"], delivery(1, "Pendiente"), "U1")
        completed = ventas.confirmar_entrega(result["deliveryId"], delivery(2), "U1")
        self.assertEqual(completed["estado"], "ENT")
        with self.assertRaises(ventas.VentaError):
            ventas.confirmar_entrega(result["deliveryId"], delivery(2), "U1")
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (8, 2))
            self.assertEqual(conn.execute("SELECT count(*) FROM entregas").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM asientos WHERE estado_asi='PEN'").fetchone()[0], 1)

    def test_sales_control_rls_allows_api_role_with_explicit_table_grants(self):
        first = create(sale(), key="api-role-request-0001")
        second = create(sale(), key="api-role-request-0002")
        role_id = sql.Identifier("api_sales_" + uuid4().hex[:12])
        try:
            with psycopg.connect(DSN, autocommit=True) as conn:
                conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role_id))
            with self.connect() as conn:
                conn.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(self.schema), role_id
                    )
                )
                conn.execute(
                    sql.SQL("GRANT SELECT, INSERT, UPDATE ON {}.ventas_control TO {}").format(
                        sql.Identifier(self.schema), role_id
                    )
                )
                conn.execute(
                    sql.SQL("GRANT SELECT ON {}.facturas TO {}").format(
                        sql.Identifier(self.schema), role_id
                    )
                )
                conn.execute("DELETE FROM ventas_control WHERE id_factura = %s", (second["id"],))
            with self.connect() as conn:
                conn.execute(sql.SQL("SET ROLE {}").format(role_id))
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM ventas_control").fetchone()[0], 1
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM facturas").fetchone()[0], 0
                )
                conn.execute(
                    """INSERT INTO ventas_control
                       (id_factura, id_usuario, id_solicitud, huella)
                       VALUES (%s, 'U1', 'api-role-insert-request', %s)""",
                    (second["id"], "a" * 64),
                )
                conn.execute(
                    "UPDATE ventas_control SET id_entrega = %s WHERE id_factura = %s",
                    (second["deliveryId"], second["id"]),
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT TRIM(id_entrega) FROM ventas_control WHERE id_factura = %s",
                        (second["id"],),
                    ).fetchone()[0],
                    second["deliveryId"],
                )
        finally:
            with psycopg.connect(DSN, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP OWNED BY {}").format(role_id))
                conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(role_id))

    def test_http_sale_requires_role_and_stable_idempotency_key(self):
        roles = [{"id_rol": "R1", "rol_nombre": "Operativo_VENTAS"}]
        payload = {
            "idCliente": "C1", "tasaIVA": 12.5, "descuento": 0.01,
            "metodoPago": "CASH", "cuotas": 1,
            "items": [{"idProducto": "P1", "cantidad": 2, "precioUnitario": 3.33}],
        }
        auth = {"Authorization": f"Bearer {main.create_auth_token('U1')}"}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=roles), \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=auth) as client:
            missing = client.post("/api/ventas", json=payload)
            self.assertEqual(missing.status_code, 422)
            key = uuid4().hex
            first = client.post("/api/ventas", json=payload, headers={"Idempotency-Key": key})
            retry = client.post("/api/ventas", json=payload, headers={"Idempotency-Key": key})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(first.json()["id"], retry.json()["id"])
            self.assertEqual(client.post(f"/api/ventas/{first.json()['id']}/aprobar").status_code, 403)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM facturas").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT pro_saldo_final FROM productos WHERE id_producto='P1'").fetchone()[0], 8)

    def test_cancel_before_and_after_approval_restores_once(self):
        for approved in (False, True):
            result = create(sale())
            if approved:
                ventas.aprobar_factura(result["id"], "U1")
            ventas.anular_factura(result["id"], "U1")
            with self.assertRaises(ventas.VentaError):
                ventas.anular_factura(result["id"], "U1")
            with self.connect() as conn:
                self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (10, 0))
                self.assertEqual(conn.execute("SELECT estado_ent FROM entregas WHERE id_entrega=%s", (result["deliveryId"],)).fetchone()[0], "ANU")
                if approved:
                    self.assertEqual(conn.execute("SELECT estado_asi FROM asientos").fetchone()[0], "ANU")

    def test_stock_failure_rolls_back_everything(self):
        items = [SimpleNamespace(product_id="P1", quantity=2, unit_price=Decimal("3.33")),
                 SimpleNamespace(product_id="P2", quantity=2, unit_price=Decimal("3.33"))]
        with self.assertRaises(ventas.VentaError) as error:
            create(sale(items=items))
        self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM facturas").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT pro_saldo_final FROM productos WHERE id_producto='P1'").fetchone()[0], 10)

    def test_two_concurrent_sales_cannot_oversell(self):
        barrier = threading.Barrier(2)
        def execute():
            barrier.wait(timeout=10)
            try:
                create(sale(qty=7))
                return "ok"
            except ventas.VentaError:
                return "failed"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: execute(), range(2))), ["failed", "ok"])
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (3, 7))
            self.assertEqual(conn.execute("SELECT count(*) FROM facturas").fetchone()[0], 1)

    def test_concurrent_retries_are_idempotent_and_payload_is_bound(self):
        barrier = threading.Barrier(2)
        key = uuid4().hex

        def execute():
            barrier.wait(timeout=10)
            return create(sale(), key)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: execute(), range(2)))
        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(results[0]["deliveryId"], results[1]["deliveryId"])
        with self.assertRaises(ventas.VentaError) as error:
            create(sale(qty=3), key)
        self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM facturas").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (8, 2))
        with self.assertRaises(ventas.VentaError):
            create(sale(), "short")

    def test_concurrent_delivery_and_cancel_cannot_both_succeed(self):
        result = create(sale())
        ventas.aprobar_factura(result["id"], "U1")
        barrier = threading.Barrier(2)

        def action(which):
            barrier.wait(timeout=10)
            try:
                if which == "deliver":
                    ventas.confirmar_entrega(result["deliveryId"], delivery(1, "Pendiente"), "U1")
                else:
                    ventas.anular_factura(result["id"], "U1")
                return "ok"
            except ventas.VentaError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(action, ("deliver", "cancel"))), ["conflict", "ok"])
        with self.connect() as conn:
            state = conn.execute("SELECT estado_fac FROM facturas").fetchone()[0]
            stock = conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone()
            self.assertEqual(stock, (10, 0) if state == "ANU" else (8, 2))

    def test_zero_iva_and_document_specific_rates(self):
        first = create(sale(qty=1, rate="0", discount="0"))
        second = create(sale(qty=1, rate="5", discount="0"))
        documents = {doc["id"]: doc for doc in ventas.listar_ventas()}
        self.assertEqual((documents[first["id"]]["taxRate"], documents[first["id"]]["tax"]),
                         (Decimal("0.00"), Decimal("0.00")))
        self.assertEqual((documents[second["id"]]["taxRate"], documents[second["id"]]["tax"]),
                         (Decimal("5.00"), Decimal("0.17")))

    def test_audit_failure_rolls_back_creation(self):
        with self.connect() as conn:
            conn.execute("ALTER TABLE log_auditoria ADD CONSTRAINT test_rechazar_auditoria CHECK (false) NOT VALID")
        with self.assertRaises(psycopg.Error):
            create(sale())
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM facturas").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (10, 0))

    def test_accounting_or_detail_inconsistency_blocks_cancellation(self):
        result = create(sale())
        ventas.aprobar_factura(result["id"], "U1")
        with self.connect() as conn:
            conn.execute("UPDATE asientos SET estado_asi='APR'")
        with self.assertRaises(ventas.VentaError) as error:
            ventas.anular_factura(result["id"], "U1")
        self.assertIn("reverso contable", error.exception.detail)
        with self.connect() as conn:
            conn.execute("UPDATE asientos SET estado_asi='PEN'")
            conn.execute("UPDATE proxent SET pxe_cantidad=3")
        with self.assertRaises(ventas.VentaError) as error:
            ventas.anular_factura(result["id"], "U1")
        self.assertIn("conciliación", error.exception.detail)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT pro_saldo_final,pro_qty_egresos FROM productos WHERE id_producto='P1'").fetchone(), (8, 2))
            self.assertEqual(conn.execute("SELECT estado_fac FROM facturas").fetchone()[0], "APR")

    def test_audit_context_and_invalid_values(self):
        result = create(sale())
        with self.connect() as conn:
            actor = conn.execute(
                "SELECT trim(id_usuario), log_ip FROM log_auditoria "
                "WHERE log_tablaafectada='FACTURAS' AND log_accion='INSERT'"
            ).fetchone()
            self.assertEqual(actor, ("U1", "127.0.0.1"))
        with self.assertRaises(ventas.VentaError):
            create(sale(rate="100.01"))
        with self.assertRaises(ventas.VentaError):
            create(sale(rate="NaN"))
        with self.assertRaises(ventas.VentaError):
            create(sale(discount="7.00"))
        duplicate = [SimpleNamespace(product_id="P1", quantity=1, unit_price=Decimal("3.33"))] * 2
        with self.assertRaises(ventas.VentaError):
            create(sale(items=duplicate))
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM facturas").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT id_factura FROM facturas").fetchone()[0].strip(), result["id"])

    def test_invalid_delivery_and_historical_invoice_are_blocked(self):
        result = create(sale())
        ventas.aprobar_factura(result["id"], "U1")
        with self.connect() as conn:
            with self.assertRaises(psycopg.Error):
                conn.execute("UPDATE entregas SET estado_ent='ENT' WHERE id_entrega=%s", (result["deliveryId"],))
        for payload in (delivery(3), delivery(1), delivery(1, "x", "P2")):
            with self.subTest(payload=payload), self.assertRaises(ventas.VentaError):
                ventas.confirmar_entrega(result["deliveryId"], payload, "U1")
        with self.connect() as conn:
            conn.execute("INSERT INTO facturas (id_factura,id_cliente,id_empleado,fac_fecha,fac_subtotal,fac_iva,fac_total,estado_fac) VALUES ('OLD','C1','E1',NOW(),0,0,0,'ABI')")
        with self.assertRaises(ventas.VentaError) as error:
            ventas.anular_factura("OLD", "U1")
        self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            with self.assertRaises(psycopg.Error):
                conn.execute("CALL sp_factura_anular('OLD','U1')")
        with self.connect() as conn:
            with self.assertRaises(psycopg.Error):
                conn.execute("UPDATE facturas SET estado_fac='ANU' WHERE id_factura='OLD'")
        with self.connect() as conn:
            with self.assertRaises(psycopg.Error):
                conn.execute("UPDATE facturas SET estado_fac='APR' WHERE id_factura='OLD'")


if __name__ == "__main__":
    unittest.main()
