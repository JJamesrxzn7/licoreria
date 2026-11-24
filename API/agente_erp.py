"""
Transacción real de un agente en el ERP de SU sede (lo usan los agentes 1 Quito, 4 Guayaquil y 6 Cuenca).

El agente trabaja como un usuario más de la app "La Cava" (header X-Sede-App):
    venta POS (-> entrega) · compra aprobada (-> recepción) · ingreso a bodega · despacho
Los procedimientos y triggers del ERP de esa sede guardan el documento y lo auditan en LOG_AUDITORIA con el usuario
RBAC que lo hizo. Después el agente anota en su bitácora (operaciones_agentes_ia / _cloud) qué documento tocó.
"""

import random

import generar_recepciones_entregas as app_flujo


def transaccion_agente(sede: str, agente: str, ciclo: int, rnd: random.Random | None = None) -> dict:
    """Hace la transacción en la app y devuelve el cuerpo para POST /api/agentes/operacion."""
    rnd = rnd or random.Random()
    try:
        doc = app_flujo.accion_bodega(rnd, sede)
    except Exception as exc:  # la app no pudo: queda en la bitácora como intento fallido (no se oculta)
        return {
            "agente": agente, "usuario": "v_operador", "password": app_flujo.CREDENCIALES["v_operador"], "modulo": "VENTAS",
            "operacion": f"[Ciclo #{ciclo}] FALLÓ la transacción en el ERP de {sede}: {str(exc)[:150]}", "montoUsd": 0.0,
        }
    return {
        "agente": agente,
        "usuario": doc["usuario"],
        "password": app_flujo.CREDENCIALES[doc["usuario"]],
        "modulo": doc["modulo"],
        "operacion": f"[Ciclo #{ciclo}] {doc['accion']}"[:255],
        "montoUsd": doc["monto"],
        "documentoApp": {"tabla": doc["tabla"], "id": doc["id"], "accion": doc["accion"]},
    }
