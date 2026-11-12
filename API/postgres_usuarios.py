"""Consultas administrativas PostgreSQL, sin exponer credenciales."""

from psycopg.rows import dict_row

from postgres_connection import connect_postgres


def listar_usuarios():
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT TRIM(u.id_usuario) AS "id_Usuario",
                       COALESCE(TRIM(u.id_empleado), '') AS "id_Empleado",
                       TRIM(u.usr_username) AS username, TRIM(u.estado_usr) AS "ESTADO_USR",
                       e.emp_nombre1 AS "emp_Nombre1", e.emp_apellido1 AS "emp_Apellido1",
                       d.dep_nombre AS "dep_Nombre",
                       ARRAY(SELECT TRIM(r.rol_nombre)
                             FROM usuariosxroles ur JOIN roles r ON r.id_rol = ur.id_rol
                             WHERE ur.id_usuario = u.id_usuario
                               AND ur.estado_uxr = 'ACT' AND r.estado_rol = 'ACT'
                             ORDER BY r.rol_nombre) AS roles
                FROM usuarios u
                LEFT JOIN empleados e ON e.id_empleado = u.id_empleado
                LEFT JOIN departamentos d ON d.id_departamento = e.id_departamento
                ORDER BY u.usr_username
            """)
            return cursor.fetchall()


def listar_roles():
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT TRIM(r.id_rol) AS id, TRIM(r.rol_nombre) AS nombre,
                       r.rol_descripcion AS descripcion, TRIM(r.estado_rol) AS estado,
                       COUNT(ur.id_usuario) AS "usuariosAsignados"
                FROM roles r
                LEFT JOIN usuariosxroles ur ON ur.id_rol = r.id_rol AND ur.estado_uxr = 'ACT'
                GROUP BY r.id_rol, r.rol_nombre, r.rol_descripcion, r.estado_rol
                ORDER BY r.id_rol
            """)
            return cursor.fetchall()


def roles_usuario(user_id):
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT TRIM(r.id_rol) AS id, TRIM(r.rol_nombre) AS nombre
                FROM usuariosxroles ur JOIN roles r ON r.id_rol = ur.id_rol
                WHERE ur.id_usuario = %s AND ur.estado_uxr = 'ACT' AND r.estado_rol = 'ACT'
                ORDER BY r.rol_nombre
            """, (user_id,))
            return cursor.fetchall()


def empleados_disponibles():
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT TRIM(e.id_empleado) AS id, e.emp_nombre1 AS nombre,
                       e.emp_apellido1 AS apellido, d.dep_nombre AS departamento
                FROM empleados e
                LEFT JOIN departamentos d ON d.id_departamento = e.id_departamento
                WHERE e.estado_emp = 'ACT'
                  AND NOT EXISTS (SELECT 1 FROM usuarios u WHERE u.id_empleado = e.id_empleado)
                ORDER BY e.emp_nombre1, e.emp_apellido1
            """)
            return cursor.fetchall()


def listar_auditoria():
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT TRIM(id_log) AS id, TRIM(id_usuario) AS usuario,
                       log_fechahora AS "fechaHora", TRIM(log_tablaafectada) AS tabla,
                       TRIM(log_accion) AS accion, log_valoranterior AS "valorAnterior",
                       log_valornuevo AS "valorNuevo"
                FROM log_auditoria ORDER BY log_fechahora DESC, id_log DESC LIMIT 100
            """)
            return cursor.fetchall()
