"""
===============================================================================
TAREA 2.4 DE LA LAPTOP: 3 AGENTES IA DE GUAYAQUIL Y CUENCA (`agentes_gye_cuenca.py`)
===============================================================================
Script asíncrono en Python que ejecuta 3 agentes en paralelo cada 60 segundos
contra el Balanceador de la API (`http://127.0.0.1:8000/api`), enviando el
Header obligatorio `X-Sede` y autenticándose con las credenciales reales de la
matriz de 15 usuarios por módulo + DBA + Admin:

- Agente 4 (`X-Sede: GUAYAQUIL`):
  Rota entre los 15 usuarios RBAC (con su contraseña real) y simula operaciones
  de los 5 módulos (`C`, `I`, `V`, `TH`, `Ctbl`) en BD 4 (MariaDB Local `:3306`).
- Agente 5 (`X-Sede: GUAYAQUIL_DWH`):
  Ejecuta un mini-ETL cada minuto consolidando ventas hacia BD 5 (`db_gye_dwh`
  en MariaDB `:3309` con esquema estrella para Power BI).
- Agente 6 (`X-Sede: CUENCA`):
  Inserta transacciones en Supabase / PostgreSQL (BD 6 `:5432`) para medir
  la latencia WAN en tiempo real.
===============================================================================
"""

import argparse
import asyncio
from datetime import datetime
import os
import random
import sys
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "API"))
import generar_recepciones_entregas as app_flujo  # noqa: E402  (flujos reales de la app: compras, POS, bodega)

API_CANDIDATES = [
    os.getenv("API_URL_LAPTOP", "http://127.0.0.1:8000/api"),
    "http://127.0.0.1:8080/api",
]

# Matriz oficial de 15 Usuarios Operativos con sus Contraseñas Reales y 3 Roles RBAC
USUARIOS_15_RBAC = [
    ("c_jefe", "ComprasJefe2026*", "rol_jefe", "COMPRAS", "Orden de compra aprobada a Cervecería Nacional GYE"),
    ("c_supervisor", "ComprasSup2026*", "rol_supervisor", "COMPRAS", "Supervisión de recepción en Puerto Marítimo Guayaquil"),
    ("c_operador", "ComprasOpe2026*", "rol_operador", "COMPRAS", "Registro de cotización de licores importados Costa"),
    ("i_jefe", "InveJefe2026*", "rol_jefe", "INVENTARIOS", "Aprobación de ajuste físico en Bodega Vía a Daule"),
    ("i_supervisor", "InveSup2026*", "rol_supervisor", "INVENTARIOS", "Auditoría de stock de reserva en Guayaquil"),
    ("i_operador", "InveOpe2026*", "rol_operador", "INVENTARIOS", "Movimiento de percha y despacho regional Costa"),
    ("v_jefe", "VentasJefe2026*", "rol_jefe", "VENTAS", "Factura corporativa aprobada para Hotel Oro Verde GYE"),
    ("v_supervisor", "VentasSup2026*", "rol_supervisor", "VENTAS", "Autorización de descuento mayorista en Samborondón"),
    ("v_operador", "VentasOpe2026*", "rol_operador", "VENTAS", "Emisión de comprobante POS en Sucursal Guayaquil"),
    ("th_jefe", "ThJefe2026*", "rol_jefe", "TALENTO_HUMANO", "Aprobación de rol de pagos mensual personal Guayaquil"),
    ("th_supervisor", "ThSup2026*", "rol_supervisor", "TALENTO_HUMANO", "Control de turnos de bodega y logística Costa"),
    ("th_operador", "ThOpe2026*", "rol_operador", "TALENTO_HUMANO", "Actualización de ficha de personal en Sucursal GYE"),
    ("ctbl_jefe", "CtblJefe2026*", "rol_jefe", "CONTABILIDAD", "Cierre diario y mayorización de asientos de Guayaquil"),
    ("ctbl_supervisor", "CtblSup2026*", "rol_supervisor", "CONTABILIDAD", "Conciliación bancaria cuenta recaudadora Costa"),
    ("ctbl_operador", "CtblOpe2026*", "rol_operador", "CONTABILIDAD", "Registro de retención electrónica SRI en Guayaquil"),
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


PROB_ACCION_BODEGA = float(os.getenv("AG4_PROB_BODEGA", "0.4"))


async def run_agente_4_bodega(client: httpx.AsyncClient, cycle: int):
    """
    Agente 4 trabajando como usuario de la app: crea y aprueba una compra (-> recepción), confirma una recepción,
    vende en el POS (-> entrega) o despacha una entrega. La app lo audita con el usuario RBAC que lo hizo, y el
    agente lo anota en su bitácora de BD 4 enlazado al documento.
    """
    doc = await asyncio.to_thread(app_flujo.accion_bodega)
    user = doc["usuario"]
    password, rol = next((p, r) for u, p, r, _, _ in USUARIOS_15_RBAC if u == user)
    res = await post_with_failover(client, {"X-Sede": "GUAYAQUIL"}, {
        "agente": "Agente-4-Guayaquil-OLTP",
        "usuario": user,
        "password": password,
        "modulo": doc["modulo"],
        "operacion": f"[Ciclo #{cycle}] [Bodega] {doc['accion']}"[:120],
        "montoUsd": doc["monto"],
        "documentoApp": {"tabla": doc["tabla"], "id": doc["id"], "accion": doc["accion"]},
    })
    print(f"  [Agente 4 | Bodega en la app] {doc['accion']} | Usr: {user} ({rol}) | bitácora BD 4 id {res['operationId']}")
    return res


async def run_agente_4_guayaquil(client: httpx.AsyncClient, cycle: int):
    """Agente 4 (X-Sede: GUAYAQUIL): Opera con los 15 usuarios y sus contraseñas en BD 4 (:3306)."""
    if random.random() < PROB_ACCION_BODEGA:
        try:
            return await run_agente_4_bodega(client, cycle)
        except Exception as exc:  # si la app no responde, el agente hace su operación normal
            print(f"  [!] Agente 4 bodega: {exc}. Hace su operación OLTP normal.")
    user, password, rol, modulo, desc = random.choice(USUARIOS_15_RBAC)
    monto = round(random.uniform(85.0, 1450.0), 2)
    headers = {
        "X-Sede": "GUAYAQUIL",
        "X-Agent-User": user,
        "X-Agent-Role": rol,
    }
    payload = {
        "agente": "Agente-4-Guayaquil-OLTP",
        "usuario": user,
        "password": password,
        "modulo": modulo,
        "operacion": f"[Ciclo #{cycle}] {desc} (Auth: {user} / Rol: {rol})",
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
    user, password, rol, _, _ = random.choice([u for u in USUARIOS_15_RBAC if u[3] in ("VENTAS", "CONTABILIDAD")])
    monto_etl = round(random.uniform(420.0, 2850.0), 2)
    headers = {
        "X-Sede": "GUAYAQUIL_DWH",
        "X-Agent-User": user,
        "X-Agent-Role": rol,
    }
    payload = {
        "agente": "Agente-5-Guayaquil-ETL-DWH",
        "usuario": user,
        "password": password,
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
    user, password, rol, modulo, _ = random.choice(USUARIOS_15_RBAC)
    monto_cloud = round(random.uniform(110.0, 960.0), 2)
    headers = {
        "X-Sede": "CUENCA",
        "X-Agent-User": user,
        "X-Agent-Role": rol,
    }
    payload = {
        "agente": "Agente-6-Cuenca-Supabase-Cloud",
        "usuario": user,
        "password": password,
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
        resultados = await asyncio.gather(
            run_agente_4_guayaquil(client, cycle),
            run_agente_5_guayaquil_dwh(client, cycle),
            run_agente_6_cuenca_cloud(client, cycle),
            return_exceptions=True,
        )
        for nombre, res in zip(("Agente 4", "Agente 5", "Agente 6"), resultados):
            if isinstance(res, Exception):
                print(f"  [!] {nombre}: ERROR -> {res}")
        await sincronizar_anillo(client)


async def sincronizar_anillo(client: httpx.AsyncClient):
    """Replicación en anillo Quito -> Guayaquil -> Cuenca -> Quito (una ronda por minuto)."""
    for base in API_CANDIDATES:
        try:
            resp = await client.post(f"{base.rstrip('/')}/replicacion/sincronizar", timeout=60.0)
            if resp.status_code == 200:
                for e in resp.json()["enlaces"]:
                    estado = f"{e['copiadas']} filas copiadas" if e["ok"] else f"ERROR: {e.get('error')}"
                    print(f"  [Replicación {e['enlace']}] {estado}")
                return
        except Exception as exc:
            print(f"  [!] Replicación: {exc}")
    print("  [!] Replicación: API no disponible en esta ronda")


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
