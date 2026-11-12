"""Autenticación y matriz de roles para el backend PostgreSQL."""

from psycopg.rows import dict_row
from uuid import uuid4
import hashlib

from postgres_connection import connect_postgres

MODULES = frozenset({"COMPRAS", "INVENTARIOS", "VENTAS", "TALENTO_HUMANO", "CONTABILIDAD"})
ACTIONS = frozenset({"CREAR", "VER", "APROBAR", "ANULAR"})
ROLE_ACTION = {"operativo": "CREAR", "auxiliar": "APROBAR", "jefe": "ANULAR"}


def grants(roles):
    """Derivar permisos únicamente de roles activos conocidos; los roles se suman."""
    result = set()
    for role in roles:
        name = str(role["rol_nombre"] or "").strip()
        if name.casefold() == "administrador":
            result.update((module, action) for module in MODULES for action in ACTIONS)
            continue
        prefix, separator, module = name.partition("_")
        module = module.upper()
        action = ROLE_ACTION.get(prefix.casefold())
        if separator and module in MODULES and action:
            result.update({(module, "VER"), (module, action)})
    return result


def is_admin(roles):
    return any(str(role["rol_nombre"] or "").strip().casefold() == "administrador" for role in roles)


def _roles(cursor, user_id):
    cursor.execute(
        """SELECT TRIM(r.id_rol) AS id_rol, TRIM(r.rol_nombre) AS rol_nombre
           FROM usuariosxroles ur JOIN roles r ON r.id_rol = ur.id_rol
           WHERE ur.id_usuario = %s AND ur.estado_uxr = 'ACT'
             AND r.estado_rol = 'ACT' ORDER BY r.id_rol""",
        (user_id,),
    )
    return cursor.fetchall()


def active_roles(user_id):
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT 1 FROM usuarios WHERE id_usuario = %s AND estado_usr = 'ACT' "
                "AND COALESCE(usr_intentosfallidos, 0) < 5",
                (user_id,),
            )
            if not cursor.fetchone():
                return None
            return _roles(cursor, user_id)


def session_revoked(token):
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with connect_postgres() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM sesiones_revocadas WHERE token_hash = %s)", (digest,))
            return cursor.fetchone()[0]


def revoke_session(token, expires_at, user_id, client_ip):
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with connect_postgres() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sesiones_revocadas (token_hash, expira_en) VALUES (%s, to_timestamp(%s)) "
                "ON CONFLICT (token_hash) DO NOTHING",
                (digest, expires_at),
            )
            if cursor.rowcount:
                cursor.execute(
                    """INSERT INTO log_auditoria
                       (id_log, id_usuario, log_fechahora, log_tablaafectada, log_accion,
                        log_ip, log_valoranterior, log_valornuevo)
                       VALUES (%s, %s, NOW(), 'USUARIOS', 'LOGOUT', %s, NULL, %s)""",
                    (f"LOG-{uuid4().hex[:10].upper()}", user_id, client_ip,
                     "Cierre de sesión de usuario"),
                )


def is_initialized() -> bool:
    with connect_postgres() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM usuarios)")
            return bool(cursor.fetchone()[0])


def login(username, password, client_ip, verify_password):
    """Bloquear la fila para serializar intentos y confirmar fallos antes de responder."""
    error = None
    result = None
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT u.id_usuario, u.id_empleado, u.usr_username, u.usr_passwordhash,
                          u.usr_intentosfallidos, u.estado_usr, e.emp_nombre1,
                          e.emp_apellido1, d.dep_nombre
                   FROM usuarios u LEFT JOIN empleados e ON e.id_empleado = u.id_empleado
                   LEFT JOIN departamentos d ON d.id_departamento = e.id_departamento
                   WHERE u.usr_username = %s FOR UPDATE OF u""",
                (username,),
            )
            user = cursor.fetchone()
            if user:
                cursor.execute(
                    "SELECT set_config('app.auditoria_usuario', %s, true), "
                    "set_config('app.auditoria_ip', %s, true)",
                    (user["id_usuario"].strip(), client_ip),
                )
            if not user:
                error = (401, "Usuario o contraseña incorrectos.")
            elif user["estado_usr"] != "ACT":
                error = (403, "La cuenta no está activa.")
            elif (user["usr_intentosfallidos"] or 0) >= 5:
                error = (403, "La cuenta se encuentra bloqueada por intentos fallidos.")
            elif not verify_password(password, user["usr_passwordhash"] or ""):
                cursor.execute(
                    "UPDATE usuarios SET usr_intentosfallidos = COALESCE(usr_intentosfallidos, 0) + 1 "
                    "WHERE id_usuario = %s", (user["id_usuario"],)
                )
                error = (401, "Usuario o contraseña incorrectos.")
            else:
                user_id = user["id_usuario"].strip()
                cursor.execute(
                    "UPDATE usuarios SET usr_intentosfallidos = 0, usr_ultimoacceso = NOW() "
                    "WHERE id_usuario = %s", (user_id,)
                )
                roles = _roles(cursor, user_id)
                cursor.execute(
                    """SELECT DISTINCT TRIM(p.id_permiso) AS id_permiso,
                              TRIM(p.prm_modulo) AS prm_modulo, TRIM(p.prm_accion) AS prm_accion
                       FROM usuariosxroles ur JOIN roles r ON r.id_rol = ur.id_rol
                       JOIN rolesxpermisos rp ON rp.id_rol = r.id_rol
                       JOIN permisos p ON p.id_permiso = rp.id_permiso
                       WHERE ur.id_usuario = %s AND ur.estado_uxr = 'ACT'
                         AND r.estado_rol = 'ACT' AND rp.estado_rxp = 'ACT'
                         AND p.estado_prm = 'ACT'""", (user_id,)
                )
                permitted = grants(roles)
                permissions = [p for p in cursor.fetchall()
                               if (str(p["prm_modulo"]).strip().upper(),
                                   str(p["prm_accion"]).strip().upper()) in permitted]
                cursor.execute(
                    """INSERT INTO log_auditoria
                       (id_log, id_usuario, log_fechahora, log_tablaafectada, log_accion,
                        log_ip, log_valoranterior, log_valornuevo)
                       VALUES (%s, %s, NOW(), 'USUARIOS', 'LOGIN', %s, NULL, %s)""",
                    (f"LOG-{uuid4().hex[:10].upper()}", user_id, client_ip,
                     "Inicio de sesión exitoso"),
                )
                result = (user, roles, permissions)
    return result, error
