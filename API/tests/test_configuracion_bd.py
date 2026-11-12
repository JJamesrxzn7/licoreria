import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import (
    app,
    connect_database,
    database_backend,
    get_cors_origins,
    get_db_config,
    validate_production_configuration,
)


class ConfiguracionBDTests(unittest.TestCase):
    def test_cors_predeterminado_solo_permite_frontend_local(self):
        with patch.dict(os.environ, {}, clear=True):
            origins = get_cors_origins()
        self.assertEqual(
            origins,
            ["http://127.0.0.1:5173", "http://localhost:5173"],
        )

    def test_cors_lee_lista_de_origenes_exactos(self):
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": " https://app.example.com, http://localhost:5173 "},
            clear=True,
        ):
            origins = get_cors_origins()
        self.assertEqual(
            origins,
            ["https://app.example.com", "http://localhost:5173"],
        )

    def test_cors_rechaza_configuracion_abierta_o_invalida(self):
        for value in ("", "*", "https://*.example.com", "https://app.example.com/path"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"CORS_ORIGINS": value}, clear=True
            ):
                with self.assertRaises(ValueError):
                    get_cors_origins()

    def test_cors_de_produccion_no_usa_origenes_locales_por_defecto(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with self.assertRaises(ValueError):
                get_cors_origins()

    def test_middleware_cors_no_permite_cualquier_origen(self):
        cors = next(
            middleware
            for middleware in app.user_middleware
            if middleware.cls is CORSMiddleware
        )
        self.assertNotIn("*", cors.kwargs["allow_origins"])

    def test_cors_permite_solo_origenes_configurados(self):
        with TestClient(app) as client:
            allowed = client.options(
                "/api",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
            rejected = client.options(
                "/api",
                headers={
                    "Origin": "https://untrusted.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )
        self.assertNotEqual(
            rejected.headers.get("access-control-allow-origin"),
            "https://untrusted.example",
        )

    def test_configuracion_local_conserva_valores(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_db_config()
        self.assertEqual(config["host"], "localhost")
        self.assertEqual(config["port"], 3307)
        self.assertNotIn("ssl_ca", config)
        self.assertNotIn("connection_timeout", config)

    def test_configuracion_remota_verifica_certificado_y_nombre(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "ca.pem"
            certificate.write_text("test", encoding="utf-8")
            with patch.dict(os.environ, {
                "MARIADB_SSL_CA": str(certificate),
                "MARIADB_CONNECTION_TIMEOUT": "30",
            }, clear=True):
                config = get_db_config()
        self.assertEqual(config["ssl_ca"], str(certificate))
        self.assertIs(config["ssl_verify_cert"], True)
        self.assertIs(config["ssl_verify_identity"], True)
        self.assertEqual(config["connection_timeout"], 30)

    def test_certificado_inexistente_no_degrada_la_seguridad(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "MARIADB_SSL_CA": str(Path(directory) / "no-existe.pem")
            }, clear=True):
                with self.assertRaises(HTTPException):
                    get_db_config()

    def test_timeout_invalido_se_rechaza(self):
        for value in ("0", "-1", "abc"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"MARIADB_CONNECTION_TIMEOUT": value}, clear=True
            ):
                with self.assertRaises(HTTPException):
                    get_db_config()

    def test_backend_predeterminado_conserva_mariadb(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(database_backend(), "mariadb")

    def test_postgresql_no_se_conecta_accidentalmente_a_mariadb(self):
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}, clear=True):
            with patch("main.mysql.connector.connect") as mysql_connect:
                with self.assertRaises(HTTPException) as raised:
                    connect_database()
        self.assertEqual(raised.exception.status_code, 503)
        mysql_connect.assert_not_called()

    def test_backend_invalido_se_rechaza(self):
        with patch.dict(os.environ, {"DATABASE_BACKEND": "desconocido"}, clear=True):
            with self.assertLogs("main", level="ERROR"):
                with self.assertRaises(HTTPException) as raised:
                    database_backend()
        self.assertEqual(raised.exception.status_code, 500)

    def test_produccion_rechaza_backend_mariadb(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "DATABASE_BACKEND": "mariadb"},
            clear=True,
        ):
            with self.assertRaises(HTTPException):
                validate_production_configuration()

    def test_produccion_requiere_secreto_tls_database_y_cors(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "ca.pem"
            certificate.write_text("test", encoding="utf-8")
            valid = {
                "APP_ENV": "production",
                "DATABASE_BACKEND": "postgresql",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "POSTGRES_SSL_ROOT_CERT": str(certificate),
                "AUTH_TOKEN_SECRET": "x" * 40,
                "CORS_ORIGINS": "https://frontend.example",
            }
            with patch.dict(os.environ, valid, clear=True):
                validate_production_configuration()
            for key, value in (
                ("AUTH_TOKEN_SECRET", "replace-with-a-secret"),
                ("POSTGRES_SSL_ROOT_CERT", str(Path(directory) / "missing.pem")),
                ("CORS_ORIGINS", ""),
            ):
                with self.subTest(key=key), patch.dict(
                    os.environ, {**valid, key: value}, clear=True
                ):
                    with self.assertRaises((RuntimeError, ValueError)):
                        validate_production_configuration()

    def test_health_y_readiness_verifican_estado_de_la_api_y_postgresql(self):
        with patch.dict(
            os.environ,
            {"DATABASE_BACKEND": "postgresql"},
            clear=True,
        ), patch("main.postgres_connection.connect_postgres") as connect:
            connection = connect.return_value.__enter__.return_value
            with TestClient(app) as client:
                self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
                ready = client.get("/readyz")
            self.assertEqual(ready.status_code, 200, ready.text)
            connection.execute.assert_called_once_with("SELECT 1")
            connect.assert_called_once()

    def test_readiness_falla_de_forma_cerrada_si_postgresql_no_disponible(self):
        with patch.dict(
            os.environ,
            {"DATABASE_BACKEND": "postgresql"},
            clear=True,
        ), patch(
            "main.postgres_connection.connect_postgres",
            side_effect=ValueError("database unavailable"),
        ), TestClient(app) as client:
            with self.assertLogs("main", level="ERROR"):
                response = client.get("/readyz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "PostgreSQL no está disponible."})


if __name__ == "__main__":
    unittest.main()
