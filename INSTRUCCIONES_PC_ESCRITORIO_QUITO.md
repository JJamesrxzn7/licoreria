# INSTRUCCIONES PARA LA PC DE ESCRITORIO — NODO QUITO (`jerxmy-01` · `100.77.220.102`)

## 0. CONTEXTO DE RED TAILSCALE (YA VERIFICADO)
El túnel VPN Tailscale entre ambas máquinas **ya está activo y con `ping` de `7 ms`**:
- **`IP_TS_QUITO` (Esta PC de Escritorio `jerxmy-01`):** `100.77.220.102`
- **`IP_TS_GUAYAQUIL` (La Laptop `desktop-6jdt8q0`):** `100.123.81.4`
- **URL de la API en la Laptop (Balanceador de las 3 Réplicas):** `http://100.123.81.4:8000/api`
- **Frontend "La Cava":** Ya está desplegado en **GitHub Pages** (`https://jjamesrxzn7.github.io/licoreria`), por lo que **NO debes levantar ningún frontend ni Nginx** en esta PC de Escritorio.

---

## 1. LO QUE FALTA EJECUTAR EN ESTA PC DE ESCRITORIO (`100.77.220.102`)

Actualmente desde la Laptop (`100.123.81.4`) el `ping` a `100.77.220.102` responde en `7 ms`, pero los puertos TCP **`3307`**, **`27017`** y **`3308`** aparecen cerrados/filtrados (`code 10035`). Debes completar estas **3 tareas exactas**:

---

### TAREA 1.1: Abrir los Puertos `3307`, `3308` y `27017` en el Firewall de Windows
Ejecuta este comando en **PowerShell como Administrador** en la PC de Escritorio para permitir que la API de la Laptop (`100.123.81.4`) consulte tus 3 bases de datos por Tailscale:

```powershell
New-NetFirewallRule -DisplayName "LaCava Quito Cluster (Tailscale 3307, 3308, 27017)" `
  -Direction Inbound -Protocol TCP -LocalPort 3307,3308,27017 -Action Allow
```

---

### TAREA 1.2: Levantar las 3 Bases de Datos de Quito (`docker-compose.quito.yml`) y Cargar Esquemas + 15 Usuarios RBAC

Crea el archivo `docker-compose.quito.yml` con volúmenes persistentes locales (`./data/...`):

```yaml
services:
  # BD 1: QUITO SQL OLTP (MariaDB Puerto 3307)
  db_quito_sql:
    image: mariadb:11.4
    container_name: db_quito_sql
    restart: unless-stopped
    environment:
      MARIADB_ROOT_PASSWORD: "1597.MyHql"
      MARIADB_DATABASE: "licoreriadatabase"
    ports:
      - "0.0.0.0:3307:3306"
    volumes:
      - ./data/quito_sql_3307:/var/lib/mysql

  # BD 2: QUITO NoSQL Documental (MongoDB Puerto 27017)
  db_quito_nosql:
    image: mongo:7.0
    container_name: db_quito_nosql
    restart: unless-stopped
    ports:
      - "0.0.0.0:27017:27017"
    volumes:
      - ./data/quito_mongo_27017:/data/db

  # BD 3: QUITO Paralela PARTITION BY HASH (MariaDB Puerto 3308)
  db_quito_paralela:
    image: mariadb:11.4
    container_name: db_quito_paralela
    restart: unless-stopped
    environment:
      MARIADB_ROOT_PASSWORD: "1597.MyHql"
      MARIADB_DATABASE: "quito_paralela_db"
    ports:
      - "0.0.0.0:3308:3306"
    volumes:
      - ./data/quito_paralela_3308:/var/lib/mysql
```

> **Nota si no usas Docker en la PC de Escritorio:** También puedes levantar las instancias directamente con los binarios nativos de `mariadbd.exe` en los puertos `3307` y `3308` (con `password=1597.MyHql`) y `mongod.exe --bind_ip_all --port 27017`.

#### Esquema exacto que espera la API de la Laptop en tus 3 BDs de Quito:

1. **En `BD 1` (`100.77.220.102:3307`, base `licoreriadatabase`, user `root`, pass `1597.MyHql`):**
   - Tablas de los 5 módulos (`compras`, `productos`, `facturas`, `empleados`, `asientos`, `clientes`, `proveedores`).
   - Los **3 roles (`rol_jefe`, `rol_supervisor`, `rol_operador`)** y los **15 usuarios RBAC** (`c_jefe`, `c_supervisor`, `c_operador`, `i_jefe`, `i_supervisor`, `i_operador`, `v_jefe`, `v_supervisor`, `v_operador`, `th_jefe`, `th_supervisor`, `th_operador`, `ctbl_jefe`, `ctbl_supervisor`, `ctbl_operador`).
   - Las dos tablas de auditoría del contrato:
     ```sql
     USE licoreriadatabase;

     CREATE TABLE IF NOT EXISTS rbac_matriz_15_usuarios (
         username VARCHAR(30) PRIMARY KEY,
         rol_bd VARCHAR(30) NOT NULL,
         modulo_codigo VARCHAR(10) NOT NULL,
         modulo_nombre VARCHAR(40) NOT NULL,
         descripcion_cargo VARCHAR(80) NOT NULL,
         sede_nodo VARCHAR(40) NOT NULL DEFAULT 'BD 1 - QUITO (:3307)',
         estado VARCHAR(15) NOT NULL DEFAULT 'ACTIVO',
         ultima_actividad DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
     );

     CREATE TABLE IF NOT EXISTS operaciones_agentes_ia (
         id_op INT AUTO_INCREMENT PRIMARY KEY,
         sede_header VARCHAR(30) NOT NULL,
         agente_nombre VARCHAR(50) NOT NULL,
         usuario_rbac VARCHAR(30) NOT NULL,
         rol_rbac VARCHAR(30) NOT NULL,
         modulo VARCHAR(30) NOT NULL,
         operacion VARCHAR(120) NOT NULL,
         monto_usd DECIMAL(12,2) NOT NULL DEFAULT 0.00,
         replica_api VARCHAR(40) NOT NULL DEFAULT 'api_lacava_1',
         fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
     );
     ```

2. **En `BD 2` (`100.77.220.102:27017`, base MongoDB `quito_nosql_mongo`):**
   - Colección `logs_auditoria`
   - Colección `eventos_agentes`

3. **En `BD 3` (`100.77.220.102:3308`, base `quito_paralela_db`, user `root`, pass `1597.MyHql`):**
   - Tabla particionada con **`PARTITION BY HASH(id) PARTITIONS 4`**:
     ```sql
     CREATE DATABASE IF NOT EXISTS quito_paralela_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
     USE quito_paralela_db;

     CREATE TABLE IF NOT EXISTS historico_transacciones (
         id INT AUTO_INCREMENT,
         sede_origen VARCHAR(30) NOT NULL DEFAULT 'QUITO_PARALELA',
         usuario_rbac VARCHAR(30) NOT NULL,
         rol_rbac VARCHAR(30) NOT NULL,
         modulo VARCHAR(30) NOT NULL,
         codigo_referencia VARCHAR(40) NOT NULL,
         monto_usd DECIMAL(12,2) NOT NULL,
         particion_hash INT GENERATED ALWAYS AS (MOD(id, 4)) VIRTUAL,
         fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
         PRIMARY KEY (id)
     )
     PARTITION BY HASH(id)
     PARTITIONS 4;
     ```

---

### TAREA 1.3: Ejecutar los 3 Agentes IA de Quito (`agentes_quito.py`) Apuntando a la Laptop (`100.123.81.4`)

Crea y ejecuta en la PC de Escritorio el script `agentes_quito.py` apuntando al Balanceador de la Laptop (`http://100.123.81.4:8000/api`):

```python
import asyncio
from datetime import datetime
import random
import httpx

# IP Tailscale de la Laptop (Nodo Guayaquil + Balanceador 3 Réplicas API)
API_URL_LAPTOP = "http://100.123.81.4:8000/api/agentes/operacion"

USUARIOS_15_RBAC = [
    ("c_jefe", "rol_jefe", "COMPRAS"),
    ("c_supervisor", "rol_supervisor", "COMPRAS"),
    ("c_operador", "rol_operador", "COMPRAS"),
    ("i_jefe", "rol_jefe", "INVENTARIOS"),
    ("i_supervisor", "rol_supervisor", "INVENTARIOS"),
    ("i_operador", "rol_operador", "INVENTARIOS"),
    ("v_jefe", "rol_jefe", "VENTAS"),
    ("v_supervisor", "rol_supervisor", "VENTAS"),
    ("v_operador", "rol_operador", "VENTAS"),
    ("th_jefe", "rol_jefe", "TALENTO_HUMANO"),
    ("th_supervisor", "rol_supervisor", "TALENTO_HUMANO"),
    ("th_operador", "rol_operador", "TALENTO_HUMANO"),
    ("ctbl_jefe", "rol_jefe", "CONTABILIDAD"),
    ("ctbl_supervisor", "rol_supervisor", "CONTABILIDAD"),
    ("ctbl_operador", "rol_operador", "CONTABILIDAD"),
]

async def ciclo_agentes_quito(ciclo: int):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === RONDA #{ciclo}: 3 AGENTES IA NODO QUITO (100.77.220.102 -> 100.123.81.4) ===")
    u1, r1, m1 = random.choice(USUARIOS_15_RBAC)
    u2, r2, m2 = random.choice(USUARIOS_15_RBAC)
    u3, r3, m3 = random.choice(USUARIOS_15_RBAC)

    async with httpx.AsyncClient(timeout=10.0) as client:
        r_a1, r_a2, r_a3 = await asyncio.gather(
            # Agente 1 -> X-Sede: QUITO (BD 1 :3307)
            client.post(
                API_URL_LAPTOP,
                headers={"X-Sede": "QUITO"},
                json={
                    "agente": "Agente-1-Quito-OLTP",
                    "usuario": u1,
                    "modulo": m1,
                    "operacion": f"[PC Escritorio Quito #{ciclo}] Operación en {m1} por {u1} ({r1})",
                    "montoUsd": round(random.uniform(120.0, 1450.0), 2),
                },
            ),
            # Agente 2 -> X-Sede: QUITO_NOSQL (BD 2 MongoDB :27017)
            client.post(
                API_URL_LAPTOP,
                headers={"X-Sede": "QUITO_NOSQL"},
                json={
                    "agente": "Agente-2-Quito-MongoDB",
                    "usuario": u2,
                    "modulo": m2,
                    "operacion": f"[PC Escritorio MongoDB #{ciclo}] Log JSON y alerta de stock bajo en Quito",
                    "montoUsd": 0.0,
                    "extraJson": {"alerta": "STOCK_MINIMO", "origen": "100.77.220.102", "ciclo": ciclo},
                },
            ),
            # Agente 3 -> X-Sede: QUITO_PARALELA (BD 3 Hash :3308)
            client.post(
                API_URL_LAPTOP,
                headers={"X-Sede": "QUITO_PARALELA"},
                json={
                    "agente": "Agente-3-Quito-Paralela-Hash",
                    "usuario": u3,
                    "modulo": m3,
                    "operacion": f"[PC Escritorio Speed-up #{ciclo}] Lote en PARTITION BY HASH(id) PARTITIONS 4",
                    "montoUsd": round(random.uniform(250.0, 2200.0), 2),
                },
            ),
        )
        print("  -> Agente 1 (QUITO):", r_a1.json())
        print("  -> Agente 2 (QUITO_NOSQL):", r_a2.json())
        print("  -> Agente 3 (QUITO_PARALELA):", r_a3.json())

async def main():
    c = 1
    while True:
        try:
            await ciclo_agentes_quito(c)
        except Exception as e:
            print("  [!] Error:", e)
        c += 1
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 2. VERIFICACIÓN FINAL DESDE LA PC DE ESCRITORIO
Una vez abiertos los puertos `3307`, `3308` y `27017` en la PC de Escritorio, verifica desde cualquier navegador o terminal:
- `http://100.123.81.4:8000/api/dba/health` $\rightarrow$ Debe mostrar `activeHost: "100.77.220.102"` en **BD 1**, **BD 2** y **BD 3** con `status: "ONLINE"`.
- `http://100.123.81.4:8000/api/dba/global` $\rightarrow$ Devuelve la tabla unificada de las **6 BDs** en tiempo real.
