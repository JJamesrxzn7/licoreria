"""
===============================================================================
TAREA 2.4 DE LA LAPTOP: 3 AGENTES IA DE GUAYAQUIL Y CUENCA (`agentes_gye_cuenca.py`)
===============================================================================
Script asíncrono en Python que ejecuta 3 agentes en paralelo cada 60 segundos
contra el Balanceador de la API (`http://localhost:8080/api` con fallback a `:8000/api`),
enviando el Header obligatorio `X-Sede` y autenticándose con la matriz de
15 usuarios y 3 roles RBAC (`rol_jefe`, `rol_supervisor`, `rol_operador`):

- Agente 4 (`X-Sede: GUAYAQUIL`):
  Rota aleatoriamente entre los 15 usuarios RBAC y simula operaciones de los
  5 módulos (`C`, `I`, `V`, `TH`, `Ctbl`) en la BD 4 (MariaDB Local `:3306`).
- Agente 5 (`X-Sede: GUAYAQUIL_DWH`):
  Ejecuta un mini-ETL cada minuto consolidando ventas hacia la BD 5
  (`db_gye_dwh` en MariaDB `:3309` con esquema estrella para Power BI).
- Agente 6 (`X-Sede: CUENCA`):
  Inserta transacciones en Supabase / PostgreSQL (BD 6 `:5432`) para medir
  la latencia WAN en tiempo real.

Uso:
  python agentes_gye_cuenca.py          # Ciclo continuo cada 60 segundos
  python agentes_gye_cuenca.py --once   # Ejecuta 1 ronda inmediata de los 3 agentes y termina
===============================================================================
"""

import argparse
import asyncio
from datetime import datetime
import os
import random
import httpx

API_CANDIDATES = [
    os.getenv("API_URL_LAPTOP", "http://127.0.0.1:8000/api"),
    "http://127.0.0.1:8080/api",
]

# Matriz oficial de 15 Usuarios y 3 Roles RBAC
USUARIOS_15_RBAC = [
    ("c_jefe", "rol_jefe", "COMPRAS", "Orden de compra aprobada a Cervecería Nacional GYE"),
    ("c_supervisor", "rol_supervisor", "COMPRAS", "Supervisión de recepción en Puerto Marítimo Guayaquil"),
    ("c_operador", "rol_operador", "COMPRAS", "Registro de cotización de licores importados Costa"),
    ("i_jefe", "rol_jefe", "INVENTARIOS", "Aprobación de ajuste físico en Bodega Vía a Daule"),
    ("i_supervisor", "rol_supervisor", "INVENTARIOS", "Auditoría de stock de reserva en Guayaquil"),
    ("i_operador", "rol_operador", "INVENTARIOS", "Movimiento de percha y despacho regional Costa"),
    ("v_jefe", "rol_jefe", "VENTAS", "Factura corporativa aprobada para Hotel Oro Verde GYE"),
    ("v_supervisor", "rol_supervisor", "VENTAS", "Autorización de descuento mayorista en Samborondón"),
    ("v_operador", "rol_operador", "VENTAS", "Emisión de comprobante POS en Sucursal Guayaquil"),
    ("th_jefe", "rol_jefe", "TALENTO_HUMANO", "Aprobación de rol de pagos mensual personal Guayaquil"),
    ("th_supervisor", "rol_supervisor", "TALENTO_HUMANO", "Control de turnos de bodega y logística Costa"),
    ("th_operador", "rol_operador", "TALENTO_HUMANO", "Actualización de ficha de personal en Sucursal GYE"),
    ("ctbl_jefe", "rol_jefe", "CONTABILIDAD", "Cierre diario y mayorización de asientos de Guayaquil"),
    ("ctbl_supervisor", "rol_supervisor", "CONTABILIDAD", "Conciliación bancaria cuenta recaudadora Costa"),
    ("ctbl_operador", "rol_operador", "CONTABILIDAD", "Registro de retención electrónica SRI en Guayaquil"),
]


async def post_with_failover(client: httpx.AsyncClient, headers: dict, payload: dict) -> dict:
    last_err = None
    for base in API_CANDIDATES:
        url = f"{base.rstrip('/')}/agentes/operacion"
        try:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"No se pudo conectar a la API en {API_CANDIDATES}: {last_err}")


async def run_agente_4_guayaquil(client: httpx.AsyncClient, cycle: int):
    """Agente 4 (X-Sede: GUAYAQUIL): Opera con los 15 usuarios en los 5 módulos sobre BD 4 (:3306)."""
    user, rol, modulo, desc = random.choice(USUARIOS_15_RBAC)
    monto = round(random.uniform(85.0, 1450.0), 2)
    headers = {
        "X-Sede": "GUAYAQUIL",
        "X-Agent-User": user,
        "X-Agent-Role": rol,
    }
    payload = {
        "agente": "Agente-4-Guayaquil-OLTP",
        "usuario": user,
        "modulo": modulo,
        "operacion": f"[Ciclo #{cycle}] {desc} (Usuario: {user} / Rol: {rol})",
        "montoUsd": monto,
    }
    res = await post_with_failover(client, headers, payload)
    print(
        f"  [Agente 4 | X-Sede: GUAYAQUIL -> {res['routedTo']} :{res['port']}] "
        f"Usr: {user} ({rol}) | Mod: {modulo} | Replica: {res['apiReplica']} | {res['latencyMs']} ms"
    )
    return res


async def run_agente_5_guayaquil_dwh(client: httpx.AsyncClient, cycle: int):
    """Agente 5 (X-Sede: GUAYAQUIL_DWH): Mini-ETL cada minuto consolidando ventas hacia BD 5 (:3309)."""
    user, rol, _, _ = random.choice([u for u in USUARIOS_15_RBAC if u[2] in ("VENTAS", "CONTABILIDAD")])
    monto_etl = round(random.uniform(420.0, 2850.0), 2)
    headers = {
        "X-Sede": "GUAYAQUIL_DWH",
        "X-Agent-User": user,
        "X-Agent-Role": rol,
    }
    payload = {
        "agente": "Agente-5-Guayaquil-ETL-DWH",
        "usuario": user,
        "modulo": "VENTAS",
        "operacion": f"[Mini-ETL #{cycle}] Consolidación OLTP -> Esquema Estrella BD 5 (:3309 fact_ventas) para Power BI",
        "montoUsd": monto_etl,
    }
    res = await post_with_failover(client, headers, payload)
    print(
        f"  [Agente 5 | X-Sede: GUAYAQUIL_DWH -> {res['routedTo']} :{res['port']}] "
        f"ETL Power BI (${monto_etl}) | Usr: {user} | Replica: {res['apiReplica']} | {res['latencyMs']} ms"
    )
    return res


async def run_agente_6_cuenca_cloud(client: httpx.AsyncClient, cycle: int):
    """Agente 6 (X-Sede: CUENCA): Inserta transacciones en Supabase / PostgreSQL BD 6 (:5432) y mide latencia WAN."""
    user, rol, modulo, _ = random.choice(USUARIOS_15_RBAC)
    monto_cloud = round(random.uniform(110.0, 960.0), 2)
    headers = {
        "X-Sede": "CUENCA",
        "X-Agent-User": user,
        "X-Agent-Role": rol,
    }
    payload = {
        "agente": "Agente-6-Cuenca-Supabase-Cloud",
        "usuario": user,
        "modulo": modulo,
        "operacion": f"[Cloud WAN #{cycle}] Transacción Austral Cuenca/Loja en Supabase DBaaS (Zhumir/Cristal)",
        "montoUsd": monto_cloud,
    }
    res = await post_with_failover(client, headers, payload)
    print(
        f"  [Agente 6 | X-Sede: CUENCA -> {res['routedTo']} :{res['port']}] "
        f"Usr: {user} ({rol}) | Mod: {modulo} | Replica: {res['apiReplica']} | Latencia WAN: {res['latencyMs']} ms"
    )
    return res


async def run_cycle(cycle: int):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === RONDA #{cycle}: EJECUTANDO 3 AGENTES IA (LAPTOP: GYE + DWH + CUENCA) ===")
    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            run_agente_4_guayaquil(client, cycle),
            run_agente_5_guayaquil_dwh(client, cycle),
            run_agente_6_cuenca_cloud(client, cycle),
        )


async def main(run_once: bool = False, interval: int = 60):
    cycle = 1
    while True:
        try:
            await run_cycle(cycle)
        except Exception as exc:
            print(f"  [!] Error en ronda #{cycle}: {exc}")
        if run_once:
            break
        cycle += 1
        await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3 Agentes IA Asíncronos de Guayaquil y Cuenca (Laptop)")
    parser.add_argument("--once", action="store_true", help="Ejecuta una sola ronda de los 3 agentes y termina")
    parser.add_argument("--interval", type=int, default=60, help="Intervalo en segundos entre rondas (default: 60)")
    args = parser.parse_args()
    asyncio.run(main(run_once=args.once, interval=args.interval))
