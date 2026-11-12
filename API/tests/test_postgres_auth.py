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
import postgres_auth
import postgres_authorization as policy


def role(name):
    return {"id_rol": name, "rol_nombre": name}


class MatrixTests(unittest.TestCase):
    def test_matrix_all_modules_and_roles(self):
        for module in postgres_auth.MODULES:
            for prefix, action in postgres_auth.ROLE_ACTION.items():
                with self.subTest(module=module, role=prefix):
                    actual = postgres_auth.grants([role(f"{prefix}_{module}")])
                    self.assertEqual(actual, {(module, "VER"), (module, action)})
                    for other in postgres_auth.MODULES - {module}:
                        self.assertFalse(any(m == other for m, _ in actual))
        self.assertEqual(len(postgres_auth.grants([role("Administrador")])), 20)
        self.assertEqual(postgres_auth.grants([role("SuperAdministrador"), role("ROL-ADMIN")]), set())

    def test_union_and_unknowns(self):
        roles = [role("Operativo_VENTAS"), role("Auxiliar_VENTAS"), role("Jefe_COMPRAS")]
        self.assertTrue(policy.allowed(roles, ("VENTAS", "CREAR")))
        self.assertTrue(policy.allowed(roles, ("VENTAS", "APROBAR")))
        self.assertFalse(policy.allowed(roles, ("VENTAS", "ANULAR")))
        self.assertTrue(policy.allowed(roles, ("COMPRAS", "ANULAR")))
        self.assertFalse(policy.allowed(roles, None))
        self.assertFalse(policy.allowed(roles, ("ADMIN", "VER")))

    def test_action_classification_and_fail_closed(self):
        for path, method, result in [
            ("/api/ventas", "GET", ("VENTAS", "VER")),
            ("/api/ventas", "POST", ("VENTAS", "CREAR")),
            ("/api/ventas/1/aprobar", "POST", ("VENTAS", "APROBAR")),
            ("/api/ventas/1/anular", "POST", ("VENTAS", "ANULAR")),
            ("/api/recepciones/1/confirmar", "POST", ("INVENTARIOS", "APROBAR")),
            ("/api/nomina/1", "DELETE", ("TALENTO_HUMANO", "ANULAR")),
            ("/api/usuarios", "GET", ("ADMIN", "VER")),
            ("/api/ventas-maliciosas", "GET", None),
            ("/api/ventas", "TRACE", None),
        ]:
            with self.subTest(path=path, method=method):
                self.assertEqual(policy.requirement(path, method), result)

    def test_postgres_supported_routes_allow_only_migrated_methods(self):
        for path, method in [
            ("/api/compras", "POST"),
            ("/api/compras/OC-1/aprobar", "POST"),
            ("/api/compras/OC-1/anular", "POST"),
            ("/api/ventas/1/aprobar", "POST"),
            ("/api/empleados", "POST"),
            ("/api/nomina/bonificaciones", "POST"),
            ("/api/nomina/bonificaciones/BON-1", "PUT"),
            ("/api/nomina/bonificaciones/BON-1", "DELETE"),
            ("/api/contabilidad/bancos", "POST"),
            ("/api/usuarios", "GET"),
        ]:
            with self.subTest(path=path, method=method):
                self.assertTrue(policy.supported(path, method))
        for path, method in [
            ("/api/usuarios", "POST"),
            ("/api/productos/PRO-1", "PUT"),
            ("/api/contabilidad/centros-costos", "POST"),
            ("/api/ciudades", "GET"),
            ("/api/auth/setup", "POST"),
            ("/api/ventas-maliciosas", "GET"),
        ]:
            with self.subTest(path=path, method=method):
                self.assertFalse(policy.supported(path, method))

    def test_http_guard_checks_live_roles_and_token(self):
        token = main.create_auth_token("USR-TEST")
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles") as active, \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("postgres_catalogos.registrar_auditoria"), \
             patch("postgres_catalogos.listar_unidades", return_value=[]), \
             TestClient(main.app) as client:
            allowed = client.get(
                "/api/unidades-medida",
                headers={"Origin": "http://localhost:5173"},
            )
            self.assertEqual(allowed.status_code, 401)
            self.assertEqual(
                allowed.headers.get("access-control-allow-origin"),
                "http://localhost:5173",
            )
            denied = client.get("/api/unidades-medida", headers={"Origin": "https://example.test"})
            self.assertEqual(denied.status_code, 401)
            self.assertIsNone(denied.headers.get("access-control-allow-origin"))
            self.assertEqual(client.get("/api/unidades-medida", headers={"Authorization": "Bearer invalid"}).status_code, 401)
            active.return_value = None
            headers = {"Authorization": f"Bearer {token}"}
            self.assertEqual(client.get("/api/unidades-medida", headers=headers).status_code, 401)
            active.return_value = [role("Operativo_VENTAS")]
            self.assertEqual(client.get("/api/unidades-medida", headers=headers).status_code, 403)
            with patch("postgres_catalogos.listar_catalogos", return_value={}):
                self.assertEqual(client.get("/api/catalogos/generales", headers=headers).status_code, 200)
            self.assertEqual(client.post("/api/ventas/1/aprobar", headers=headers).status_code, 403)
            active.return_value = [role("Operativo_COMPRAS")]
            self.assertEqual(client.get("/api/unidades-medida", headers=headers).status_code, 200)
            active.return_value = [role("Operativo_COMPRAS"), role("Operativo_INVENTARIOS")]
            with patch("postgres_modulos.listar", return_value=[]):
                self.assertEqual(client.get("/api/ajustes", headers=headers).status_code, 200)
            # El registro todavía no migrado permanece bloqueado.
            self.assertEqual(client.post("/api/auth/registro", headers=headers).status_code, 503)
            self.assertEqual(client.get("/api/ventas", headers=headers).status_code, 403)
            self.assertEqual(client.get("/api/desconocido", headers=headers).status_code, 503)
            with patch("postgres_auth.is_initialized", return_value=True):
                self.assertEqual(client.get("/api/auth/setup-status").json(), {"initialized": True})

    def test_unmigrated_endpoints_never_fall_back_to_mariadb(self):
        token = main.create_auth_token("USR-TEST")
        headers = {"Authorization": "Bearer " + token}
        admin_roles = [role("Administrador")]
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("postgres_auth.active_roles", return_value=admin_roles), \
             patch("postgres_auth.session_revoked", return_value=False), \
             patch("main.connect_database", side_effect=AssertionError("MariaDB fallback reached")), \
             TestClient(main.app) as client:
            requests = (
                ("post", "/api/usuarios", {}),
                ("put", "/api/productos/PRO-1", {}),
                ("post", "/api/contabilidad/centros-costos", {}),
                ("get", "/api/ciudades", None),
                ("post", "/api/auth/setup", {}),
            )
            for method, path, body in requests:
                with self.subTest(method=method, path=path):
                    request = getattr(client, method)
                    kwargs = {"headers": headers} if path != "/api/auth/setup" else {}
                    if body is not None:
                        kwargs["json"] = body
                    response = request(path, **kwargs)
                    self.assertEqual(response.status_code, 503, response.text)


DSN = os.getenv("LICORERIA_TEST_POSTGRES_DSN", "")


@unittest.skipUnless(DSN, "Configura LICORERIA_TEST_POSTGRES_DSN para PostgreSQL aislado.")
class PostgresAuthIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(DSN)
        if config.get("host") not in {"127.0.0.1", "localhost", "::1"} or config.get("dbname") != "licoreria_api_test":
            raise RuntimeError("Solo se admite la base local aislada licoreria_api_test.")

    def setUp(self):
        self.schema = "api_auth_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE departamentos (id_departamento text PRIMARY KEY, dep_nombre text);
                CREATE TABLE empleados (id_empleado text PRIMARY KEY, id_departamento text,
                    emp_nombre1 text, emp_apellido1 text);
                CREATE TABLE usuarios (id_usuario text PRIMARY KEY, id_empleado text, usr_username text,
                    usr_passwordhash text, usr_intentosfallidos int, estado_usr text, usr_ultimoacceso timestamp);
                CREATE TABLE roles (id_rol text PRIMARY KEY, rol_nombre text, estado_rol text);
                CREATE TABLE usuariosxroles (id_usuario text, id_rol text, estado_uxr text);
                CREATE TABLE permisos (id_permiso text PRIMARY KEY, prm_modulo text, prm_accion text, estado_prm text);
                CREATE TABLE rolesxpermisos (id_rol text, id_permiso text, estado_rxp text);
                CREATE TABLE log_auditoria (id_log text PRIMARY KEY, id_usuario text, log_fechahora timestamp,
                    log_tablaafectada text, log_accion text, log_ip text, log_valoranterior text, log_valornuevo text);
                INSERT INTO departamentos VALUES ('D1', 'Ventas');
                INSERT INTO empleados VALUES ('E1', 'D1', 'Ana', 'Prueba');
                INSERT INTO roles VALUES ('R1', 'Operativo_VENTAS', 'ACT'), ('R2', 'Auxiliar_VENTAS', 'ACT'),
                    ('R3', 'Jefe_COMPRAS', 'INA');
                INSERT INTO usuariosxroles VALUES ('U1', 'R1', 'ACT'), ('U1', 'R2', 'ACT'), ('U1', 'R3', 'ACT');
                INSERT INTO permisos VALUES ('P1', 'VENTAS', 'VER', 'ACT'), ('P2', 'VENTAS', 'ANULAR', 'ACT');
                INSERT INTO rolesxpermisos VALUES ('R1', 'P1', 'ACT'), ('R1', 'P2', 'ACT');
            """)
            conn.execute("INSERT INTO usuarios VALUES ('U1', 'E1', 'ana', %s, 0, 'ACT', NULL)",
                         (main.hash_password("clave-prueba"),))
            migration = Path(__file__).resolve().parents[1] / "migrations" / "20261108_sesiones_postgresql.sql"
            conn.execute(migration.read_text(encoding="utf-8"))
        self.patches = [
            patch("postgres_auth.connect_postgres", self.connect),
            patch("postgres_catalogos.connect_postgres", self.connect),
            patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def connect(self):
        return psycopg.connect(DSN, options=f"-c search_path={self.schema}")

    def drop_schema(self):
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def test_login_failures_success_active_roles_and_revocation(self):
        with TestClient(main.app) as client:
            for _ in range(2):
                response = client.post("/api/auth/login", json={"username": "ana", "password": "equivocada"})
                self.assertEqual(response.status_code, 401)
            with self.connect() as conn:
                self.assertEqual(conn.execute("SELECT usr_intentosfallidos FROM usuarios").fetchone()[0], 2)
            response = client.post("/api/auth/login", json={"username": "ana", "password": "clave-prueba"})
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(set(data["user"]["roles"]), {"Operativo_VENTAS", "Auxiliar_VENTAS"})
            self.assertEqual(data["user"]["permissions"], ["P1"])
            headers = {"Authorization": "Bearer " + data["token"]}
            self.assertEqual(client.post("/api/ventas/1/anular", headers=headers).status_code, 403)
            self.assertEqual(client.post("/api/ventas/1/aprobar", headers=headers).status_code, 503)
            with self.connect() as conn:
                conn.execute("UPDATE usuariosxroles SET estado_uxr = 'INA' WHERE id_rol = 'R2'")
            self.assertEqual(client.post("/api/ventas/1/aprobar", headers=headers).status_code, 403)
            with self.connect() as conn:
                conn.execute("UPDATE usuarios SET estado_usr = 'INA'")
            self.assertEqual(client.get("/api/ventas", headers=headers).status_code, 401)
            with self.connect() as conn:
                self.assertEqual(conn.execute("SELECT usr_intentosfallidos FROM usuarios").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT count(*) FROM log_auditoria WHERE log_accion = 'LOGIN'").fetchone()[0], 1)

    def test_lockout_and_audit_failure_rolls_back(self):
        with self.connect() as conn:
            conn.execute("UPDATE usuarios SET usr_intentosfallidos = 4")
        result, error = postgres_auth.login("ana", "incorrecta", "127.0.0.1", main.verify_password)
        self.assertIsNone(result)
        self.assertEqual(error[0], 401)
        result, error = postgres_auth.login("ana", "clave-prueba", "127.0.0.1", main.verify_password)
        self.assertEqual(error[0], 403)
        with self.connect() as conn:
            conn.execute("UPDATE usuarios SET usr_intentosfallidos = 2")
            conn.execute("DROP TABLE log_auditoria")
        with self.assertRaises(psycopg.Error):
            postgres_auth.login("ana", "clave-prueba", "127.0.0.1", main.verify_password)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT usr_intentosfallidos FROM usuarios").fetchone()[0], 2)

    def test_logout_revokes_only_current_session_and_is_audited(self):
        with TestClient(main.app) as client:
            login = {"username": "ana", "password": "clave-prueba"}
            first = client.post("/api/auth/login", json=login).json()["token"]
            second = client.post("/api/auth/login", json=login).json()["token"]
            self.assertNotEqual(first, second)
            first_headers = {"Authorization": "Bearer " + first}
            second_headers = {"Authorization": "Bearer " + second}
            result = client.post("/api/auth/logout", json={"userId": "otro"}, headers=first_headers)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(client.get("/api/capabilities", headers=first_headers).status_code, 401)
            self.assertEqual(client.post("/api/auth/logout", json={}, headers=first_headers).status_code, 401)
            self.assertEqual(client.get("/api/capabilities", headers=second_headers).status_code, 200)
            with self.connect() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM sesiones_revocadas").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT id_usuario FROM log_auditoria WHERE log_accion = 'LOGOUT'").fetchone()[0], "U1")

    def test_logout_audit_failure_rolls_back_revocation(self):
        with TestClient(main.app) as client:
            token = client.post("/api/auth/login", json={"username": "ana", "password": "clave-prueba"}).json()["token"]
            with self.connect() as conn:
                conn.execute("DROP TABLE log_auditoria")
            headers = {"Authorization": "Bearer " + token}
            self.assertEqual(client.post("/api/auth/logout", json={}, headers=headers).status_code, 500)
            with self.connect() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM sesiones_revocadas").fetchone()[0], 0)
            self.assertFalse(postgres_auth.session_revoked(token))

    def test_missing_revocation_table_blocks_protected_requests(self):
        with TestClient(main.app) as client:
            token = client.post("/api/auth/login", json={"username": "ana", "password": "clave-prueba"}).json()["token"]
            with self.connect() as conn:
                conn.execute("DROP TABLE sesiones_revocadas")
            headers = {"Authorization": "Bearer " + token}
            response = client.get("/api/capabilities", headers=headers)
            self.assertEqual(response.status_code, 500)

    def test_non_owner_with_explicit_grants_can_read_revocations_under_rls(self):
        test_role = "api_session_" + uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(test_role)))
        def drop_role():
            with psycopg.connect(DSN, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(test_role)))
                conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(test_role)))
        self.addCleanup(drop_role)
        with self.connect() as conn:
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(self.schema), sql.Identifier(test_role)))
            conn.execute(sql.SQL("GRANT SELECT, INSERT ON sesiones_revocadas TO {}").format(
                sql.Identifier(test_role)))
            conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(test_role)))
            conn.execute("INSERT INTO sesiones_revocadas VALUES (%s, NOW())", ("a" * 64,))
            self.assertEqual(conn.execute("SELECT count(*) FROM sesiones_revocadas").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
