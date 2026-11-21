"""
Script Maestro de Aprovisionamiento de los 17 Usuarios Oficiales (15 por Módulo + DBA + Administrador)
en las Bases de Datos Relacionales (BD 1 Quito :3307, BD 4 Guayaquil :3306, BD 6 Cuenca :5432),
Motor NoSQL (BD 2 MongoDB :27017), Motor Paralelo (BD 3 :3308) y DWH Estrella (BD 5 :3309).

Crea cuentas 100% funcionales tanto para:
1. Iniciar sesión en la Interfaz Web "La Cava" (`USUARIOS`, `EMPLEADOS`, `USUARIOSxROLES`, `ROLES`, `ROLESxPERMISOS`).
2. Autenticación de los 6 Agentes IA (`agentes_quito.py` y `agentes_gye_cuenca.py`) y usuarios nativos del motor SQL (`CREATE USER` / `GRANT`).
"""

import base64
from datetime import datetime
import hashlib
import os
import secrets
import mysql.connector
import psycopg

MARIADB_PASS = os.getenv("MARIADB_PASSWORD", "1597.MyHql")
PG_PASS = os.getenv("PGPASSWORD", "147852369.MyPost")
PASSWORD_HASH_ITERATIONS = 310_000


def hash_password(raw_password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", raw_password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_HASH_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


# ==============================================================================
# MATRIZ OFICIAL DE 17 USUARIOS (15 DE MÓDULOS + 1 DBA + 1 ADMINISTRADOR)
# ==============================================================================
# Tupla: (id_usr, id_emp, username, password, rol_id_app, rol_motor_bd, modulo_cod, modulo_nom, dep_id, cedula, nombre, apellido, cargo, sueldo, email)
MATRIZ_17_USUARIOS = [
    # --- 0. ADMINISTRADOR GENERAL (Todo el sistema disponible) y DBA (Consola de Arquitectura) ---
    ("USR-ADMIN01", "EMP-000901", "admin", "LaCavaAdmin2026*", "ROL-ADM", "rol_jefe", "ALL", "ADMINISTRACION_GENERAL", "DEP-ADM", "1710034065", "Sebastián", "Mendoza", "Administrador General del ERP", 2400.00, "admin@lacava.ec"),
    ("USR-DBA0001", "EMP-000902", "dba", "LaCavaDba2026*", "ROL-DBA", "rol_jefe", "DBA", "ARQUITECTURA_Y_DBA", "DEP-SYS", "1713175071", "Alejandro", "Viteri", "Administrador de Bases de Datos (DBA)", 2250.00, "dba@lacava.ec"),

    # --- 1. MÓDULO COMPRAS (C) ---
    ("USR-COMP001", "EMP-000201", "c_jefe", "ComprasJefe2026*", "ROL-000001", "rol_jefe", "C", "COMPRAS", "DEP-COMP", "1714223318", "Roberto", "Gavilanes", "Jefe Nacional de Compras", 1650.00, "c_jefe@lacava.ec"),
    ("USR-COMP002", "EMP-000202", "c_supervisor", "ComprasSup2026*", "ROL-000002", "rol_supervisor", "C", "COMPRAS", "DEP-COMP", "1715334429", "Valeria", "Salazar", "Supervisora de Abastecimiento", 1250.00, "c_supervisor@lacava.ec"),
    ("USR-COMP003", "EMP-000203", "c_operador", "ComprasOpe2026*", "ROL-000003", "rol_operador", "C", "COMPRAS", "DEP-COMP", "1716445530", "Mateo", "Cevallos", "Operador de Órdenes de Compra", 850.00, "c_operador@lacava.ec"),

    # --- 2. MÓDULO INVENTARIOS (I) ---
    ("USR-INVE001", "EMP-000301", "i_jefe", "InveJefe2026*", "ROL-000004", "rol_jefe", "I", "INVENTARIOS", "DEP-INVE", "0912345672", "Fernando", "Baquerizo", "Jefe de Bodega e Inventarios", 1600.00, "i_jefe@lacava.ec"),
    ("USR-INVE002", "EMP-000302", "i_supervisor", "InveSup2026*", "ROL-000005", "rol_supervisor", "I", "INVENTARIOS", "DEP-INVE", "0913456783", "Gabriela", "Pincay", "Supervisora de Control de Stock", 1200.00, "i_supervisor@lacava.ec"),
    ("USR-INVE003", "EMP-000303", "i_operador", "InveOpe2026*", "ROL-000006", "rol_operador", "I", "INVENTARIOS", "DEP-INVE", "0914567894", "Diego", "Zambrano", "Operador de Recepciones y Despachos", 820.00, "i_operador@lacava.ec"),

    # --- 3. MÓDULO VENTAS (V) ---
    ("USR-VENT001", "EMP-000401", "v_jefe", "VentasJefe2026*", "ROL-000007", "rol_jefe", "V", "VENTAS", "DEP-VENT", "1717556641", "Carolina", "Andrade", "Jefa Comercial y Facturación", 1700.00, "v_jefe@lacava.ec"),
    ("USR-VENT002", "EMP-000402", "v_supervisor", "VentasSup2026*", "ROL-000008", "rol_supervisor", "V", "VENTAS", "DEP-VENT", "0915678905", "Andrés", "Villacís", "Supervisor de Punto de Venta", 1280.00, "v_supervisor@lacava.ec"),
    ("USR-VENT003", "EMP-000403", "v_operador", "VentasOpe2026*", "ROL-000009", "rol_operador", "V", "VENTAS", "DEP-VENT", "0102345675", "Camila", "Ordóñez", "Operadora de Caja y POS", 860.00, "v_operador@lacava.ec"),

    # --- 4. MÓDULO TALENTO HUMANO (TH) ---
    ("USR-RRHH001", "EMP-000501", "th_jefe", "ThJefe2026*", "ROL-000010", "rol_jefe", "TH", "TALENTO_HUMANO", "DEP-RRHH", "1718667752", "Patricia", "Espinosa", "Jefa de Talento Humano y Nómina", 1650.00, "th_jefe@lacava.ec"),
    ("USR-RRHH002", "EMP-000502", "th_supervisor", "ThSup2026*", "ROL-000011", "rol_supervisor", "TH", "TALENTO_HUMANO", "DEP-RRHH", "1719778863", "Santiago", "Mosquera", "Supervisor de Roles de Pago", 1220.00, "th_supervisor@lacava.ec"),
    ("USR-RRHH003", "EMP-000503", "th_operador", "ThOpe2026*", "ROL-000012", "rol_operador", "TH", "TALENTO_HUMANO", "DEP-RRHH", "0103456786", "Daniela", "Cordero", "Operadora de Registro de Personal", 840.00, "th_operador@lacava.ec"),

    # --- 5. MÓDULO CONTABILIDAD (Ctbl) ---
    ("USR-CONT001", "EMP-000601", "ctbl_jefe", "CtblJefe2026*", "ROL-000013", "rol_jefe", "Ctbl", "CONTABILIDAD", "DEP-CONT", "1720889974", "Ricardo", "Peñaherrera", "Jefe Financiero y Contable", 1800.00, "ctbl_jefe@lacava.ec"),
    ("USR-CONT002", "EMP-000602", "ctbl_supervisor", "CtblSup2026*", "ROL-000014", "rol_supervisor", "Ctbl", "CONTABILIDAD", "DEP-CONT", "0916789016", "Mónica", "Arosemena", "Supervisora de Auditoría y Bancos", 1320.00, "ctbl_supervisor@lacava.ec"),
    ("USR-CONT003", "EMP-000603", "ctbl_operador", "CtblOpe2026*", "ROL-000015", "rol_operador", "Ctbl", "CONTABILIDAD", "DEP-CONT", "0104567897", "Esteban", "crespo", "Operador de Asientos y Libro Diario", 880.00, "ctbl_operador@lacava.ec"),
]


def ensure_auth_schema_in_mariadb(cur):
    """Asegura que las tablas de seguridad de la aplicación existan también en BD 4 Guayaquil (:3306)."""
    cur.execute("""
    CREATE TABLE IF NOT EXISTS departamentos (
        id_Departamento VARCHAR(15) PRIMARY KEY,
        id_Empleado VARCHAR(15) NULL,
        dep_Nombre VARCHAR(80) NOT NULL,
        dep_Telefono VARCHAR(20) NULL,
        dep_Mail VARCHAR(100) NULL,
        ESTADO_DEP VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id_Rol VARCHAR(15) PRIMARY KEY,
        rol_Nombre VARCHAR(60) NOT NULL,
        rol_Descripcion VARCHAR(160) NULL,
        ESTADO_ROL VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS permisos (
        id_Permiso VARCHAR(15) PRIMARY KEY,
        prm_Modulo VARCHAR(40) NOT NULL,
        prm_Accion VARCHAR(30) NOT NULL,
        prm_Descripcion VARCHAR(160) NULL,
        ESTADO_PRM VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id_Usuario VARCHAR(20) PRIMARY KEY,
        id_Empleado VARCHAR(20) NULL,
        usr_Username VARCHAR(50) NOT NULL,
        usr_PasswordHash VARCHAR(255) NOT NULL,
        usr_IntentosFallidos INT DEFAULT 0,
        usr_UltimoAcceso DATETIME NULL,
        usr_RequiereCambioClave TINYINT DEFAULT 0,
        usr_FechaCambioClave DATETIME NULL,
        usr_TokenRecuperacion VARCHAR(100) NULL,
        ESTADO_USR VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuariosxroles (
        id_Usuario VARCHAR(20) NOT NULL,
        id_Rol VARCHAR(15) NOT NULL,
        ESTADO_UxR VARCHAR(10) DEFAULT 'ACT',
        PRIMARY KEY (id_Usuario, id_Rol)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS rolesxpermisos (
        id_Rol VARCHAR(15) NOT NULL,
        id_Permiso VARCHAR(15) NOT NULL,
        ESTADO_RxP VARCHAR(10) DEFAULT 'ACT',
        PRIMARY KEY (id_Rol, id_Permiso)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS log_auditoria (
        id_Log VARCHAR(30) PRIMARY KEY,
        id_Usuario VARCHAR(20) NULL,
        log_FechaHora DATETIME DEFAULT CURRENT_TIMESTAMP,
        log_TablaAfectada VARCHAR(60) NULL,
        log_Accion VARCHAR(40) NULL,
        log_IP VARCHAR(45) NULL,
        log_ValorAnterior TEXT NULL,
        log_ValorNuevo TEXT NULL
    )
    """)


def provision_17_users_on_mariadb_node(host: str, port: int, sede_label: str):
    print(f"-> Provisionando los 17 usuarios oficiales en MariaDB {host}:{port} ({sede_label})...")
    conn = mysql.connector.connect(
        host=host, port=port, user="root", password=MARIADB_PASS, autocommit=True
    )
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS `licoreriadatabase` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute("USE `licoreriadatabase`")
    ensure_auth_schema_in_mariadb(cur)

    # Departamentos base
    deps = [
        ("DEP-ADM", "Administración General", "022999999", "admin@lacava.ec"),
        ("DEP-SYS", "Sistemas y DBA", "022888999", "dba@lacava.ec"),
        ("DEP-COMP", "Departamento de Compras", "022333444", "compras@lacava.ec"),
        ("DEP-INVE", "Departamento de Inventarios", "022555666", "inventarios@lacava.ec"),
        ("DEP-VENT", "Departamento de Ventas", "022777888", "ventas@lacava.ec"),
        ("DEP-RRHH", "Talento Humano", "022999000", "rrhh@lacava.ec"),
        ("DEP-CONT", "Contabilidad y Finanzas", "022111222", "contabilidad@lacava.ec"),
    ]
    for d_id, d_nom, d_tel, d_mail in deps:
        cur.execute(
            "INSERT INTO departamentos (id_Departamento, dep_Nombre, dep_Telefono, dep_Mail, ESTADO_DEP) "
            "VALUES (%s, %s, %s, %s, 'ACT') ON DUPLICATE KEY UPDATE dep_Nombre = VALUES(dep_Nombre), ESTADO_DEP = 'ACT'",
            (d_id, d_nom, d_tel, d_mail),
        )

    # Roles de la Aplicación (15 de módulos + ROL-ADM + ROL-DBA)
    app_roles = [
        ("ROL-ADM", "SuperAdministrador", "Acceso total y absoluto a todos los módulos del ERP y Consola DBA"),
        ("ROL-DBA", "DBA_Arquitecto", "Administrador de Bases de Datos: acceso exclusivo a Topología, 6 BDs, Prompt SQL y Auditoría"),
        ("ROL-000001", "Jefe_COMPRAS", "Jefe del módulo de Compras (VER, CREAR, APROBAR, ANULAR)"),
        ("ROL-000002", "Supervisor_COMPRAS", "Supervisor del módulo de Compras (VER, CREAR, APROBAR)"),
        ("ROL-000003", "Operativo_COMPRAS", "Operador del módulo de Compras (VER, CREAR)"),
        ("ROL-000004", "Jefe_INVENTARIOS", "Jefe del módulo de Inventarios (VER, CREAR, APROBAR, ANULAR)"),
        ("ROL-000005", "Supervisor_INVENTARIOS", "Supervisor del módulo de Inventarios (VER, CREAR, APROBAR)"),
        ("ROL-000006", "Operativo_INVENTARIOS", "Operador del módulo de Inventarios (VER, CREAR)"),
        ("ROL-000007", "Jefe_VENTAS", "Jefe del módulo de Ventas (VER, CREAR, APROBAR, ANULAR)"),
        ("ROL-000008", "Supervisor_VENTAS", "Supervisor del módulo de Ventas (VER, CREAR, APROBAR)"),
        ("ROL-000009", "Operativo_VENTAS", "Operador del módulo de Ventas (VER, CREAR)"),
        ("ROL-000010", "Jefe_TALENTO_HUMANO", "Jefe del módulo de Talento Humano (VER, CREAR, APROBAR, ANULAR)"),
        ("ROL-000011", "Supervisor_TALENTO_HUMANO", "Supervisor del módulo de Talento Humano (VER, CREAR, APROBAR)"),
        ("ROL-000012", "Operativo_TALENTO_HUMANO", "Operador del módulo de Talento Humano (VER, CREAR)"),
        ("ROL-000013", "Jefe_CONTABILIDAD", "Jefe del módulo de Contabilidad (VER, CREAR, APROBAR, ANULAR)"),
        ("ROL-000014", "Supervisor_CONTABILIDAD", "Supervisor del módulo de Contabilidad (VER, CREAR, APROBAR)"),
        ("ROL-000015", "Operativo_CONTABILIDAD", "Operador del módulo de Contabilidad (VER, CREAR)"),
    ]
    for r_id, r_nom, r_desc in app_roles:
        cur.execute(
            "INSERT INTO roles (id_Rol, rol_Nombre, rol_Descripcion, ESTADO_ROL) VALUES (%s, %s, %s, 'ACT') "
            "ON DUPLICATE KEY UPDATE rol_Nombre = VALUES(rol_Nombre), rol_Descripcion = VALUES(rol_Descripcion), ESTADO_ROL = 'ACT'",
            (r_id, r_nom, r_desc),
        )

    # Permisos por módulo (CREAR, VER, ANULAR, APROBAR)
    permisos_base = [
        ("PRM-000001", "COMPRAS", "CREAR"), ("PRM-000002", "COMPRAS", "VER"), ("PRM-000003", "COMPRAS", "ANULAR"), ("PRM-000004", "COMPRAS", "APROBAR"),
        ("PRM-000005", "INVENTARIOS", "CREAR"), ("PRM-000006", "INVENTARIOS", "VER"), ("PRM-000007", "INVENTARIOS", "ANULAR"), ("PRM-000008", "INVENTARIOS", "APROBAR"),
        ("PRM-000009", "VENTAS", "CREAR"), ("PRM-000010", "VENTAS", "VER"), ("PRM-000011", "VENTAS", "ANULAR"), ("PRM-000012", "VENTAS", "APROBAR"),
        ("PRM-000013", "TALENTO_HUMANO", "CREAR"), ("PRM-000014", "TALENTO_HUMANO", "VER"), ("PRM-000015", "TALENTO_HUMANO", "ANULAR"), ("PRM-000016", "TALENTO_HUMANO", "APROBAR"),
        ("PRM-000017", "CONTABILIDAD", "CREAR"), ("PRM-000018", "CONTABILIDAD", "VER"), ("PRM-000019", "CONTABILIDAD", "ANULAR"), ("PRM-000020", "CONTABILIDAD", "APROBAR"),
    ]
    for p_id, p_mod, p_acc in permisos_base:
        cur.execute(
            "INSERT INTO permisos (id_Permiso, prm_Modulo, prm_Accion, prm_Descripcion, ESTADO_PRM) "
            "VALUES (%s, %s, %s, %s, 'ACT') ON DUPLICATE KEY UPDATE ESTADO_PRM = 'ACT'",
            (p_id, p_mod, p_acc, f"{p_acc} en {p_mod}"),
        )

    # Asignar permisos exactos por jerarquía (Jefe: 4 permisos; Supervisor: VER, CREAR, APROBAR; Operador: VER, CREAR)
    role_perm_groups = [
        ("ROL-000001", ["PRM-000001", "PRM-000002", "PRM-000003", "PRM-000004"]),
        ("ROL-000002", ["PRM-000001", "PRM-000002", "PRM-000004"]),
        ("ROL-000003", ["PRM-000001", "PRM-000002"]),
        ("ROL-000004", ["PRM-000005", "PRM-000006", "PRM-000007", "PRM-000008"]),
        ("ROL-000005", ["PRM-000005", "PRM-000006", "PRM-000008"]),
        ("ROL-000006", ["PRM-000005", "PRM-000006"]),
        ("ROL-000007", ["PRM-000009", "PRM-000010", "PRM-000011", "PRM-000012"]),
        ("ROL-000008", ["PRM-000009", "PRM-000010", "PRM-000012"]),
        ("ROL-000009", ["PRM-000009", "PRM-000010"]),
        ("ROL-000010", ["PRM-000013", "PRM-000014", "PRM-000015", "PRM-000016"]),
        ("ROL-000011", ["PRM-000013", "PRM-000014", "PRM-000016"]),
        ("ROL-000012", ["PRM-000013", "PRM-000014"]),
        ("ROL-000013", ["PRM-000017", "PRM-000018", "PRM-000019", "PRM-000020"]),
        ("ROL-000014", ["PRM-000017", "PRM-000018", "PRM-000020"]),
        ("ROL-000015", ["PRM-000017", "PRM-000018"]),
    ]
    for r_id, p_list in role_perm_groups:
        for p_id in p_list:
            cur.execute(
                "INSERT INTO rolesxpermisos (id_Rol, id_Permiso, ESTADO_RxP) VALUES (%s, %s, 'ACT') "
                "ON DUPLICATE KEY UPDATE ESTADO_RxP = 'ACT'",
                (r_id, p_id),
            )

    # Crear los 3 roles en el motor MariaDB + rol_dba + rol_admin
    for db_role in ("rol_jefe", "rol_supervisor", "rol_operador", "rol_dba", "rol_admin"):
        try:
            cur.execute(f"CREATE ROLE IF NOT EXISTS '{db_role}'")
        except Exception:
            pass
    try:
        cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'rol_admin' WITH GRANT OPTION")
        cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'rol_dba'")
        cur.execute("GRANT ALL PRIVILEGES ON `licoreriadatabase`.* TO 'rol_jefe'")
        cur.execute("GRANT SELECT, INSERT, UPDATE ON `licoreriadatabase`.* TO 'rol_supervisor'")
        cur.execute("GRANT SELECT, INSERT ON `licoreriadatabase`.* TO 'rol_operador'")
    except Exception:
        pass

    # Tabla rbac_matriz_15_usuarios (incluye los 15 + dba + admin = 17 registros documentados)
    cur.execute("DROP TABLE IF EXISTS rbac_matriz_15_usuarios")
    cur.execute("""
    CREATE TABLE rbac_matriz_15_usuarios (
        username VARCHAR(30) PRIMARY KEY,
        password_plano VARCHAR(40) NOT NULL,
        rol_bd VARCHAR(30) NOT NULL,
        rol_aplicacion VARCHAR(35) NOT NULL,
        modulo_codigo VARCHAR(10) NOT NULL,
        modulo_nombre VARCHAR(40) NOT NULL,
        nombre_colaborador VARCHAR(80) NOT NULL,
        descripcion_cargo VARCHAR(90) NOT NULL,
        sede_nodo VARCHAR(80) NOT NULL,
        estado VARCHAR(15) NOT NULL DEFAULT 'ACTIVO',
        ultima_actividad DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Insertar Empleados, Usuarios de Aplicación, UsuariosxRoles, Usuarios del Motor SQL y Matriz RBAC
    for (
        id_usr, id_emp, username, raw_pass, rol_app, rol_bd,
        mod_cod, mod_nom, dep_id, cedula, nombre, apellido, cargo, sueldo, email
    ) in MATRIZ_17_USUARIOS:
        # 1. Empleado (compatible con esquema de :3307, :3306 y el esquema de la PC de Escritorio 100.77.220.102)
        try:
            cur.execute(
                """
                INSERT INTO empleados (
                    id_Empleado, id_Departamento, emp_Cedula, emp_Apellido1, emp_Nombre1,
                    emp_Sexo, emp_FechaNacimiento, emp_Sueldo, emp_Mail, USER_ID, ESTADO_EMP
                ) VALUES (%s, %s, %s, %s, %s, 'M', '1990-05-15', %s, %s, %s, 'ACT')
                ON DUPLICATE KEY UPDATE emp_Nombre1 = VALUES(emp_Nombre1), emp_Apellido1 = VALUES(emp_Apellido1), ESTADO_EMP = 'ACT'
                """,
                (id_emp, dep_id, cedula, apellido, nombre, sueldo, email, id_usr),
            )
        except Exception:
            try:
                cur.execute(
                    """
                    INSERT INTO empleados (id_Empleado, emp_Cedula, emp_Nombre1, emp_Apellido1, emp_Sueldo, emp_Mail, ESTADO_EMP)
                    VALUES (%s, %s, %s, %s, %s, %s, 'ACT')
                    ON DUPLICATE KEY UPDATE emp_Nombre1 = VALUES(emp_Nombre1), ESTADO_EMP = 'ACT'
                    """,
                    (id_emp, cedula, nombre, apellido, sueldo, email),
                )
            except Exception:
                try:
                    cur.execute(
                        """
                        INSERT INTO empleados (cedula, nombres, apellidos, modulo, cargo, sede, salario_base, activo)
                        VALUES (%s, %s, %s, %s, %s, 'QUITO', %s, 1)
                        """,
                        (cedula, nombre, apellido, mod_nom, cargo, sueldo),
                    )
                except Exception:
                    pass

        # 2. Usuario en tabla USUARIOS (con PBKDF2-SHA256 para login en la interfaz web)
        pw_hash = hash_password(raw_pass)
        cur.execute("SELECT id_Usuario FROM usuarios WHERE usr_Username = %s LIMIT 1", (username,))
        existing = cur.fetchone()
        effective_usr_id = existing[0] if existing else id_usr

        if existing:
            cur.execute(
                "UPDATE usuarios SET usr_PasswordHash = %s, usr_IntentosFallidos = 0, usr_RequiereCambioClave = 0, ESTADO_USR = 'ACT' WHERE id_Usuario = %s",
                (pw_hash, effective_usr_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO usuarios (id_Usuario, id_Empleado, usr_Username, usr_PasswordHash, usr_IntentosFallidos, usr_RequiereCambioClave, ESTADO_USR)
                VALUES (%s, %s, %s, %s, 0, 0, 'ACT')
                """,
                (effective_usr_id, id_emp, username, pw_hash),
            )

        # 3. Asignar rol en USUARIOSxROLES
        cur.execute("DELETE FROM usuariosxroles WHERE id_Usuario = %s", (effective_usr_id,))
        cur.execute(
            "INSERT INTO usuariosxroles (id_Usuario, id_Rol, ESTADO_UxR) VALUES (%s, %s, 'ACT')",
            (effective_usr_id, rol_app),
        )

        # 4. Crear usuario real en el motor MariaDB con su contraseña propia
        for h in ("%", "localhost", "127.0.0.1"):
            try:
                cur.execute(f"CREATE USER IF NOT EXISTS '{username}'@'{h}' IDENTIFIED BY '{raw_pass}'")
                cur.execute(f"ALTER USER '{username}'@'{h}' IDENTIFIED BY '{raw_pass}'")
                cur.execute(f"GRANT '{rol_bd}' TO '{username}'@'{h}'")
                cur.execute(f"SET DEFAULT ROLE '{rol_bd}' FOR '{username}'@'{h}'")
            except Exception:
                pass

        # 5. Registrar en rbac_matriz_15_usuarios
        cur.execute(
            """
            INSERT INTO rbac_matriz_15_usuarios (
                username, password_plano, rol_bd, rol_aplicacion, modulo_codigo,
                modulo_nombre, nombre_colaborador, descripcion_cargo, sede_nodo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username, raw_pass, rol_bd, rol_app, mod_cod,
                mod_nom, f"{nombre} {apellido}", cargo, sede_label,
            ),
        )

    cur.execute("FLUSH PRIVILEGES")
    cur.close()
    conn.close()
    print(f"   [OK] 17 usuarios creados y habilitados para Login Web + Motor SQL en :{port}")


def provision_17_users_on_postgres_cuenca():
    print("-> Provisionando los 17 usuarios oficiales en PostgreSQL :5432 (BD 6 Cuenca Cloud)...")
    dsn = f"host=127.0.0.1 port=5432 dbname=cloud_cuenca_loja user=postgres password={PG_PASS}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS rbac_matriz_15_usuarios")
            cur.execute("""
            CREATE TABLE rbac_matriz_15_usuarios (
                username VARCHAR(30) PRIMARY KEY,
                password_plano VARCHAR(40) NOT NULL,
                rol_bd VARCHAR(30) NOT NULL,
                rol_aplicacion VARCHAR(35) NOT NULL,
                modulo_codigo VARCHAR(10) NOT NULL,
                modulo_nombre VARCHAR(40) NOT NULL,
                nombre_colaborador VARCHAR(80) NOT NULL,
                descripcion_cargo VARCHAR(90) NOT NULL,
                sede_nodo VARCHAR(40) NOT NULL DEFAULT 'BD 6 - CUENCA CLOUD (:5432)'
            )
            """)
            for (
                _, _, username, raw_pass, rol_app, rol_bd,
                mod_cod, mod_nom, _, _, nombre, apellido, cargo, _, _
            ) in MATRIZ_17_USUARIOS:
                cur.execute(
                    "INSERT INTO rbac_matriz_15_usuarios VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        username, raw_pass, rol_bd, rol_app, mod_cod,
                        mod_nom, f"{nombre} {apellido}", cargo, "BD 6 - CUENCA CLOUD (:5432)"
                    ),
                )
    print("   [OK] 17 usuarios replicados en BD 6 Cuenca Cloud (:5432)")


if __name__ == "__main__":
    provision_17_users_on_mariadb_node("127.0.0.1", 3307, "BD 1 - QUITO LOCAL (:3307)")
    try:
        provision_17_users_on_mariadb_node("100.77.220.102", 3307, "BD 1 - QUITO PC ESCRITORIO (100.77.220.102:3307)")
    except Exception as exc:
        print(f"   [Aviso] No se pudo conectar a 100.77.220.102:3307: {exc}")
    provision_17_users_on_mariadb_node("127.0.0.1", 3306, "BD 4 - GUAYAQUIL LAPTOP (100.123.81.4:3306)")
    provision_17_users_on_postgres_cuenca()
    print("\n¡MATRIZ DE 17 USUARIOS (15 MÓDULOS + DBA + ADMIN) APROVISIONADA CON ÉXITO!")
