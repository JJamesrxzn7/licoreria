"""
Genera RECEPCIONES y ENTREGAS reales en la base principal de la app "La Cava" usando la API, igual que
lo haría un usuario desde la interfaz (no inserta filas a mano):

  Compras:      c_operador crea órdenes de compra  ->  c_supervisor las aprueba
                (al aprobar, la app crea la RECEPCIÓN en estado PEN)
  Bodega:       i_operador confirma algunas recepciones (una con diferencia y su motivo)
  Ventas (POS): v_operador registra ventas          ->  la app crea la ENTREGA en estado PEN
  Bodega:       i_operador confirma algunas entregas

Si un usuario no tiene permiso para un paso (403), se reintenta con `admin` y se avisa.

Uso (con la API encendida en :8000):
    python API/generar_recepciones_entregas.py [--compras 6] [--ventas 6]
"""

import argparse
import json
import os
import random
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

BASE = os.getenv("LACAVA_APP_URL", "http://127.0.0.1:8000")  # la PC de Quito apunta al balanceador de la laptop
CREDENCIALES = {
    "admin": "LaCavaAdmin2026*",
    "c_operador": "ComprasOpe2026*",
    "c_supervisor": "ComprasSup2026*",
    "i_operador": "InveOpe2026*",
    "i_supervisor": "InveSup2026*",
    "v_operador": "VentasOpe2026*",
    "v_supervisor": "VentasSup2026*",
    "v_jefe": "VentasJefe2026*",
    "c_jefe": "ComprasJefe2026*",
}
_tokens: dict[tuple[str, str], str] = {}  # (sede, usuario) -> token


def llamar(metodo: str, ruta: str, usuario: str | None = None, cuerpo: dict | None = None, sede: str = "GUAYAQUIL"):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Sede-App", sede)  # la API enruta al ERP de esa sede (Quito, Guayaquil o Cuenca)
    if metodo == "POST" and ruta == "/api/ventas":
        req.add_header("Idempotency-Key", uuid.uuid4().hex)  # el POS no duplica la venta si se reintenta
    if usuario:
        req.add_header("Authorization", f"Bearer {token(usuario, sede)}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read() or b"null")
        except ValueError:
            detalle = None
        return e.code, detalle


def token(usuario: str, sede: str = "GUAYAQUIL") -> str:
    if (sede, usuario) not in _tokens:
        st, body = llamar("POST", "/api/auth/login", None, {"username": usuario, "password": CREDENCIALES[usuario]}, sede)
        if st != 200 or not body or not body.get("token"):
            raise RuntimeError(f"No se pudo iniciar sesión como {usuario} en {sede}: {st} {body}")
        _tokens[(sede, usuario)] = body["token"]
    return _tokens[(sede, usuario)]


def como(usuario: str, metodo: str, ruta: str, cuerpo: dict | None = None, sede: str = "GUAYAQUIL"):
    """Ejecuta con el usuario del módulo en el ERP de `sede`; si no tiene permiso, reintenta con admin."""
    st, body = llamar(metodo, ruta, usuario, cuerpo, sede)
    if st == 401:  # token vencido: nuevo inicio de sesión y un reintento
        _tokens.pop((sede, usuario), None)
        st, body = llamar(metodo, ruta, usuario, cuerpo, sede)
    if st == 403 and usuario != "admin":
        print(f"    (aviso: {usuario} no tiene permiso para {metodo} {ruta} en {sede}; se usa admin)")
        st, body = llamar(metodo, ruta, "admin", cuerpo, sede)
    return st, body


_como = como


def _sin_permiso_es_error(st: int, body, que: str) -> None:
    if st not in (200, 201):
        raise RuntimeError(f"{que}: {st} {body}")


# Peso de cada acción en el sorteo del ciclo (las que no tienen documento elegible se descartan solas)
PESOS_ACCIONES = {
    "nueva_venta": 22, "nueva_compra": 14, "aprobar_compra": 10, "aprobar_factura": 9, "confirmar_recepcion": 9,
    "despachar_entrega": 9, "consultar": 8, "anular_factura": 5, "anular_compra": 5, "nuevo_cliente": 5, "editar_cliente": 4,
}
# Rol que ejecuta cada acción (la matriz del ERP: Operativo = VER + CREAR · Supervisor = VER + APROBAR · Jefe = VER + ANULAR)
ROL_DE_ACCION = {
    "nueva_venta": ("v_operador", "VENTAS", "CREAR"), "nuevo_cliente": ("v_operador", "VENTAS", "CREAR"),
    "editar_cliente": ("v_operador", "VENTAS", "EDITAR"), "consultar": ("v_operador", "VENTAS", "VER"),
    "nueva_compra": ("c_operador", "COMPRAS", "CREAR"),
    "aprobar_factura": ("v_supervisor", "VENTAS", "APROBAR"), "aprobar_compra": ("c_supervisor", "COMPRAS", "APROBAR"),
    "confirmar_recepcion": ("i_supervisor", "INVENTARIOS", "APROBAR"), "despachar_entrega": ("i_supervisor", "INVENTARIOS", "APROBAR"),
    "anular_factura": ("v_jefe", "VENTAS", "ANULAR"), "anular_compra": ("c_jefe", "COMPRAS", "ANULAR"),
}
# Cuenca (API PostgreSQL) todavía no expone alta/edición de clientes: allí esas dos acciones no se sortean
SOLO_MARIADB = {"nuevo_cliente", "editar_cliente"}
PREFIJO_CLIENTE_AGENTE = "Cliente Agente"


def accion_bodega(rnd: random.Random | None = None, sede: str = "GUAYAQUIL", forzar: str | None = None) -> dict:
    """
    UNA acción real en el ERP de `sede`, hecha con la app por el usuario RBAC que le corresponde
    (la usan los agentes 1, 4 y 6). El ciclo de vida completo de los documentos:
      Operativo  (VER + CREAR):   venta POS, orden de compra, cliente nuevo, edición de un cliente, consulta (SELECT)
      Supervisor (VER + APROBAR): aprobar factura, aprobar orden de compra, ingreso a bodega, despacho
      Jefe       (VER + ANULAR):  anular factura, anular orden de compra (en el ERP no se borra un documento: se ANULA)
    Los triggers del ERP auditan cada cambio con ese usuario.
    Devuelve: {usuario, modulo, tabla, id, accion, monto, tipo}.
    """
    rnd = rnd or random.Random()

    def como(usuario, metodo, ruta, cuerpo=None):  # noqa: F811  (misma función, fijada a la sede y SIN plan B con admin)
        st, body = llamar(metodo, ruta, usuario, cuerpo, sede)
        if st == 401:
            _tokens.pop((sede, usuario), None)
            st, body = llamar(metodo, ruta, usuario, cuerpo, sede)
        return st, body

    def lista(usuario, ruta):
        st, body = como(usuario, "GET", ruta)
        _sin_permiso_es_error(st, body, f"{usuario} no pudo consultar {ruta}")
        return body or []

    # Lo que hay pendiente en este ERP (cada rol consulta lo de su módulo)
    facturas = lista("v_supervisor", "/api/ventas")
    compras = lista("c_supervisor", "/api/compras")
    recepciones = lista("i_supervisor", "/api/recepciones")
    entregas = lista("i_supervisor", "/api/entregas")
    clientes = lista("v_operador", "/api/clientes")
    fac_abiertas = [f for f in facturas if str(f.get("status")).upper() == "ABI"]
    oc_pendientes = [o for o in compras if str(o.get("estado")).upper() not in ("APR", "ANU")]
    rec_pend = [r for r in recepciones if str(r.get("status")).upper() == "PEN"]
    ent_pend = [e for e in entregas if str(e.get("status")).upper() == "PEN"]
    fac_con_entrega_pend = {str(e.get("invoiceId")) for e in ent_pend}
    # Se anula solo lo que todavía no salió de bodega: factura abierta cuya entrega sigue pendiente
    fac_anulables = [f for f in fac_abiertas if str(f.get("id")) in fac_con_entrega_pend]
    clientes_agente = [c for c in clientes if str(c.get("name", "")).startswith(PREFIJO_CLIENTE_AGENTE)]

    disponibles = {
        "nueva_venta": True, "nueva_compra": True, "consultar": True, "nuevo_cliente": True,
        "aprobar_factura": bool(fac_abiertas), "aprobar_compra": bool(oc_pendientes),
        "confirmar_recepcion": bool(rec_pend), "despachar_entrega": bool(ent_pend),
        "anular_factura": bool(fac_anulables), "anular_compra": bool(oc_pendientes),
        "editar_cliente": bool(clientes_agente),
    }
    if sede == "CUENCA":
        for a in SOLO_MARIADB:
            disponibles[a] = False
    opciones = [a for a, ok in disponibles.items() if ok]
    if forzar:  # pruebas: ejecutar una acción concreta
        if forzar not in opciones:
            raise RuntimeError(f"La acción {forzar} no está disponible ahora en {sede}")
        eleccion = forzar
    else:
        eleccion = rnd.choices(opciones, weights=[PESOS_ACCIONES[a] for a in opciones])[0]
    usuario, modulo, tipo = ROL_DE_ACCION[eleccion]

    def resultado(tabla, doc_id, accion, monto=0.0):
        return {"usuario": usuario, "modulo": modulo, "tabla": tabla, "id": doc_id, "monto": monto, "tipo": tipo,
                "accion": f"[{tipo}] {accion}"}

    if eleccion == "consultar":
        st, res = como(usuario, "GET", "/api/ventas")
        _sin_permiso_es_error(st, res, "Consultar facturas")
        abiertas = sum(1 for f in res if str(f.get("status")).upper() == "ABI")
        total = round(sum(float(f.get("total") or 0) for f in res if str(f.get("status")).upper() != "ANU"), 2)
        return resultado("FACTURAS", None, f"Consulta (SELECT) de {len(res)} facturas de {sede.title()}: {abiertas} abiertas, "
                                           f"ventas vigentes ${total}")

    if eleccion == "aprobar_factura":
        fac = rnd.choice(fac_abiertas)
        st, res = como(usuario, "POST", f"/api/ventas/{fac['id']}/aprobar")
        _sin_permiso_es_error(st, res, f"Aprobar factura {fac['id']}")
        return resultado("FACTURAS", fac["id"], f"Factura {fac['id']} de {fac.get('customerName') or fac.get('customerId')} aprobada",
                         float(fac.get("total") or 0))

    if eleccion == "anular_factura":
        fac = rnd.choice(fac_anulables)
        st, res = como(usuario, "POST", f"/api/ventas/{fac['id']}/anular")
        _sin_permiso_es_error(st, res, f"Anular factura {fac['id']}")
        return resultado("FACTURAS", fac["id"], f"Factura {fac['id']} ANULADA (no se había despachado)", float(fac.get("total") or 0))

    if eleccion == "aprobar_compra":
        oc = rnd.choice(oc_pendientes)
        st, res = como(usuario, "POST", f"/api/compras/{oc['id']}/aprobar")
        _sin_permiso_es_error(st, res, f"Aprobar orden {oc['id']}")
        return resultado("COMPRAS", oc["id"], f"Orden de compra {oc['id']} a {oc.get('proveedor') or oc.get('proveedorId')} aprobada: "
                                              f"se genera su recepción en bodega", float(oc.get("total") or 0))

    if eleccion == "anular_compra":
        oc = rnd.choice(oc_pendientes)
        st, res = como(usuario, "POST", f"/api/compras/{oc['id']}/anular")
        _sin_permiso_es_error(st, res, f"Anular orden {oc['id']}")
        return resultado("COMPRAS", oc["id"], f"Orden de compra {oc['id']} ANULADA antes de aprobarse", float(oc.get("total") or 0))

    if eleccion == "confirmar_recepcion":
        rec = rnd.choice(rec_pend)
        con_diferencia = rnd.random() < 0.25
        items = []
        for j, it in enumerate(rec["items"]):
            esperado = int(it["expectedQty"])
            if con_diferencia and j == 0 and esperado > 1:
                items.append({"productId": it["productId"], "receivedQty": esperado - 1, "reason": "Unidad dañada en el transporte"})
            else:
                items.append({"productId": it["productId"], "receivedQty": esperado, "reason": ""})
        st, res = como(usuario, "POST", f"/api/recepciones/{rec['id']}/confirmar", {"items": items})
        _sin_permiso_es_error(st, res, f"Confirmar recepción {rec['id']}")
        return resultado("RECEPCIONES", rec["id"], f"Ingreso a bodega de la recepción {rec['id']} (OC {rec.get('poId')})"
                         + (" con diferencia" if con_diferencia else ""))

    if eleccion == "despachar_entrega":
        ent = rnd.choice(ent_pend)
        items = [{"productId": it["productId"], "deliveredQty": int(it["expectedQty"]), "reason": ""} for it in ent["items"]]
        if ent.get("invoiceId"):
            # Algunos ERP (Cuenca) exigen la factura APROBADA antes de despachar: la aprueba el supervisor de ventas
            como("v_supervisor", "POST", f"/api/ventas/{ent['invoiceId']}/aprobar")
        st, res = como(usuario, "POST", f"/api/entregas/{ent['id']}/confirmar", {"items": items})
        _sin_permiso_es_error(st, res, f"Despachar entrega {ent['id']}")
        return resultado("ENTREGAS", ent["id"], f"Despacho de la entrega {ent['id']} (factura {ent.get('invoiceId')})")

    if eleccion == "nuevo_cliente":
        n = rnd.randint(1000, 9999)
        cedula = f"17{rnd.randint(10_000_000, 99_999_999)}"
        st, res = como(usuario, "POST", "/api/clientes", {
            "nombre": f"{PREFIJO_CLIENTE_AGENTE} {sede.title()} {n}", "ciRuc": cedula, "telefono": f"09{rnd.randint(10_000_000, 99_999_999)}",
            "email": f"cliente{n}@lacava.ec", "idCiudad": {"QUITO": "UIO", "CUENCA": "CUE"}.get(sede, "GYE"),
            "direccion": f"Av. Principal {n}", "cupoCredito": 500, "descuento": 0,
        })
        _sin_permiso_es_error(st, res, "Registrar cliente")
        return resultado("CLIENTES", res.get("id"), f"Cliente nuevo {res.get('id')} registrado ({PREFIJO_CLIENTE_AGENTE} {sede.title()} {n})")

    if eleccion == "editar_cliente":
        cli = rnd.choice(clientes_agente)
        nuevo_tel = f"09{rnd.randint(10_000_000, 99_999_999)}"
        # PUT con los datos que ya tenía (la API no cambia ciudad ni celular en una edición): solo cambia el teléfono
        st, res = como(usuario, "PUT", f"/api/clientes/{cli['id']}", {
            "nombre": cli["name"], "ciRuc": cli["ciRuc"], "telefono": nuevo_tel, "email": cli.get("email") or "",
            "direccion": cli.get("address") or "", "cupoCredito": cli.get("creditLimit") or 0, "descuento": cli.get("discountRate") or 0,
        })
        _sin_permiso_es_error(st, res, f"Editar cliente {cli['id']}")
        return resultado("CLIENTES", cli["id"], f"Cliente {cli['id']} editado: teléfono {cli.get('contact')} -> {nuevo_tel}")

    productos = lista("v_operador", "/api/productos")
    if eleccion == "nueva_compra":
        proveedores = lista("c_operador", "/api/proveedores")
        prov = rnd.choice(proveedores)
        items = [{"idProducto": p["id"], "cantidad": rnd.randint(6, 24), "costoUnitario": max(0.01, float(p.get("cost") or 5))}
                 for p in rnd.sample(productos, k=min(len(productos), rnd.randint(1, 3)))]
        st, oc = como(usuario, "POST", "/api/compras", {
            "idProveedor": prov["id"], "fechaEntrega": str(date.today() + timedelta(days=rnd.randint(1, 5))), "tasaIVA": 15, "items": items,
        })
        _sin_permiso_es_error(st, oc, "Crear orden de compra")
        total = round(sum(i["cantidad"] * i["costoUnitario"] for i in items) * 1.15, 2)
        return resultado("COMPRAS", oc.get("id"), f"Orden de compra {oc.get('id')} a {prov.get('name', prov['id'])} creada: "
                                                  f"espera aprobación del supervisor", total)

    # nueva_venta
    con_stock = [p for p in productos if float(p.get("stock") or 0) >= 5] or productos
    items = [{"idProducto": p["id"], "cantidad": rnd.randint(1, 3), "precioUnitario": float(p.get("price") or 10)}
             for p in rnd.sample(con_stock, k=min(len(con_stock), rnd.randint(1, 3)))]
    cli = rnd.choice(clientes)
    st, venta = como(usuario, "POST", "/api/ventas", {
        "idCliente": cli["id"], "descripcion": f"Venta POS registrada por el agente de {sede.title()}", "tasaIVA": 15,
        "metodoPago": rnd.choice(["CASH", "CARD", "TRANSFER"]), "items": items,
    })
    _sin_permiso_es_error(st, venta, "Venta POS")
    return resultado("ENTREGAS", venta.get("deliveryId"), f"Venta POS {venta.get('id')} a {cli.get('name', cli['id'])}: "
                                                          f"entrega {venta.get('deliveryId')} pendiente de despacho",
                     float(venta.get("total") or 0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compras", type=int, default=6)
    ap.add_argument("--ventas", type=int, default=6)
    args = ap.parse_args()
    rnd = random.Random()

    _, proveedores = como("admin", "GET", "/api/proveedores")
    _, productos = como("admin", "GET", "/api/productos")
    _, clientes = como("admin", "GET", "/api/clientes")
    proveedores = [p for p in proveedores if str(p.get("status", p.get("estado", "ACT"))).upper() in ("ACT", "ACTIVE", "ACTIVO")] or proveedores
    print(f"Catálogo: {len(proveedores)} proveedores · {len(productos)} productos · {len(clientes)} clientes")

    def stock(p):
        for k in ("stock", "currentStock", "saldo", "stockActual"):
            if k in p and p[k] is not None:
                return float(p[k])
        return 0.0

    def precio(p, *claves):
        for k in claves:
            if p.get(k):
                return round(float(p[k]), 2)
        return 10.0

    # ---------------- COMPRAS -> RECEPCIONES ----------------
    recepciones_creadas = 0
    for i in range(args.compras):
        prov = rnd.choice(proveedores)
        items = []
        for p in rnd.sample(productos, k=min(len(productos), rnd.randint(2, 3))):
            costo = precio(p, "cost", "costo", "purchasePrice", "precioCompra", "price")
            items.append({"idProducto": p["id"], "cantidad": rnd.randint(6, 24), "costoUnitario": max(0.01, costo)})
        st, oc = como("c_operador", "POST", "/api/compras", {
            "idProveedor": prov["id"], "fechaEntrega": str(date.today() + timedelta(days=rnd.randint(1, 5))),
            "tasaIVA": 15, "items": items,
        })
        if st not in (200, 201):
            print(f"  [!] Orden de compra no creada: {st} {oc}")
            continue
        oc_id = oc.get("id") or oc.get("orderId")
        st, ap_res = como("c_supervisor", "POST", f"/api/compras/{oc_id}/aprobar")
        print(f"  OC {oc_id} ({prov.get('name', prov['id'])}): creada por c_operador · aprobación {st} -> {ap_res.get('mensaje') if isinstance(ap_res, dict) else ap_res}")
        recepciones_creadas += 1 if st == 200 else 0

    # Confirmar ingreso a bodega de la mitad de las recepciones pendientes
    _, recepciones = como("admin", "GET", "/api/recepciones")
    pendientes = [r for r in recepciones if str(r.get("status")).upper() == "PEN"]
    for n, rec in enumerate(pendientes[: max(1, len(pendientes) // 2)]):
        items = []
        for j, it in enumerate(rec["items"]):
            esperado = int(it["expectedQty"])
            if n == 0 and j == 0 and esperado > 1:  # una con diferencia, para ver el motivo
                items.append({"productId": it["productId"], "receivedQty": esperado - 1, "reason": "Botella rota en el transporte"})
            else:
                items.append({"productId": it["productId"], "receivedQty": esperado, "reason": ""})
        st, res = como("i_operador", "POST", f"/api/recepciones/{rec['id']}/confirmar", {"items": items})
        print(f"  Recepción {rec['id']} confirmada por bodega: {st} {res.get('mensaje') if isinstance(res, dict) else res}")

    # ---------------- VENTAS POS -> ENTREGAS ----------------
    con_stock = [p for p in productos if stock(p) >= 5] or productos
    for i in range(args.ventas):
        cli = rnd.choice(clientes)
        items = []
        for p in rnd.sample(con_stock, k=min(len(con_stock), rnd.randint(1, 3))):
            items.append({"idProducto": p["id"], "cantidad": rnd.randint(1, 3),
                          "precioUnitario": precio(p, "price", "precio", "salePrice", "precioVenta")})
        st, venta = como("v_operador", "POST", "/api/ventas", {
            "idCliente": cli["id"], "descripcion": "Venta POS (generada para demo)", "tasaIVA": 15,
            "metodoPago": rnd.choice(["CASH", "CARD", "TRANSFER"]), "items": items,
        })
        if st not in (200, 201):
            print(f"  [!] Venta no registrada: {st} {venta}")
            continue
        print(f"  Venta {venta.get('id')} -> entrega {venta.get('deliveryId')} (cliente {cli.get('name', cli['id'])})")

    _, entregas = como("admin", "GET", "/api/entregas")
    pendientes = [e for e in entregas if str(e.get("status")).upper() == "PEN"]
    for ent in pendientes[: max(1, len(pendientes) // 2)]:
        items = [{"productId": it["productId"], "deliveredQty": int(it["expectedQty"]), "reason": ""} for it in ent["items"]]
        st, res = como("i_operador", "POST", f"/api/entregas/{ent['id']}/confirmar", {"items": items})
        print(f"  Entrega {ent['id']} confirmada: {st} {res.get('mensaje') if isinstance(res, dict) else res}")

    _, recepciones = como("admin", "GET", "/api/recepciones")
    _, entregas = como("admin", "GET", "/api/entregas")
    resumen = lambda docs: {s: sum(1 for d in docs if d.get("status") == s) for s in sorted({d.get("status") for d in docs})}
    print(f"\nRECEPCIONES: {len(recepciones)} {resumen(recepciones)}")
    print(f"ENTREGAS:    {len(entregas)} {resumen(entregas)}")


if __name__ == "__main__":
    main()
