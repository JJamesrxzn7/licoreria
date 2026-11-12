"""Política cerrada para las rutas PostgreSQL; no habilita operaciones no migradas."""

import re

import postgres_auth

# La tabla se revisa explícitamente al agregar rutas: ninguna ruta desconocida
# adquiere permisos por el método HTTP o por un prefijo accidental.
ROUTES = (
    (r"/api/(?:catalogos/generales)", "ANY"),
    (r"/api/capabilities", "ANY"),
    (r"/api/(?:ciudades)", "ANY"),
    (r"/api/(?:unidades-medida|categorias|marcas)(?:/[^/]+)?", "COMPRAS"),
    (r"/api/(?:compras|productos|proveedores)(?:/[^/]+){0,2}", "COMPRAS"),
    (r"/api/(?:ventas|clientes)(?:/[^/]+){0,2}", "VENTAS"),
    (r"/api/(?:recepciones|entregas|ajustes)(?:/[^/]+){0,2}", "INVENTARIOS"),
    (r"/api/(?:departamentos|cargos|empleados|nomina)(?:/[^/]+){0,3}", "TALENTO_HUMANO"),
    (r"/api/contabilidad/(?:bancos|centros-costos|cuentas|asientos)(?:/[^/]+){0,2}", "CONTABILIDAD"),
    (r"/api/(?:usuarios|auditoria)(?:/[^/]+){0,3}", "ADMIN"),
)

SUPPORTED_ROUTES = (
    (r"/api/capabilities", {"GET"}),
    (r"/api/catalogos/generales", {"GET"}),
    (r"/api/unidades-medida", {"GET"}),
    (r"/api/compras/catalogos", {"GET"}),
    (r"/api/compras", {"GET", "POST"}),
    (r"/api/compras/[^/]+/(?:aprobar|anular)", {"POST"}),
    (r"/api/productos", {"GET"}),
    (r"/api/clientes", {"GET"}),
    (r"/api/proveedores", {"GET"}),
    (r"/api/ventas", {"GET", "POST"}),
    (r"/api/ventas/[^/]+/(?:aprobar|anular)", {"POST"}),
    (r"/api/recepciones", {"GET"}),
    (r"/api/recepciones/[^/]+/confirmar", {"POST"}),
    (r"/api/entregas", {"GET"}),
    (r"/api/entregas/[^/]+/confirmar", {"POST"}),
    (r"/api/ajustes", {"GET", "POST"}),
    (r"/api/ajustes/[^/]+/anular", {"POST"}),
    (r"/api/departamentos", {"GET"}),
    (r"/api/cargos", {"GET"}),
    (r"/api/empleados", {"GET", "POST"}),
    (r"/api/empleados/[^/]+/(?:cargos|cargas)", {"GET"}),
    (r"/api/nomina/(?:bonificaciones|descuentos)", {"GET", "POST"}),
    (r"/api/nomina/(?:bonificaciones|descuentos)/[^/]+", {"PUT", "DELETE"}),
    (r"/api/nomina", {"GET", "POST"}),
    (r"/api/nomina/[^/]+/(?:aprobar|anular)", {"POST"}),
    (r"/api/contabilidad/bancos", {"GET", "POST"}),
    (r"/api/contabilidad/bancos/[^/]+", {"PUT"}),
    (r"/api/contabilidad/centros-costos", {"GET"}),
    (r"/api/contabilidad/cuentas", {"GET", "POST"}),
    (r"/api/contabilidad/asientos", {"GET", "POST"}),
    (r"/api/auditoria", {"GET"}),
    (r"/api/auth/logout", {"POST"}),
    (r"/api/auth/roles", {"GET"}),
    (r"/api/usuarios", {"GET"}),
    (r"/api/usuarios/empleados-disponibles", {"GET"}),
    (r"/api/usuarios/[^/]+/roles", {"GET"}),
)


def supported(path, method):
    return any(method in methods and re.fullmatch(pattern, path) for pattern, methods in SUPPORTED_ROUTES)


def requirement(path, method):
    if path == "/api/productos" and method == "GET":
        return "PRODUCT_READ", "VER"
    module = next((name for pattern, name in ROUTES if re.fullmatch(pattern, path)), None)
    if module is None:
        return None
    if method == "GET":
        action = "VER"
    elif method == "POST" and path.endswith(("/aprobar", "/confirmar")):
        action = "APROBAR"
    elif method == "POST" and path.endswith("/anular"):
        action = "ANULAR"
    elif method == "DELETE":
        action = "ANULAR"
    elif method in {"POST", "PUT", "PATCH"}:
        action = "CREAR"
    else:
        return None
    return module, action


def allowed(roles, requirement_value):
    if requirement_value is None:
        return False
    module, action = requirement_value
    if module == "ADMIN":
        return postgres_auth.is_admin(roles)
    permissions = postgres_auth.grants(roles)
    if module == "PRODUCT_READ":
        return action == "VER" and any(
            (module_name, "VER") in permissions
            for module_name in ("COMPRAS", "VENTAS", "INVENTARIOS", "CONTABILIDAD")
        )
    if module == "ANY":
        return action == "VER" and any(a == "VER" for _, a in permissions)
    return (module, action) in permissions
