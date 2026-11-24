"""
Sede activa de cada petición de la app (header `X-Sede-App`): decide a qué ERP se conecta la API.

    QUITO     -> MariaDB de la PC de Escritorio (lacava_quito)
    GUAYAQUIL -> MariaDB de la Laptop (licoreriadatabase, el ERP original)  [por defecto]
    CUENCA    -> PostgreSQL de la Laptop (lacava_cuenca, rol de mínimo privilegio)
"""

import os
from contextvars import ContextVar

SEDES = ("QUITO", "GUAYAQUIL", "CUENCA")
sede_app: ContextVar[str] = ContextVar("sede_app", default="GUAYAQUIL")

_ALIAS = {"UIO": "QUITO", "GYE": "GUAYAQUIL", "CUE": "CUENCA", "CUENCA_CLOUD": "CUENCA"}


def normalizar(valor: str | None) -> str:
    v = (valor or "").strip().upper()
    v = _ALIAS.get(v, v)
    return v if v in SEDES else "GUAYAQUIL"


def mariadb_destino(sede: str) -> dict:
    """Host, puerto y base del ERP MariaDB de la sede (Quito o Guayaquil)."""
    if sede == "QUITO":
        return {
            "host": os.getenv("ERP_QUITO_HOST", os.getenv("IP_TS_QUITO", "100.77.220.102")),
            "port": int(os.getenv("ERP_QUITO_PORT", "3307")),
            "database": os.getenv("ERP_QUITO_DATABASE", "lacava_quito"),
        }
    return {
        "host": os.getenv("MARIADB_HOST", "localhost"),
        "port": int(os.getenv("MARIADB_PORT", "3307")),
        "database": os.getenv("MARIADB_DATABASE", "licoreriadatabase"),
    }
