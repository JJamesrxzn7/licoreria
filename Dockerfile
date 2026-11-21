# ==============================================================================
# DOCKERFILE — ARQUITECTURA DE SISTEMAS DE INFORMACIÓN (PIZARRA DEL PROFESOR)
# Licorería La Cava — Middleware FastAPI & Coordinador Distribuido 2PC (:8000)
# ==============================================================================
FROM python:3.14-slim

LABEL maintainer="DBA & Arquitecto de SI - Licorería La Cava (PUCE Bases de Datos II)"
LABEL architecture="3-Tier Distributed ERP + Multi-Engine DB Cluster (MariaDB :3307/:3308/:3309, NoSQL JSON, PostgreSQL :5432)"

WORKDIR /app

# Instalar dependencias nativas para conectores PostgreSQL (psycopg) y MariaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias de la capa de Lógica de Negocio (FastAPI)
COPY API/ /app/API/

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    mysql-connector-python \
    "psycopg[binary]" \
    pydantic \
    python-dotenv

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/API"]
