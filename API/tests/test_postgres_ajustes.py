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
import postgres_ajustes


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura PostgreSQL local aislado con copia del esquema sin datos.")
class AjustesRealSchemaTests(unittest.TestCase):
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
        self.schema = "api_ajustes_" + uuid4().hex
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
                INSERT INTO unidades_medidas (id_unidad_medida,um_descripcion,um_factorconversion)
                    VALUES ('UND','Unidad',1);
                INSERT INTO categorias (id_categoria,cat_nombre,estado_cat) VALUES ('CA','Categoria','ACT');
                INSERT INTO marcas (id_marca,mar_nombre,estado_mar) VALUES ('MA','Marca','ACT');
                INSERT INTO productos (id_producto,id_categoria,id_marca,pro_descripcion,pro_um_compra,
                    pro_um_venta,pro_valor_compra,pro_precio_venta,pro_saldo_inicial,pro_qty_ingresos,
                    pro_qty_egresos,pro_qty_ajustes,pro_saldo_final,estado_prod)
                    VALUES ('P1','CA','MA','Producto','UND','UND',1,3,10,0,0,0,10,'ACT');
            """)
        self.patch = patch("postgres_ajustes.connect_postgres", self.connect)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema} -c lock_timeout=5000")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def adjustment(self, kind="OUT", reason="Merma"):
        return main.PhysicalAdjustmentInput(idEmpleado="FALSO", idProducto="P1", tipo=kind, cantidad=2, motivo=reason)

    def test_create_and_cancel_preserve_stock_and_bind_actor(self):
        for kind, signed in [("IN", 2), ("OUT", -2)]:
            result = postgres_ajustes.crear_ajuste(self.adjustment(kind), "U1", "127.0.0.1")
            with self.connect() as conn:
                self.assertEqual(conn.execute(
                    "SELECT TRIM(a.id_empleado), d.pxa_cantidad, d.pxa_qty_ajustada "
                    "FROM ajustes a JOIN proxaju d USING (id_ajuste) WHERE a.id_ajuste=%s", (result["id"],)
                ).fetchone(), ("E1", 2, signed))
            self.assertEqual(postgres_ajustes.anular_ajuste(result["id"], "U1", None)["estado"], "ANU")
            with self.assertRaises(HTTPException) as error:
                postgres_ajustes.anular_ajuste(result["id"], "U1", None)
            self.assertEqual(error.exception.status_code, 409)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT pro_saldo_final, pro_qty_ajustes FROM productos").fetchone(), (10, 0))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asientos").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM proxaju WHERE estado_pxaju = 'ANU'").fetchone()[0], 2)

    def test_validation_audit_failure_and_concurrent_cancel(self):
        with self.assertRaises(HTTPException) as error:
            postgres_ajustes.crear_ajuste(self.adjustment(reason="x" * 31), "U1", None)
        self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(HTTPException):
            postgres_ajustes.crear_ajuste(self.adjustment(), "NOEXISTE", None)
        result = postgres_ajustes.crear_ajuste(self.adjustment(), "U1", None)
        def cancel():
            try:
                postgres_ajustes.anular_ajuste(result["id"], "U1", None)
                return 200
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: cancel(), range(2))), [200, 409])
        with self.connect() as conn:
            conn.execute("DROP TABLE log_auditoria CASCADE")
        with self.assertRaises(psycopg.Error):
            postgres_ajustes.crear_ajuste(self.adjustment(), "U1", None)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM ajustes").fetchone()[0], 1)

    def test_http_permissions_and_approval_remains_blocked(self):
        roles = [{"rol_nombre": "Operativo_INVENTARIOS"}]
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=roles) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            payload = {"idProducto": "P1", "tipo": "OUT", "cantidad": 2, "motivo": "Merma"}
            response = client.post("/api/ajustes", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            adjustment_id = response.json()["id"]
            self.assertEqual(client.post(f"/api/ajustes/{adjustment_id}/anular").status_code, 403)
            active.return_value = [{"rol_nombre": "Auxiliar_INVENTARIOS"}]
            self.assertEqual(client.post(f"/api/ajustes/{adjustment_id}/aprobar").status_code, 503)
            active.return_value = [{"rol_nombre": "Jefe_INVENTARIOS"}]
            self.assertEqual(client.post(f"/api/ajustes/{adjustment_id}/anular").status_code, 200)


if __name__ == "__main__":
    unittest.main()
