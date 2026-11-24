"""
===============================================================================
TAREA 2.4 DE LA LAPTOP: 3 AGENTES IA DE GUAYAQUIL Y CUENCA (`agentes_gye_cuenca.py`)
===============================================================================
Script asíncrono en Python que ejecuta 3 agentes en paralelo cada 60 segundos
contra el Balanceador de la API (`http://127.0.0.1:8000/api`), enviando el
Header obligatorio `X-Sede` y autenticándose con las credenciales reales de la
matriz de 15 usuarios por módulo + DBA + Admin:

- Agente 4 (`X-Sede: GUAYAQUIL`):
  Hace transacciones REALES en el ERP de Guayaquil (BD 4, MariaDB :3307) usando la app:
  venta POS, compra aprobada, ingreso a bodega o despacho; todo queda en LOG_AUDITORIA.
- Agente 5 (`X-Sede: GUAYAQUIL_DWH`):
  Ejecuta un mini-ETL cada minuto consolidando ventas hacia BD 5 (`db_gye_dwh`
  en MariaDB `:3309` con esquema estrella para Power BI).
- Agente 6 (`X-Sede: CUENCA`):
  Igual que el 4 pero en el ERP PostgreSQL de Cuenca (BD 6 `:5432` lacava_cuenca),
  midiendo la latencia hasta el nodo.
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
import agente_erp  # noqa: E402  (transacciones reales en el ERP de cada sede: POS, compras, bodega)

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


async def run_agente_erp(client: httpx.AsyncClient, cycle: int, num: int, sede: str, agente: str):
    """
    Agente 4 (Guayaquil) y Agente 6 (Cuenca): hacen una transacción REAL en el ERP de su sede usando la app
    (venta POS, compra aprobada, ingreso a bodega o despacho). El ERP la guarda y la audita con el usuario RBAC;
    luego el agente la anota en su bitácora enlazada al documento.
    """
    t0 = asyncio.get_running_loop().time()
    payload = await asyncio.to_thread(agente_erp.transaccion_agente, sede, agente, cycle)
    res = await post_with_failover(client, {"X-Sede": sede}, payload)
    ms = round((asyncio.get_running_loop().time() - t0) * 1000)
    doc = payload.get("documentoApp") or {}
    print(f"  [Agente {num} | ERP {sede}] {payload['operacion'][:110]} | Usr: {payload['usuario']} | "
          f"doc {doc.get('tabla', '-')}:{doc.get('id', '-')} | bitácora id {res['operationId']} | {ms} ms")
    return res


async def run_agente_5_guayaquil_dwh(client: httpx.AsyncClient, cycle: int):
    """Agente 5 (X-Sede: GUAYAQUIL_DWH): ETL incremental cada minuto desde el log de los 3 ERP hacia el esquema estrella de BD 5."""
    user, password, rol, _, _ = random.choice([u for u in USUARIOS_15_RBAC if u[3] in ("VENTAS", "CONTABILIDAD")])
    payload = {
        "agente": "Agente-5-Guayaquil-ETL-DWH",
        "usuario": user,
        "password": password,
        "modulo": "VENTAS",
        "operacion": f"[Mini-ETL #{cycle}] CDC: líneas de venta nuevas de los 3 ERP (LOG_AUDITORIA) -> fact_ventas de BD 5",
        "montoUsd": 0.0,
    }
    res = await post_with_failover(client, {"X-Sede": "GUAYAQUIL_DWH", "X-Agent-User": user, "X-Agent-Role": rol}, payload)
    fuentes = [i for i in res.get("impacto", []) if str(i.get("tabla", "")).startswith("ETL ")]
    detalle = " · ".join(f"{i['tabla'].split()[1]}: {i.get('accion', '')[:40] if i.get('ok') else 'OFFLINE'}" for i in fuentes)
    print(f"  [Agente 5 | ETL -> BD 5 :3309] lote {res.get('operationId')} | {detalle} | {res['latencyMs']} ms")
    return res


async def run_cycle(cycle: int):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === RONDA #{cycle}: EJECUTANDO 3 AGENTES IA (LAPTOP: GYE + DWH + CUENCA) ===")
    async with httpx.AsyncClient() as client:
        resultados = await asyncio.gather(
            run_agente_erp(client, cycle, 4, "GUAYAQUIL", "Agente-4-Guayaquil-OLTP"),
            run_agente_5_guayaquil_dwh(client, cycle),
            run_agente_erp(client, cycle, 6, "CUENCA", "Agente-6-Cuenca-ERP-PostgreSQL"),
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
