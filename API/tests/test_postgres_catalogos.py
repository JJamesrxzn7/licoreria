import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import postgres_catalogos


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL aislado.")
class PostgresCatalogosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Las pruebas PostgreSQL requieren un servidor local.")
        if config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Las pruebas requieren la base licoreria_api_test.")

    def setUp(self):
        self.schema = "api_test_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE ciudades (id_ciudad char(10), ciu_descripcion text,
                                       ciu_provincia text, ciu_region text);
                CREATE TABLE unidades_medidas (id_unidad_medida char(10) PRIMARY KEY,
                                              um_descripcion text, um_factorconversion numeric);
                CREATE TABLE categorias (id_categoria char(10), cat_nombre text, estado_cat text);
                CREATE TABLE marcas (id_marca char(10), mar_nombre text, estado_mar text);
                CREATE TABLE perchas (id_percha char(10), pch_descripcion text, pch_letra text,
                                      pch_nivel integer, estado_pch text);
                CREATE TABLE bancos (id_banco char(10), ban_nombre text, estado_ban text);
                CREATE TABLE log_auditoria (id_log char(15) PRIMARY KEY, id_usuario char(16),
                    log_fechahora timestamp NOT NULL, log_tablaafectada varchar(50) NOT NULL,
                    log_accion varchar(20) NOT NULL, log_ip varchar(45),
                    log_valoranterior text, log_valornuevo text);
                CREATE TABLE context_events (actor text, ip text);
                CREATE FUNCTION record_context() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    INSERT INTO context_events VALUES (
                        current_setting('app.auditoria_usuario', true),
                        current_setting('app.auditoria_ip', true)
                    );
                    RETURN NEW;
                END $$;
                CREATE TRIGGER unit_audit AFTER INSERT ON unidades_medidas
                    FOR EACH ROW EXECUTE FUNCTION record_context();
                INSERT INTO ciudades VALUES ('C1', 'Quito', 'Pichincha', 'Sierra');
                INSERT INTO categorias VALUES ('C1', 'Activa', 'ACT'), ('C2', 'Inactiva', 'INA');
                INSERT INTO marcas VALUES ('M1', 'Marca', NULL);
                INSERT INTO perchas VALUES ('P1', 'Percha', 'A', 1, 'ACT');
                INSERT INTO bancos VALUES ('B1', 'Banco', 'ACT');
            """)
        self.connection_patch = patch("postgres_catalogos.connect_postgres", self.connect)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.environment_patch = patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"})
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.roles_patch = patch("postgres_auth.active_roles", return_value=[
            {"id_rol": "ROL-ADMIN", "rol_nombre": "Administrador"}
        ])
        self.roles_patch.start()
        self.addCleanup(self.roles_patch.stop)
        self.revocation_patch = patch("postgres_auth.session_revoked", return_value=False)
        self.revocation_patch.start()
        self.addCleanup(self.revocation_patch.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema}")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def test_catalogs_are_read_only_when_units_are_empty(self):
        result = postgres_catalogos.listar_catalogos("USR-TEST", "127.0.0.1")
        self.assertEqual(result["ciudades"], [
            {"id": "C1", "nombre": "Quito", "provincia": "Pichincha", "region": "Sierra"}
        ])
        self.assertEqual(result["categorias"], [{"id": "C1", "nombre": "Activa"}])
        self.assertEqual(result["marcas"], [{"id": "M1", "nombre": "Marca"}])
        self.assertEqual(result["perchas"], [{"id": "P1", "nombre": "Percha", "letra": "A", "nivel": 1}])
        self.assertEqual(result["bancos"], [{"id": "B1", "nombre": "Banco"}])
        self.assertEqual(result["unidadesMedida"], [])
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM unidades_medidas").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM context_events").fetchone()[0], 0)

    def test_catalogs_only_include_authorized_modules(self):
        sales = postgres_catalogos.listar_catalogos("USR-TEST", "127.0.0.1", {"VENTAS"})
        self.assertEqual(len(sales["ciudades"]), 1)
        for field in ("categorias", "marcas", "perchas", "bancos", "unidadesMedida"):
            self.assertEqual(sales[field], [])
        inventory = postgres_catalogos.listar_catalogos("USR-TEST", "127.0.0.1", {"INVENTARIOS"})
        self.assertEqual(len(inventory["perchas"]), 1)
        self.assertEqual(inventory["categorias"], [])
        combined = postgres_catalogos.listar_catalogos(
            "USR-TEST", "127.0.0.1", {"COMPRAS", "CONTABILIDAD"}
        )
        self.assertEqual(len(combined["categorias"]), 1)
        self.assertEqual(len(combined["bancos"]), 1)

    def test_http_catalogs_and_unmigrated_route(self):
        headers = {"Authorization": f"Bearer {main.create_auth_token('USR-TEST')}"}
        with TestClient(main.app, headers=headers) as client:
            catalog = client.get("/api/catalogos/generales")
            units = client.get("/api/unidades-medida")
            categories = client.get("/api/categorias")
            blocked = client.get("/api/auth/demo-accounts")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(units.status_code, 200)
        self.assertEqual(categories.status_code, 503)
        self.assertEqual(catalog.json()["unidadesMedida"], [])
        self.assertEqual(units.json(), [])
        self.assertIn("aún no", categories.json()["detail"])
        self.assertEqual(blocked.status_code, 503)
        self.assertIn("aún no", blocked.json()["detail"])
        with self.connect() as conn:
            rows = conn.execute("SELECT log_accion, log_valornuevo FROM log_auditoria").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(action == "SELECT" for action, _ in rows))

    def test_audit_failure_does_not_return_success(self):
        with patch("postgres_catalogos.registrar_auditoria", side_effect=psycopg.OperationalError("fallo")):
            with self.assertLogs("main", level="ERROR"):
                headers = {"Authorization": f"Bearer {main.create_auth_token('USR-TEST')}"}
                with TestClient(main.app, headers=headers) as client:
                    response = client.get("/api/unidades-medida")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("fallo", response.text)


if __name__ == "__main__":
    unittest.main()
