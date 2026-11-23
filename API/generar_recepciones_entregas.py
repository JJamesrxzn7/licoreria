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
import random
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:8000"
CREDENCIALES = {
    "admin": "LaCavaAdmin2026*",
    "c_operador": "ComprasOpe2026*",
    "c_supervisor": "ComprasSup2026*",
    "i_operador": "InveOpe2026*",
    "v_operador": "VentasOpe2026*",
}
_tokens: dict[str, str] = {}


def llamar(metodo: str, ruta: str, usuario: str | None = None, cuerpo: dict | None = None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo)
    req.add_header("Content-Type", "application/json")
    if usuario:
        req.add_header("Authorization", f"Bearer {token(usuario)}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read() or b"null")
        except ValueError:
            detalle = None
        return e.code, detalle


def token(usuario: str) -> str:
    if usuario not in _tokens:
        st, body = llamar("POST", "/api/auth/login", None, {"username": usuario, "password": CREDENCIALES[usuario]})
        if st != 200 or not body or not body.get("token"):
            raise SystemExit(f"No se pudo iniciar sesión como {usuario}: {st} {body}")
        _tokens[usuario] = body["token"]
    return _tokens[usuario]


def como(usuario: str, metodo: str, ruta: str, cuerpo: dict | None = None):
    """Ejecuta con el usuario del módulo; si no tiene permiso, reintenta con admin."""
    st, body = llamar(metodo, ruta, usuario, cuerpo)
    if st == 401:  # token vencido: nuevo inicio de sesión y un reintento
        _tokens.pop(usuario, None)
        st, body = llamar(metodo, ruta, usuario, cuerpo)
    if st == 403 and usuario != "admin":
        print(f"    (aviso: {usuario} no tiene permiso para {metodo} {ruta}; se usa admin)")
        st, body = llamar(metodo, ruta, "admin", cuerpo)
    return st, body


def accion_bodega(rnd: random.Random | None = None) -> dict:
    """
    UNA acción de bodega hecha con la app como un usuario más (la usa el Agente 4 cada cierto ciclo).
    Devuelve qué documento creó/confirmó: {usuario, modulo, tabla, id, accion, monto}.
    """
    rnd = rnd or random.Random()
    _, recepciones = como("admin", "GET", "/api/recepciones")
    _, entregas = como("admin", "GET", "/api/entregas")
    rec_pend = [r for r in recepciones or [] if str(r.get("status")).upper() == "PEN"]
    ent_pend = [e for e in entregas or [] if str(e.get("status")).upper() == "PEN"]
    opciones = ["nueva_compra", "nueva_venta"] + (["confirmar_recepcion"] * 2 if rec_pend else []) + (["despachar_entrega"] * 2 if ent_pend else [])
    eleccion = rnd.choice(opciones)

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
        st, res = como("i_operador", "POST", f"/api/recepciones/{rec['id']}/confirmar", {"items": items})
        if st != 200:
            raise RuntimeError(f"Confirmar recepción {rec['id']}: {st} {res}")
        return {"usuario": "i_operador", "modulo": "INVENTARIOS", "tabla": "RECEPCIONES", "id": rec["id"], "monto": 0.0,
                "accion": f"Ingreso a bodega de la recepción {rec['id']} (OC {rec.get('poId')})" + (" con diferencia" if con_diferencia else "")}

    if eleccion == "despachar_entrega":
        ent = rnd.choice(ent_pend)
        items = [{"productId": it["productId"], "deliveredQty": int(it["expectedQty"]), "reason": ""} for it in ent["items"]]
        st, res = como("i_operador", "POST", f"/api/entregas/{ent['id']}/confirmar", {"items": items})
        if st != 200:
            raise RuntimeError(f"Despachar entrega {ent['id']}: {st} {res}")
        return {"usuario": "i_operador", "modulo": "INVENTARIOS", "tabla": "ENTREGAS", "id": ent["id"], "monto": 0.0,
                "accion": f"Despacho de la entrega {ent['id']} (factura {ent.get('invoiceId')})"}

    _, productos = como("admin", "GET", "/api/productos")
    if eleccion == "nueva_compra":
        _, proveedores = como("admin", "GET", "/api/proveedores")
        prov = rnd.choice(proveedores)
        items = [{"idProducto": p["id"], "cantidad": rnd.randint(6, 24), "costoUnitario": max(0.01, float(p.get("cost") or 5))}
                 for p in rnd.sample(productos, k=min(len(productos), rnd.randint(1, 3)))]
        st, oc = como("c_operador", "POST", "/api/compras", {
            "idProveedor": prov["id"], "fechaEntrega": str(date.today() + timedelta(days=rnd.randint(1, 5))), "tasaIVA": 15, "items": items,
        })
        if st not in (200, 201):
            raise RuntimeError(f"Crear orden de compra: {st} {oc}")
        oc_id = oc.get("id")
        st, res = como("c_supervisor", "POST", f"/api/compras/{oc_id}/aprobar")
        if st != 200:
            raise RuntimeError(f"Aprobar {oc_id}: {st} {res}")
        _, recepciones = como("admin", "GET", "/api/recepciones")
        rec = next((r for r in recepciones if r.get("poId") == oc_id), None)
        total = round(sum(i["cantidad"] * i["costoUnitario"] for i in items) * 1.15, 2)
        return {"usuario": "c_operador", "modulo": "COMPRAS", "tabla": "RECEPCIONES", "id": rec["id"] if rec else oc_id, "monto": total,
                "accion": f"Orden de compra {oc_id} a {prov.get('name', prov['id'])} aprobada: recepción {rec['id'] if rec else '?'} pendiente en bodega"}

    # nueva_venta
    _, clientes = como("admin", "GET", "/api/clientes")
    con_stock = [p for p in productos if float(p.get("stock") or 0) >= 5] or productos
    items = [{"idProducto": p["id"], "cantidad": rnd.randint(1, 3), "precioUnitario": float(p.get("price") or 10)}
             for p in rnd.sample(con_stock, k=min(len(con_stock), rnd.randint(1, 3)))]
    cli = rnd.choice(clientes)
    st, venta = como("v_operador", "POST", "/api/ventas", {
        "idCliente": cli["id"], "descripcion": "Venta POS registrada por Agente 4", "tasaIVA": 15,
        "metodoPago": rnd.choice(["CASH", "CARD", "TRANSFER"]), "items": items,
    })
    if st not in (200, 201):
        raise RuntimeError(f"Venta POS: {st} {venta}")
    total = float(venta.get("total") or 0)
    return {"usuario": "v_operador", "modulo": "VENTAS", "tabla": "ENTREGAS", "id": venta.get("deliveryId"), "monto": total,
            "accion": f"Venta POS {venta.get('id')} a {cli.get('name', cli['id'])}: entrega {venta.get('deliveryId')} pendiente de despacho"}


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
