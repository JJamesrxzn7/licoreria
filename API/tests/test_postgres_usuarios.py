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
import postgres_usuarios


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL aislado.")
class UsuariosPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")

    def setUp(self):
        self.schema = "api_usuarios_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE departamentos (id_departamento char(10), dep_nombre text);
                CREATE TABLE empleados (id_empleado char(10), id_departamento char(10),
                    emp_nombre1 text, emp_apellido1 text, estado_emp char(3));
                CREATE TABLE usuarios (id_usuario char(16), id_empleado char(10),
                    usr_username text, usr_passwordhash text, estado_usr char(3));
                CREATE TABLE roles (id_rol char(10), rol_nombre text, rol_descripcion text, estado_rol char(3));
                CREATE TABLE usuariosxroles (id_usuario char(16), id_rol char(10), estado_uxr char(3));
                CREATE TABLE log_auditoria (id_log char(14), id_usuario char(16),
                    log_fechahora timestamp, log_tablaafectada text, log_accion text,
                    log_valoranterior text, log_valornuevo text);
                INSERT INTO departamentos VALUES ('D1', 'Ventas');
                INSERT INTO empleados VALUES ('E1', 'D1', 'Ana', 'Prueba', 'ACT'),
                    ('E2', 'D1', 'Luis', 'Libre', 'ACT'), ('E3', 'D1', 'Inactivo', 'Prueba', 'INA');
                INSERT INTO usuarios VALUES ('U1', 'E1', 'ana', 'hash-no-visible', 'ACT'),
                    ('U2', NULL, 'sin-empleado', 'otro-hash', 'PEN');
                INSERT INTO roles VALUES ('R1', 'Operativo_VENTAS', 'Venta', 'ACT'),
                    ('R2', 'Jefe_COMPRAS', 'Compra', 'INA');
                INSERT INTO usuariosxroles VALUES ('U1', 'R1', 'ACT'), ('U1', 'R2', 'ACT'),
                    ('U2', 'R1', 'INA');
                INSERT INTO log_auditoria
                    SELECT 'L' || n, 'U1', timestamp '2026-01-01' + n * interval '1 minute',
                           'PRUEBA', 'SELECT', NULL, n::text
                    FROM generate_series(1, 105) n;
            """)
        self.db_patch = patch("postgres_usuarios.connect_postgres", self.connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema}")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def test_data_shape_roles_and_audit_limit(self):
        users = postgres_usuarios.listar_usuarios()
        self.assertEqual(users[0], {
            "id_Usuario": "U1", "id_Empleado": "E1", "username": "ana",
            "ESTADO_USR": "ACT", "emp_Nombre1": "Ana", "emp_Apellido1": "Prueba",
            "dep_Nombre": "Ventas", "roles": ["Operativo_VENTAS"],
        })
        self.assertEqual(users[1]["id_Empleado"], "")
        self.assertEqual(users[1]["roles"], [])
        self.assertEqual(postgres_usuarios.roles_usuario("U1"), [{"id": "R1", "nombre": "Operativo_VENTAS"}])
        self.assertEqual(postgres_usuarios.empleados_disponibles(), [
            {"id": "E2", "nombre": "Luis", "apellido": "Libre", "departamento": "Ventas"},
        ])
        roles = postgres_usuarios.listar_roles()
        self.assertEqual(roles[0]["usuariosAsignados"], 1)
        self.assertEqual(roles[1]["estado"], "INA")
        logs = postgres_usuarios.listar_auditoria()
        self.assertEqual(len(logs), 100)
        self.assertEqual(logs[0]["valorNuevo"], "105")
        self.assertEqual(logs[-1]["valorNuevo"], "6")

    def test_http_only_administrator_and_writes_stay_blocked(self):
        admin = [{"rol_nombre": "Administrador"}]
        operative = [{"rol_nombre": "Operativo_VENTAS"}]
        headers = {"Authorization": "Bearer " + main.create_auth_token("U1")}
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=admin) as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             TestClient(main.app, headers=headers) as client:
            for path in ("/api/usuarios", "/api/usuarios/U1/roles",
                         "/api/usuarios/empleados-disponibles", "/api/auth/roles", "/api/auditoria"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(client.get("/api/capabilities").json()["userManagementWrites"])
            self.assertEqual(client.delete("/api/usuarios/U1").status_code, 503)
            active.return_value = operative
            for path in ("/api/usuarios", "/api/auth/roles", "/api/auditoria"):
                self.assertEqual(client.get(path).status_code, 403)
            active.return_value = None
            self.assertEqual(client.get("/api/usuarios").status_code, 401)


if __name__ == "__main__":
    unittest.main()
