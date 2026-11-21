"""
===============================================================================
3 AGENTES IA DE QUITO (`agentes_quito.py` - Listo para PC Escritorio o Simulación)
===============================================================================
Ejecuta los 3 agentes del Nodo QUITO en paralelo cada 60 segundos apuntando a
la API de la Laptop (`http://<IP_TS_GUAYAQUIL>:8080/api` o `:8000/api`):
- Agente 1 (`X-Sede: QUITO`): Rota entre los 15 usuarios RBAC en los 5 módulos (BD 1 :3307).
- Agente 2 (`X-Sede: QUITO_NOSQL`): Envía logs JSON y alertas de stock bajo a MongoDB (BD 2 :27017).
- Agente 3 (`X-Sede: QUITO_PARALELA`): Inserta lotes históricos en la tabla particionada
  `historico_transacciones` (`PARTITION BY HASH(id) PARTITIONS 4` en BD 3 :3308).
===============================================================================
"""

import argparse
import asyncio
from datetime import datetime
import os
import random
import httpx

IP_TS_GUAYAQUIL = os.getenv("IP_TS_GUAYAQUIL", "127.0.0.1")
API_CANDIDATES = [
    f"http://{IP_TS_GUAYAQUIL}:8080/api",
    f"http://{IP_TS_GUAYAQUIL}:8000/api",
    "http://127.0.0.1:8000/api",
]

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
    raise RuntimeError(f"Error conectando a API: {last_err}")


async def run_cycle(cycle: int):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === RONDA #{cycle}: 3 AGENTES IA NODO QUITO ===")
    async with httpx.AsyncClient() as client:
        u1, r1, m1 = random.choice(USUARIOS_15_RBAC)
        u2, r2, m2 = random.choice(USUARIOS_15_RBAC)
        u3, r3, m3 = random.choice(USUARIOS_15_RBAC)

        await asyncio.gather(
            post_with_failover(
                client,
                {"X-Sede": "QUITO"},
                {
                    "agente": "Agente-1-Quito-OLTP",
                    "usuario": u1,
                    "modulo": m1,
                    "operacion": f"[Quito OLTP #{cycle}] Transacción en módulo {m1} ejecutada por {u1} ({r1})",
                    "montoUsd": round(random.uniform(95.0, 1200.0), 2),
                },
            ),
            post_with_failover(
                client,
                {"X-Sede": "QUITO_NOSQL"},
                {
                    "agente": "Agente-2-Quito-MongoDB",
                    "usuario": u2,
                    "modulo": m2,
                    "operacion": f"[MongoDB NoSQL #{cycle}] Log JSON de telemetría y alerta de stock bajo en Quito",
                    "montoUsd": 0.0,
                    "extraJson": {"alerta": "STOCK_BAJO", "producto": "PRO-001", "ciclo": cycle},
                },
            ),
            post_with_failover(
                client,
                {"X-Sede": "QUITO_PARALELA"},
                {
                    "agente": "Agente-3-Quito-Paralela-Hash",
                    "usuario": u3,
                    "modulo": m3,
                    "operacion": f"[Speed-up Hash #{cycle}] Inserción masiva en PARTITION BY HASH(id) PARTITIONS 4",
                    "montoUsd": round(random.uniform(150.0, 1800.0), 2),
                },
            ),
        )
        print("  -> OK: Agente 1 (QUITO :3307), Agente 2 (QUITO_NOSQL :27017) y Agente 3 (QUITO_PARALELA :3308) completados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    async def loop():
        c = 1
        while True:
            await run_cycle(c)
            if args.once:
                break
            c += 1
            await asyncio.sleep(args.interval)

    asyncio.run(loop())
