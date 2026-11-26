"""
BD 2 (MongoDB, Quito): almacén DOCUMENTAL de eventos del negocio, alimentado con datos REALES de los 3 ERP.

Cada vez que el Agente 2 llama a la API (X-Sede: QUITO_NOSQL), se sincroniza:

  eventos_negocio  Un documento por hecho de negocio leído del LOG_AUDITORIA de cada ERP (por log_seq, como un CDC).
                   Cada TIPO de evento trae campos distintos en la MISMA colección (esquema flexible):
                     VENTA_REGISTRADA     -> factura, cliente, total y un ARREGLO embebido de productos
                     ORDEN_COMPRA_CREADA  -> orden, proveedor, entrega y su arreglo de productos
                     FACTURA_APROBADA / FACTURA_ANULADA / ORDEN_COMPRA_* -> estado antes y después
                     ENTREGA_DESPACHADA / RECEPCION_INGRESADA -> documento y estado
                     CLIENTE_REGISTRADO / CLIENTE_EDITADO -> en la edición, solo los campos que cambiaron
  alertas_stock    Un documento por producto bajo el umbral de reposición, con su HISTORIAL embebido (arreglo).
  eventos_agentes  Lo que hizo el Agente 2 en esa corrida (resumen de lo sincronizado).
  logs_auditoria   Auditoría de cada corrida del agente NoSQL (quién, cuándo, desde dónde, cuántos documentos).
  control_sync     Marca de agua (último log_seq leído) por sede: la sincronización es incremental e idempotente.
"""

import json
import os
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from pymongo import ReplaceOne, UpdateOne

UMBRAL_STOCK = int(os.getenv("NOSQL_UMBRAL_STOCK", "500"))
LOTE = 400
TABLAS = ("FACTURAS", "PROXFAC", "COMPRAS", "PROXOC", "ENTREGAS", "RECEPCIONES", "CLIENTES")


def _dict(texto: Any) -> dict[str, Any]:
    try:
        d = json.loads(texto) if texto else {}
        return {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _txt(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


def _num(v: Any) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _eventos_de_lote(sede: str, filas: list[tuple], usuarios: dict[str, str]) -> list[dict[str, Any]]:
    """Convierte cambios del log en documentos de negocio. Las líneas (PROxFAC / PROxOC) se EMBEBEN en su documento."""
    lineas: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for _seq, _usr, _f, tabla, accion, _ant, nuevo in filas:
        t = tabla.upper()
        if accion == "INSERT" and t in ("PROXFAC", "PROXOC"):
            n = _dict(nuevo)
            clave = ("FAC", _txt(n.get("id_factura"))) if t == "PROXFAC" else ("OC", _txt(n.get("id_compra")))
            lineas.setdefault(clave, []).append({
                "producto": _txt(n.get("id_producto")),
                "cantidad": n.get("pxf_cantidad", n.get("pxo_cantidad")),
                "precio": _num(n.get("pxf_precio", n.get("pxo_valor"))),
                "subtotal": _num(n.get("pxf_subtotal", n.get("pxo_subtotal"))),
            })

    eventos = []
    for seq, id_usr, fecha, tabla, accion, anterior, nuevo in filas:
        t, a, n = tabla.upper(), accion, _dict(nuevo)
        base = {"_id": f"{sede}-{seq}", "sede": sede, "log_seq": int(seq), "fecha": fecha,
                "usuario": usuarios.get(str(id_usr or "").strip(), _txt(id_usr) or "sistema"), "tabla_origen": t}
        if t == "FACTURAS" and a == "INSERT":
            fac = _txt(n.get("id_factura"))
            # Un solo documento por factura (el ERP deja 2 filas de INSERT: la completa y la del trigger original)
            eventos.append({**base, "_id": f"{sede}-VENTA-{fac}", "_fusionar": True, "tipo": "VENTA_REGISTRADA", "factura": fac, "cliente": _txt(n.get("id_cliente")),
                            "forma_pago": _txt(n.get("fac_formapago")), "total": _num(n.get("fac_total")),
                            "productos": lineas.get(("FAC", fac), [])})
        elif t == "COMPRAS" and a == "INSERT":
            oc = _txt(n.get("id_compra"))
            eventos.append({**base, "_id": f"{sede}-OC-{oc}", "_fusionar": True, "tipo": "ORDEN_COMPRA_CREADA", "orden": oc, "proveedor": _txt(n.get("id_proveedor")),
                            "fecha_entrega": n.get("oc_fechaentrega"), "total": _num(n.get("oc_total")),
                            "productos": lineas.get(("OC", oc), [])})
        elif a == "UPDATE" and t in ("FACTURAS", "COMPRAS", "ENTREGAS", "RECEPCIONES"):
            v = _dict(anterior)
            campo = {"FACTURAS": "estado_fac", "COMPRAS": "estado_oc", "ENTREGAS": "estado_ent", "RECEPCIONES": "estado_rec"}[t]
            antes, despues = _txt(v.get(campo)), _txt(n.get(campo))
            if t == "FACTURAS" and (not despues or antes == despues):
                # El POS crea la factura y luego le pone cliente y totales con un UPDATE: se completa la venta ya guardada
                eventos.append({"_parche": True, "factura": _txt(n.get("id_factura")),
                                "set": {k2: v2 for k2, v2 in {"cliente": _txt(n.get("id_cliente")), "forma_pago": _txt(n.get("fac_formapago")),
                                                              "subtotal": _num(n.get("fac_subtotal")), "iva": _num(n.get("fac_iva")),
                                                              "total": _num(n.get("fac_total"))}.items() if v2 not in (None, "")}})
                continue
            if not despues or antes == despues:
                continue  # actualizaciones internas sin cambio de estado
            if t == "FACTURAS":
                tipo = {"APR": "FACTURA_APROBADA", "ANU": "FACTURA_ANULADA"}.get(despues, "FACTURA_CAMBIO_ESTADO")
                extra = {"factura": _txt(n.get("id_factura")), "total": _num(n.get("fac_total"))}
            elif t == "COMPRAS":
                tipo = {"APR": "ORDEN_COMPRA_APROBADA", "ANU": "ORDEN_COMPRA_ANULADA"}.get(despues, "ORDEN_COMPRA_CAMBIO_ESTADO")
                extra = {"orden": _txt(n.get("id_compra")), "total": _num(n.get("oc_total"))}
            elif t == "ENTREGAS":
                tipo, extra = "ENTREGA_DESPACHADA", {"entrega": _txt(n.get("id_entrega")), "factura": _txt(n.get("id_factura"))}
            else:
                tipo, extra = "RECEPCION_INGRESADA", {"recepcion": _txt(n.get("id_recibo")), "orden": _txt(n.get("id_compra"))}
            eventos.append({**base, "tipo": tipo, **extra, "estado": {"antes": antes, "despues": despues}})
        elif t == "CLIENTES" and a == "INSERT":
            eventos.append({**base, "tipo": "CLIENTE_REGISTRADO", "cliente": _txt(n.get("id_cliente")),
                            "nombre": _txt(n.get("cli_nombre")), "ciudad": _txt(n.get("id_ciudad"))})
        elif t == "CLIENTES" and a == "UPDATE":
            v = _dict(anterior)
            cambios = {k: {"antes": _txt(v.get(k)), "despues": _txt(n.get(k))} for k in n if _txt(v.get(k)) != _txt(n.get(k))}
            if cambios:
                eventos.append({**base, "tipo": "CLIENTE_EDITADO", "cliente": _txt(n.get("id_cliente")), "cambios": cambios})
    return eventos


def sincronizar(db, conectar_erp, usuario_agente: str, rol: str, ip: str) -> dict[str, Any]:
    """
    Una corrida del Agente 2. `conectar_erp(sede)` devuelve (conexión, es_postgres) del ERP de esa sede.
    Devuelve el resumen que queda en eventos_agentes.
    """
    t0 = time.perf_counter()
    resumen: dict[str, Any] = {"eventos_por_sede": {}, "eventos_por_tipo": {}, "alertas_stock": 0, "errores": {}}
    for sede in ("QUITO", "GUAYAQUIL", "CUENCA"):
        ctrl = db["control_sync"].find_one({"_id": sede}) or {}
        marca = int(ctrl.get("ultimo_log_seq", 0))
        try:
            conn, es_pg = conectar_erp(sede)
            try:
                cur = conn.cursor()
                marcas = ", ".join(["%s"] * len(TABLAS))
                cur.execute(f"SELECT log_seq, id_usuario, log_fechahora, log_tablaafectada, log_accion, log_valoranterior, "
                            f"log_valornuevo FROM log_auditoria WHERE log_seq > %s AND UPPER(log_tablaafectada) IN ({marcas}) "
                            f"ORDER BY log_seq LIMIT {LOTE}", (marca, *TABLAS))
                filas = cur.fetchall()
                cur.execute("SELECT id_usuario, usr_username FROM usuarios")
                usuarios = {str(a).strip(): str(b).strip() for a, b in cur.fetchall()}
                alertas = []
                if sede == "QUITO":  # las alertas de reposición son de la bodega de Quito (la sede de esta BD)
                    cur.execute("SELECT id_producto, pro_descripcion, pro_saldo_final FROM productos WHERE pro_saldo_final < %s "
                                "ORDER BY pro_saldo_final", (UMBRAL_STOCK,))
                    alertas = cur.fetchall()
                cur.close()
            finally:
                conn.close()
        except Exception as exc:
            resumen["errores"][sede] = str(exc)[:160]
            continue

        todos = _eventos_de_lote(sede, filas, usuarios)
        eventos = [e for e in todos if not e.get("_parche")]
        # Escritura por lotes (una sola ida y vuelta por la VPN). Idempotente: el _id es sede-log_seq
        ops = []
        for ev in eventos:
            if ev.get("_fusionar"):
                # Fusión: solo se escriben los campos que traen valor, así la fila incompleta no borra a la completa
                campos = {k: v for k, v in ev.items() if k not in ("_id", "_fusionar") and v not in (None, "", [])}
                ops.append(UpdateOne({"_id": ev["_id"]}, {"$set": campos}, upsert=True))
            else:
                ops.append(ReplaceOne({"_id": ev["_id"]}, ev, upsert=True))
        ops += [UpdateOne({"_id": f"{sede}-VENTA-{p['factura']}"}, {"$set": p["set"]})
                for p in todos if p.get("_parche") and p["set"]]
        if ops:
            db["eventos_negocio"].bulk_write(ops, ordered=True)  # en orden: la venta existe antes de completarla
        unicos = {ev["_id"]: ev for ev in eventos}.values()
        for ev in unicos:
            resumen["eventos_por_tipo"][ev["tipo"]] = resumen["eventos_por_tipo"].get(ev["tipo"], 0) + 1
        resumen["eventos_por_sede"][sede] = len(unicos)
        if filas:
            db["control_sync"].update_one({"_id": sede}, {"$set": {"ultimo_log_seq": int(filas[-1][0]), "actualizado": datetime.now()}},
                                          upsert=True)

        for id_p, nombre, stock in alertas:
            stock = int(stock or 0)
            db["alertas_stock"].update_one(
                {"_id": f"QUITO-{str(id_p).strip()}"},
                {"$set": {"sede": "QUITO", "producto": str(id_p).strip(), "nombre": str(nombre).strip(), "stock_actual": stock,
                          "umbral_reposicion": UMBRAL_STOCK, "faltan_para_umbral": UMBRAL_STOCK - stock,
                          "nivel": "CRITICO" if stock < UMBRAL_STOCK * 0.5 else "BAJO", "ultima_revision": datetime.now()},
                 # el historial embebido guarda las últimas 20 lecturas (operador $push + $slice)
                 "$push": {"historial": {"$each": [{"fecha": datetime.now(), "stock": stock}], "$slice": -20}}},
                upsert=True,
            )
        resumen["alertas_stock"] += len(alertas) if sede == "QUITO" else 0

    total = sum(resumen["eventos_por_sede"].values())
    ms = round((time.perf_counter() - t0) * 1000, 1)
    evento_id = f"AGT2-{uuid4().hex[:8].upper()}"
    ahora = datetime.now().isoformat()
    tipos = ", ".join(f"{k} x{v}" for k, v in sorted(resumen["eventos_por_tipo"].items())) or "sin cambios nuevos"
    db["eventos_agentes"].insert_one({
        "evento_id": evento_id, "agente": "Agente-2-Quito-MongoDB", "header_x_sede": "QUITO_NOSQL", "version": 2,
        "usuario_rbac": usuario_agente, "rol_rbac": rol, "modulo": "NOSQL",
        "mensaje": f"Sincronización documental: {total} eventos de negocio nuevos ({tipos}); {resumen['alertas_stock']} alertas de stock",
        "detalle": resumen, "duracion_ms": ms, "timestamp": ahora,
    })
    db["logs_auditoria"].insert_one({
        "evento_id": evento_id, "accion": "SINCRONIZACION_NOSQL", "version": 2, "usuario_rbac": usuario_agente, "rol_rbac": rol,
        "ip": ip, "colecciones_escritas": ["eventos_negocio", "alertas_stock", "control_sync", "eventos_agentes"],
        "documentos": {"eventos_negocio": total, "alertas_stock": resumen["alertas_stock"]},
        "errores": resumen["errores"], "timestamp": ahora,
    })
    return {"evento_id": evento_id, "total": total, "resumen": resumen, "ms": ms}
