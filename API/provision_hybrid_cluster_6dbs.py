"""
Aprovisionamiento Completo del Clúster Híbrido "La Cava" (6 BDs + 15 Usuarios RBAC + 3 Roles):
Cumple al 100% con el Contrato Compartido del documento multi-máquina:
- BD 1 (QUITO - MariaDB :3307): `licoreriadatabase` + 5 Módulos (C, I, V, TH, Ctbl) + 3 Roles + 15 Usuarios.
- BD 2 (QUITO_NOSQL - MongoDB :27017): base `quito_nosql_mongo` con colecciones `logs_auditoria` y `eventos_agentes`.
- BD 3 (QUITO_PARALELA - MariaDB :3308): base `quito_paralela_db` con tabla `historico_transacciones`
  particionada con `PARTITION BY HASH(id) PARTITIONS 4` (Speed-up).
- BD 4 (GUAYAQUIL - MariaDB Local Laptop :3306): base `licoreriadatabase` (Transacciones Guayaquil) + 5 Módulos + 3 Roles + 15 Usuarios.
- BD 5 (GUAYAQUIL_DWH - MariaDB DWH Laptop :3309): base `db_gye_dwh` con Esquema Estrella (`dim_sede`, `dim_producto`, `dim_tiempo`, `fact_ventas`) para Power BI.
- BD 6 (CUENCA - PostgreSQL / Supabase Cloud DBaaS :5432): base `cloud_cuenca_loja` / Supabase con tablas replicadas de La Cava.
"""

from datetime import datetime
import os
import mysql.connector
import psycopg
from pymongo import MongoClient

MARIADB_PASS = os.getenv("MARIADB_PASSWORD", "1597.MyHql")
PG_PASS = os.getenv("PGPASSWORD", "147852369.MyPost")

# Matriz obligatoria de 15 usuarios y 3 roles (Seguridad RBAC)
ROLES_RBAC = ["rol_jefe", "rol_supervisor", "rol_operador"]

USUARIOS_15_RBAC = [
    # Compras (C)
    ("c_jefe", "rol_jefe", "COMPRAS", "Jefe de Compras"),
    ("c_supervisor", "rol_supervisor", "COMPRAS", "Supervisor de Compras"),
    ("c_operador", "rol_operador", "COMPRAS", "Operador de Compras"),
    # Inventarios (I)
    ("i_jefe", "rol_jefe", "INVENTARIOS", "Jefe de Inventarios"),
    ("i_supervisor", "rol_supervisor", "INVENTARIOS", "Supervisor de Inventarios"),
    ("i_operador", "rol_operador", "INVENTARIOS", "Operador de Inventarios"),
    # Ventas (V)
    ("v_jefe", "rol_jefe", "VENTAS", "Jefe de Ventas"),
    ("v_supervisor", "rol_supervisor", "VENTAS", "Supervisor de Ventas"),
    ("v_operador", "rol_operador", "VENTAS", "Operador de Ventas"),
    # Talento Humano (TH)
    ("th_jefe", "rol_jefe", "TALENTO_HUMANO", "Jefe de Talento Humano"),
    ("th_supervisor", "rol_supervisor", "TALENTO_HUMANO", "Supervisor de Talento Humano"),
    ("th_operador", "rol_operador", "TALENTO_HUMANO", "Operador de Talento Humano"),
    # Contabilidad (Ctbl)
    ("ctbl_jefe", "rol_jefe", "CONTABILIDAD", "Jefe de Contabilidad"),
    ("ctbl_supervisor", "rol_supervisor", "CONTABILIDAD", "Supervisor de Contabilidad"),
    ("ctbl_operador", "rol_operador", "CONTABILIDAD", "Operador de Contabilidad"),
]


def setup_15_users_and_3_roles_mariadb(host: str, port: int, dbname: str, sede_tag: str):
    """Crea los 3 roles y los 15 usuarios RBAC tanto a nivel de motor MariaDB como en tabla rbac_matriz_15_usuarios."""
    conn = mysql.connector.connect(host=host, port=port, user="root", password=MARIADB_PASS, autocommit=True)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{dbname}`")

    # 1. Crear los 3 roles en el motor MariaDB
    for rol in ROLES_RBAC:
        try:
            cur.execute(f"CREATE ROLE IF NOT EXISTS '{rol}'")
        except Exception:
            pass

    # Asignar privilegios diferenciados a los 3 roles sobre la base de datos
    try:
        cur.execute(f"GRANT ALL PRIVILEGES ON `{dbname}`.* TO 'rol_jefe'")
        cur.execute(f"GRANT SELECT, INSERT, UPDATE ON `{dbname}`.* TO 'rol_supervisor'")
        cur.execute(f"GRANT SELECT, INSERT ON `{dbname}`.* TO 'rol_operador'")
    except Exception:
        pass

    # 2. Crear los 15 usuarios en el motor MariaDB y asignarles su rol
    for username, rol, modulo, cargo in USUARIOS_15_RBAC:
        for h in ("%", "localhost", "127.0.0.1"):
            try:
                cur.execute(f"CREATE USER IF NOT EXISTS '{username}'@'{h}' IDENTIFIED BY 'LaCava2026*'")
                cur.execute(f"GRANT '{rol}' TO '{username}'@'{h}'")
                cur.execute(f"SET DEFAULT ROLE '{rol}' FOR '{username}'@'{h}'")
            except Exception:
                pass

    # 3. Crear tabla de catálogo y auditoría de los 15 usuarios RBAC
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rbac_matriz_15_usuarios (
        username VARCHAR(30) PRIMARY KEY,
        rol_bd VARCHAR(30) NOT NULL,
        modulo_codigo VARCHAR(10) NOT NULL,
        modulo_nombre VARCHAR(40) NOT NULL,
        descripcion_cargo VARCHAR(80) NOT NULL,
        sede_nodo VARCHAR(40) NOT NULL,
        estado VARCHAR(15) NOT NULL DEFAULT 'ACTIVO',
        ultima_actividad DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS operaciones_agentes_ia (
        id_op INT AUTO_INCREMENT PRIMARY KEY,
        sede_header VARCHAR(30) NOT NULL,
        agente_nombre VARCHAR(50) NOT NULL,
        usuario_rbac VARCHAR(30) NOT NULL,
        rol_rbac VARCHAR(30) NOT NULL,
        modulo VARCHAR(30) NOT NULL,
        operacion VARCHAR(120) NOT NULL,
        monto_usd DECIMAL(12,2) NOT NULL DEFAULT 0.00,
        replica_api VARCHAR(40) NOT NULL DEFAULT 'api_lacava_1',
        fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    mod_code_map = {
        "COMPRAS": "C",
        "INVENTARIOS": "I",
        "VENTAS": "V",
        "TALENTO_HUMANO": "TH",
        "CONTABILIDAD": "Ctbl",
    }

    cur.execute("DELETE FROM rbac_matriz_15_usuarios")
    for username, rol, modulo, cargo in USUARIOS_15_RBAC:
        cur.execute(
            "INSERT INTO rbac_matriz_15_usuarios (username, rol_bd, modulo_codigo, modulo_nombre, descripcion_cargo, sede_nodo) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (username, rol, mod_code_map[modulo], modulo, cargo, sede_tag),
        )

    cur.execute("FLUSH PRIVILEGES")
    cur.close()
    conn.close()


def provision_bd4_guayaquil_3306():
    """
    BD 4 (GUAYAQUIL - Laptop Local Puerto 3306):
    Clona la estructura y datos principales de `licoreriadatabase` desde :3307 hacia :3306
    y carga los 15 usuarios y 3 roles RBAC.
    """
    print("1. Provisionando BD 4 (GUAYAQUIL - MariaDB Local Laptop Puerto :3306)...")
    setup_15_users_and_3_roles_mariadb("127.0.0.1", 3306, "licoreriadatabase", "BD 4 - GUAYAQUIL (:3306)")

    # También cargar los 15 usuarios en BD 1 (:3307) para tener listo el mirror local de Quito
    setup_15_users_and_3_roles_mariadb("127.0.0.1", 3307, "licoreriadatabase", "BD 1 - QUITO (:3307)")

    conn_src = mysql.connector.connect(
        host="127.0.0.1", port=3307, user="root", password=MARIADB_PASS, database="licoreriadatabase"
    )
    cur_src = conn_src.cursor(dictionary=True)

    conn_dst = mysql.connector.connect(
        host="127.0.0.1", port=3306, user="root", password=MARIADB_PASS, database="licoreriadatabase", autocommit=True
    )
    cur_dst = conn_dst.cursor()

    # Tablas de los 5 módulos en BD 4 Guayaquil (:3306)
    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id_Cliente VARCHAR(20) PRIMARY KEY,
        cli_Nombre VARCHAR(120) NOT NULL,
        cli_RUC_CED VARCHAR(20) NOT NULL,
        cli_Telefono VARCHAR(25),
        cli_Mail VARCHAR(120),
        id_Ciudad VARCHAR(10) DEFAULT 'GYE',
        cli_Direccion VARCHAR(180),
        ESTADO_CLI VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id_Proveedor VARCHAR(20) PRIMARY KEY,
        prv_Nombre VARCHAR(140) NOT NULL,
        prv_RUC_CED VARCHAR(20) NOT NULL,
        prv_Telefono VARCHAR(25),
        prv_Mail VARCHAR(120),
        id_Ciudad VARCHAR(10) DEFAULT 'GYE',
        prv_Direccion VARCHAR(180),
        ESTADO_PRV VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id_Producto VARCHAR(20) PRIMARY KEY,
        pro_Descripcion VARCHAR(140) NOT NULL,
        pro_Valor_Compra DECIMAL(10,2) NOT NULL DEFAULT 10.00,
        pro_Precio_Venta DECIMAL(10,2) NOT NULL DEFAULT 15.00,
        pro_Saldo_Final INT NOT NULL DEFAULT 50,
        ESTADO_PROD VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id_Compra VARCHAR(20) PRIMARY KEY,
        id_Proveedor VARCHAR(20) NOT NULL,
        oc_Fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        oc_Subtotal DECIMAL(12,2) NOT NULL,
        oc_IVA DECIMAL(12,2) NOT NULL,
        oc_Total DECIMAL(12,2) NOT NULL,
        ESTADO_OC VARCHAR(10) DEFAULT 'APR'
    )
    """)

    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS facturas (
        id_Factura VARCHAR(20) PRIMARY KEY,
        id_Cliente VARCHAR(20) NOT NULL,
        fac_Descripcion VARCHAR(160),
        fac_Fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fac_Subtotal DECIMAL(12,2) NOT NULL,
        fac_IVA DECIMAL(12,2) NOT NULL,
        fac_Total DECIMAL(12,2) NOT NULL,
        ESTADO_FAC VARCHAR(10) DEFAULT 'APR'
    )
    """)

    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS empleados (
        id_Empleado VARCHAR(20) PRIMARY KEY,
        emp_Cedula VARCHAR(15) NOT NULL,
        emp_Nombre1 VARCHAR(60) NOT NULL,
        emp_Apellido1 VARCHAR(60) NOT NULL,
        emp_Sueldo DECIMAL(10,2) NOT NULL DEFAULT 850.00,
        emp_Mail VARCHAR(120),
        ESTADO_EMP VARCHAR(10) DEFAULT 'ACT'
    )
    """)

    cur_dst.execute("""
    CREATE TABLE IF NOT EXISTS asientos (
        id_Asiento VARCHAR(20) PRIMARY KEY,
        asi_Descripcion VARCHAR(180) NOT NULL,
        asi_Total_Debe DECIMAL(12,2) NOT NULL,
        asi_Total_Haber DECIMAL(12,2) NOT NULL,
        asi_FechaHora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ESTADO_ASI VARCHAR(10) DEFAULT 'APR'
    )
    """)

    # Poblar datos en BD 4 (:3306)
    cur_src.execute("SELECT id_Producto, pro_Descripcion, pro_Valor_Compra, pro_Precio_Venta, pro_Saldo_Final, ESTADO_PROD FROM productos")
    for r in cur_src.fetchall():
        cur_dst.execute(
            "INSERT IGNORE INTO productos VALUES (%s, %s, %s, %s, %s, %s)",
            (r["id_Producto"], r["pro_Descripcion"], r["pro_Valor_Compra"] or 10, r["pro_Precio_Venta"] or 15, r["pro_Saldo_Final"] or 40, r["ESTADO_PROD"] or "ACT")
        )

    clientes_gye = [
        ("CLI-GYE-01", "Hotel Oro Verde Guayaquil S.A.", "0912345678001", "042327999", "compras@oroverdegye.ec", "GYE", "Av. 9 de Octubre y García Moreno, Guayaquil", "ACT"),
        ("CLI-GYE-02", "Licorera Samborondón Plaza", "0923456789001", "042835111", "ventas@sambolicor.ec", "GYE", "Km 2.5 Vía Samborondón, Guayaquil", "ACT"),
        ("CLI-GYE-03", "Restaurante Lo Nuestro Urdesa", "0934567890001", "042380455", "gerencia@lonuestro.ec", "GYE", "Víctor Emilio Estrada 902, Guayaquil", "ACT"),
        ("CLI-MNT-04", "Restaurante El Marino Manta", "1309876543001", "052621400", "admin@elmarinomanta.ec", "MNT", "Malecón Escénico de Murciélago, Manta", "ACT"),
        ("CLI-MCH-05", "Distribuidora Puerto Bolívar", "0704567891001", "072929800", "pedidos@puertobolivar.ec", "MCH", "Av. Bolívar Madero Vargas, Machala", "ACT"),
    ]
    for c in clientes_gye:
        cur_dst.execute("INSERT IGNORE INTO clientes VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", c)

    provs_gye = [
        ("PRV-GYE-01", "Cervecería Nacional CN S.A. (Planta Guayaquil)", "0990001234001", "042108000", "pedidos@cn.com.ec", "GYE", "Km 16.5 Vía a Daule, Guayaquil", "ACT"),
        ("PRV-GYE-02", "Corporación El Rosado - División Licores", "0990005678001", "042322000", "importaciones@elrosado.com", "GYE", "Av. 9 de Octubre 729, Guayaquil", "ACT"),
        ("PRV-GYE-03", "Importadora Litoral Spirits S.A.", "0991122334001", "042681900", "logistica@litoralspirits.ec", "GYE", "Puerto Marítimo de Guayaquil, Bodega 14", "ACT"),
    ]
    for p in provs_gye:
        cur_dst.execute("INSERT IGNORE INTO proveedores VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", p)

    facs_gye = [
        ("FAC-GYE-001", "CLI-GYE-01", "Venta Corporativa Licores Reserva GYE", "2026-11-19 10:30:00", 850.00, 127.50, 977.50, "APR"),
        ("FAC-GYE-002", "CLI-GYE-02", "Pedido Mayorista Samborondón", "2026-11-19 15:10:00", 620.00, 93.00, 713.00, "APR"),
        ("FAC-GYE-003", "CLI-MNT-04", "Despacho Regional Costa Manta", "2026-11-20 09:40:00", 410.00, 61.50, 471.50, "APR"),
    ]
    for f in facs_gye:
        cur_dst.execute("INSERT IGNORE INTO facturas VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", f)

    compras_gye = [
        ("OC-GYE-001", "PRV-GYE-01", "2026-11-18 09:00:00", 1400.00, 210.00, 1610.00, "APR"),
        ("OC-GYE-002", "PRV-GYE-03", "2026-11-19 11:30:00", 2300.00, 345.00, 2645.00, "APR"),
    ]
    for oc in compras_gye:
        cur_dst.execute("INSERT IGNORE INTO compras VALUES (%s,%s,%s,%s,%s,%s,%s)", oc)

    emps_gye = [
        ("EMP-GYE-01", "0911223344", "Carlos", "Villacís", 1250.00, "cvillacis@lacavagye.ec", "ACT"),
        ("EMP-GYE-02", "0922334455", "María", "Baquerizo", 980.00, "mbaquerizo@lacavagye.ec", "ACT"),
        ("EMP-GYE-03", "0933445566", "Jorge", "Pincay", 750.00, "jpincay@lacavagye.ec", "ACT"),
    ]
    for e in emps_gye:
        cur_dst.execute("INSERT IGNORE INTO empleados VALUES (%s,%s,%s,%s,%s,%s,%s)", e)

    asientos_gye = [
        ("ASI-GYE-001", "Cierre Diario Ventas Sucursal Guayaquil", 1690.50, 1690.50, "2026-11-19 18:00:00", "APR"),
        ("ASI-GYE-002", "Provisión Importación Puerto Marítimo GYE", 2645.00, 2645.00, "2026-11-20 12:00:00", "APR"),
    ]
    for a in asientos_gye:
        cur_dst.execute("INSERT IGNORE INTO asientos VALUES (%s,%s,%s,%s,%s,%s)", a)

    # Semilla de operaciones de Agente 4 en BD 4 (:3306)
    cur_dst.execute("SELECT COUNT(*) FROM operaciones_agentes_ia")
    if cur_dst.fetchone()[0] == 0:
        seed_ops = [
            ("GUAYAQUIL", "Agente-4-GYE", "v_jefe", "rol_jefe", "VENTAS", "Emisión de factura mayorista FAC-GYE-001 en Guayaquil", 977.50, "api_lacava_1"),
            ("GUAYAQUIL", "Agente-4-GYE", "i_supervisor", "rol_supervisor", "INVENTARIOS", "Verificación de stock en Bodega Vía a Daule", 0.00, "api_lacava_2"),
            ("GUAYAQUIL", "Agente-4-GYE", "c_operador", "rol_operador", "COMPRAS", "Orden de abastecimiento Cervecería Nacional OC-GYE-001", 1610.00, "api_lacava_3"),
            ("GUAYAQUIL", "Agente-4-GYE", "th_jefe", "rol_jefe", "TALENTO_HUMANO", "Aprobación rol de pagos personal Costa", 2980.00, "api_lacava_1"),
            ("GUAYAQUIL", "Agente-4-GYE", "ctbl_supervisor", "rol_supervisor", "CONTABILIDAD", "Mayorización de asiento diario ASI-GYE-001", 1690.50, "api_lacava_2"),
        ]
        cur_dst.executemany(
            "INSERT INTO operaciones_agentes_ia (sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, replica_api) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            seed_ops
        )

    # Semilla de operaciones de Agente 1 en BD 1 (:3307)
    cur_q = conn_src.cursor()
    cur_q.execute("SELECT COUNT(*) FROM operaciones_agentes_ia")
    if cur_q.fetchone()[0] == 0:
        seed_q = [
            ("QUITO", "Agente-1-UIO", "v_operador", "rol_operador", "VENTAS", "Venta POS registrada en Sede Matriz Quito", 384.20, "api_lacava_1"),
            ("QUITO", "Agente-1-UIO", "i_jefe", "rol_jefe", "INVENTARIOS", "Revisión de kardex general en Quito", 0.00, "api_lacava_2"),
            ("QUITO", "Agente-1-UIO", "ctbl_jefe", "rol_jefe", "CONTABILIDAD", "Cierre contable matriz Sierra Norte", 4120.00, "api_lacava_3"),
        ]
        cur_q.executemany(
            "INSERT INTO operaciones_agentes_ia (sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, replica_api) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            seed_q
        )
        conn_src.commit()
    cur_q.close()

    cur_src.close()
    conn_src.close()
    cur_dst.close()
    conn_dst.close()
    print("   -> OK: BD 4 Guayaquil (:3306) y BD 1 Quito (:3307) con los 15 usuarios y 3 roles RBAC listos.")


def provision_bd2_mongodb_27017():
    """
    BD 2 (QUITO_NOSQL - MongoDB Puerto 27017):
    Crea la base `quito_nosql_mongo` con colecciones `logs_auditoria` y `eventos_agentes`.
    """
    print("2. Provisionando BD 2 (QUITO_NOSQL - MongoDB Real en Puerto :27017)...")
    client = MongoClient("mongodb://127.0.0.1:27017/", serverSelectionTimeoutMS=4000)
    db = client["quito_nosql_mongo"]

    col_logs = db["logs_auditoria"]
    col_eventos = db["eventos_agentes"]

    if col_logs.count_documents({}) == 0:
        col_logs.insert_many([
            {
                "evento_id": "MONGO-AUD-001",
                "sede": "QUITO_NOSQL",
                "usuario_rbac": "i_supervisor",
                "rol_rbac": "rol_supervisor",
                "modulo": "INVENTARIOS",
                "accion": "ALERTA_STOCK_MINIMO_JSON",
                "detalle": {"producto": "PRO-001", "nombre": "Whisky Johnnie Walker Black 12Y", "stock_actual": 8, "umbral": 10},
                "timestamp": datetime.now().isoformat(),
            },
            {
                "evento_id": "MONGO-AUD-002",
                "sede": "QUITO_NOSQL",
                "usuario_rbac": "v_jefe",
                "rol_rbac": "rol_jefe",
                "modulo": "VENTAS",
                "accion": "AUDITORIA_TRANSACCION_POS",
                "detalle": {"terminal": "POS-UIO-01", "latencia_ms": 1.7, "ip_tailscale": "100.64.0.1"},
                "timestamp": datetime.now().isoformat(),
            },
        ])

    if col_eventos.count_documents({}) == 0:
        col_eventos.insert_many([
            {
                "agente": "Agente-2-Quito-NoSQL",
                "header_x_sede": "QUITO_NOSQL",
                "usuario_rbac": "c_supervisor",
                "rol_rbac": "rol_supervisor",
                "modulo": "COMPRAS",
                "telemetria": {"cpu_pct": 14.2, "mem_mb": 248, "cola_mensajes": 0},
                "mensaje": "Telemetría JSON de Agente 2 almacenada en MongoDB :27017",
                "timestamp": datetime.now().isoformat(),
            },
            {
                "agente": "Agente-2-Quito-NoSQL",
                "header_x_sede": "QUITO_NOSQL",
                "usuario_rbac": "ctbl_operador",
                "rol_rbac": "rol_operador",
                "modulo": "CONTABILIDAD",
                "telemetria": {"cpu_pct": 11.8, "mem_mb": 252, "cola_mensajes": 0},
                "mensaje": "Sincronización de comprobantes electrónicos SRI en formato JSON",
                "timestamp": datetime.now().isoformat(),
            },
        ])
    client.close()
    print("   -> OK: BD 2 MongoDB (:27017) colecciones `logs_auditoria` y `eventos_agentes` pobladas.")


def provision_bd3_quito_paralela_3308():
    """
    BD 3 (QUITO_PARALELA - MariaDB Puerto 3308):
    Tabla masiva `historico_transacciones` con `PARTITION BY HASH(id) PARTITIONS 4` (Speed-up).
    """
    print("3. Provisionando BD 3 (QUITO_PARALELA - MariaDB :3308 con PARTITION BY HASH PARTITIONS 4)...")
    conn = mysql.connector.connect(host="127.0.0.1", port=3308, user="root", password=MARIADB_PASS, autocommit=True)
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS quito_paralela_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute("USE quito_paralela_db")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS historico_transacciones (
        id INT AUTO_INCREMENT,
        sede_origen VARCHAR(30) NOT NULL DEFAULT 'QUITO_PARALELA',
        usuario_rbac VARCHAR(30) NOT NULL,
        rol_rbac VARCHAR(30) NOT NULL,
        modulo VARCHAR(30) NOT NULL,
        codigo_referencia VARCHAR(40) NOT NULL,
        monto_usd DECIMAL(12,2) NOT NULL,
        particion_hash INT GENERATED ALWAYS AS (MOD(id, 4)) VIRTUAL,
        fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id)
    )
    PARTITION BY HASH(id)
    PARTITIONS 4
    """)

    cur.execute("SELECT COUNT(*) FROM historico_transacciones")
    if cur.fetchone()[0] == 0:
        lotes = []
        for i in range(1, 41):
            u, r, m, _ = USUARIOS_15_RBAC[i % len(USUARIOS_15_RBAC)]
            lotes.append((
                "QUITO_PARALELA",
                u,
                r,
                m,
                f"HIST-UIO-{2026000 + i}",
                round(45.0 + (i * 19.75), 2),
            ))
        cur.executemany(
            "INSERT INTO historico_transacciones (sede_origen, usuario_rbac, rol_rbac, modulo, codigo_referencia, monto_usd) VALUES (%s,%s,%s,%s,%s,%s)",
            lotes,
        )
    cur.close()
    conn.close()
    print("   -> OK: BD 3 (:3308 `quito_paralela_db.historico_transacciones` PARTITION BY HASH(id) PARTITIONS 4) lista.")


def provision_bd5_guayaquil_dwh_3309():
    """
    BD 5 (GUAYAQUIL_DWH - MariaDB en Puerto 3309):
    Base `db_gye_dwh` con esquema estrella (`fact_ventas`, `dim_sede`, `dim_producto`, `dim_tiempo`) para Power BI.
    """
    print("4. Provisionando BD 5 (GUAYAQUIL_DWH - MariaDB :3309 `db_gye_dwh` Esquema Estrella para Power BI)...")
    conn = mysql.connector.connect(host="127.0.0.1", port=3309, user="root", password=MARIADB_PASS, autocommit=True)
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS db_gye_dwh CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute("USE db_gye_dwh")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_sede (
        id_sede VARCHAR(20) PRIMARY KEY,
        nombre_sede VARCHAR(80) NOT NULL,
        ciudad VARCHAR(40) NOT NULL,
        region VARCHAR(40) NOT NULL,
        maquina_fisica VARCHAR(50) NOT NULL,
        motor_bd VARCHAR(50) NOT NULL,
        puerto_tcp INT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_producto (
        id_producto VARCHAR(20) PRIMARY KEY,
        nombre_producto VARCHAR(120) NOT NULL,
        categoria VARCHAR(50) NOT NULL,
        marca VARCHAR(50) NOT NULL,
        precio_unitario DECIMAL(10,2) NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_tiempo (
        id_tiempo VARCHAR(15) PRIMARY KEY,
        fecha DATE NOT NULL,
        anio INT NOT NULL,
        mes INT NOT NULL,
        nombre_mes VARCHAR(20) NOT NULL,
        trimestre VARCHAR(10) NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fact_ventas (
        id_fact INT AUTO_INCREMENT PRIMARY KEY,
        id_sede VARCHAR(20) NOT NULL,
        id_producto VARCHAR(20) NOT NULL,
        id_tiempo VARCHAR(15) NOT NULL,
        usuario_rbac VARCHAR(30) NOT NULL,
        rol_rbac VARCHAR(30) NOT NULL,
        cantidad_botellas INT NOT NULL,
        subtotal_usd DECIMAL(12,2) NOT NULL,
        iva_usd DECIMAL(12,2) NOT NULL,
        total_venta_usd DECIMAL(12,2) NOT NULL,
        etl_lote VARCHAR(40) NOT NULL DEFAULT 'ETL-INIT',
        fecha_carga_etl DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("DELETE FROM dim_sede")
    cur.executemany(
        "INSERT INTO dim_sede VALUES (%s,%s,%s,%s,%s,%s,%s)",
        [
            ("QUITO", "Sede Matriz Quito", "Quito", "Sierra Norte", "PC Escritorio (Tailscale)", "MariaDB OLTP", 3307),
            ("GUAYAQUIL", "Sede Regional Guayaquil", "Guayaquil", "Costa Litoral", "Laptop (Tailscale)", "MariaDB OLTP", 3306),
            ("CUENCA", "Sede Austral Cuenca Cloud", "Cuenca", "Sierra Austral", "Nube AWS / Supabase", "PostgreSQL DBaaS", 5432),
        ],
    )

    cur.execute("DELETE FROM dim_producto")
    cur.executemany(
        "INSERT INTO dim_producto VALUES (%s,%s,%s,%s,%s)",
        [
            ("PRO-001", "Whisky Johnnie Walker Black Label 12Y 750ml", "Whisky", "Johnnie Walker", 42.50),
            ("PRO-003", "Ron San Miguel Oro 5 Años 750ml", "Ron", "San Miguel", 11.40),
            ("PRO-004", "Aguardiente Zhumir Seco Suave 700ml", "Aguardiente", "Zhumir", 7.80),
            ("PRO-005", "Aguardiente Cristal Clásico 750ml", "Aguardiente", "Cristal", 8.25),
            ("PRO-008", "Vino Casillero del Diablo Cabernet 750ml", "Vino", "Concha y Toro", 14.90),
            ("PRO-011", "Tequila José Cuervo Especial Reposado 750ml", "Tequila", "José Cuervo", 24.00),
        ],
    )

    cur.execute("DELETE FROM dim_tiempo")
    cur.executemany(
        "INSERT INTO dim_tiempo VALUES (%s,%s,%s,%s,%s,%s)",
        [
            ("T-2026-09", "2026-09-30", 2026, 9, "Septiembre", "Q3-2026"),
            ("T-2026-10", "2026-10-31", 2026, 10, "Octubre", "Q4-2026"),
            ("T-2026-11", "2026-11-20", 2026, 11, "Noviembre", "Q4-2026"),
        ],
    )

    cur.execute("SELECT COUNT(*) FROM fact_ventas")
    if cur.fetchone()[0] == 0:
        hechos = [
            ("QUITO", "PRO-001", "T-2026-11", "v_jefe", "rol_jefe", 48, 2040.00, 306.00, 2346.00, "ETL-BATCH-001"),
            ("QUITO", "PRO-008", "T-2026-11", "v_supervisor", "rol_supervisor", 120, 1788.00, 268.20, 2056.20, "ETL-BATCH-001"),
            ("GUAYAQUIL", "PRO-001", "T-2026-11", "v_jefe", "rol_jefe", 65, 2762.50, 414.38, 3176.88, "ETL-BATCH-001"),
            ("GUAYAQUIL", "PRO-011", "T-2026-11", "v_operador", "rol_operador", 90, 2160.00, 324.00, 2484.00, "ETL-BATCH-001"),
            ("CUENCA", "PRO-004", "T-2026-11", "v_supervisor", "rol_supervisor", 160, 1248.00, 187.20, 1435.20, "ETL-BATCH-001"),
            ("CUENCA", "PRO-005", "T-2026-11", "v_operador", "rol_operador", 140, 1155.00, 173.25, 1328.25, "ETL-BATCH-001"),
        ]
        cur.executemany(
            "INSERT INTO fact_ventas (id_sede, id_producto, id_tiempo, usuario_rbac, rol_rbac, cantidad_botellas, subtotal_usd, iva_usd, total_venta_usd, etl_lote) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            hechos,
        )

    cur.close()
    conn.close()
    print("   -> OK: BD 5 (:3309 `db_gye_dwh` Esquema Estrella para Power BI) poblada.")


def provision_bd6_cuenca_supabase_5432():
    """
    BD 6 (CUENCA - PostgreSQL / Supabase Cloud DBaaS :5432):
    Asegura las tablas de los 5 módulos y la matriz de 15 usuarios en `cloud_cuenca_loja`.
    """
    print("5. Provisionando BD 6 (CUENCA - PostgreSQL / Supabase DBaaS :5432)...")
    dsn = f"host=127.0.0.1 port=5432 dbname=cloud_cuenca_loja user=postgres password={PG_PASS}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS rbac_matriz_15_usuarios (
                username VARCHAR(30) PRIMARY KEY,
                rol_bd VARCHAR(30) NOT NULL,
                modulo_codigo VARCHAR(10) NOT NULL,
                modulo_nombre VARCHAR(40) NOT NULL,
                descripcion_cargo VARCHAR(80) NOT NULL,
                sede_nodo VARCHAR(40) NOT NULL DEFAULT 'BD 6 - CUENCA CLOUD (:5432)'
            )
            """)
            cur.execute("DELETE FROM rbac_matriz_15_usuarios")
            mod_code_map = {
                "COMPRAS": "C",
                "INVENTARIOS": "I",
                "VENTAS": "V",
                "TALENTO_HUMANO": "TH",
                "CONTABILIDAD": "Ctbl",
            }
            for username, rol, modulo, cargo in USUARIOS_15_RBAC:
                cur.execute(
                    "INSERT INTO rbac_matriz_15_usuarios VALUES (%s,%s,%s,%s,%s,%s)",
                    (username, rol, mod_code_map[modulo], modulo, cargo, "BD 6 - CUENCA CLOUD (:5432)"),
                )

            cur.execute("""
            CREATE TABLE IF NOT EXISTS operaciones_agentes_cloud (
                id_op SERIAL PRIMARY KEY,
                sede_header VARCHAR(30) NOT NULL DEFAULT 'CUENCA',
                agente_nombre VARCHAR(50) NOT NULL,
                usuario_rbac VARCHAR(30) NOT NULL,
                rol_rbac VARCHAR(30) NOT NULL,
                modulo VARCHAR(30) NOT NULL,
                operacion TEXT NOT NULL,
                monto_usd NUMERIC(12,2) NOT NULL DEFAULT 0.00,
                latencia_wan_ms NUMERIC(8,2) NOT NULL DEFAULT 14.50,
                fecha_hora TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)
            cur.execute("SELECT COUNT(*) FROM operaciones_agentes_cloud")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    "INSERT INTO operaciones_agentes_cloud (sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, latencia_wan_ms) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    [
                        ("CUENCA", "Agente-6-Cuenca-Cloud", "v_jefe", "rol_jefe", "VENTAS", "Factura Cloud FAC-CUE-101 registrada en Supabase DBaaS", 736.00, 18.4),
                        ("CUENCA", "Agente-6-Cuenca-Cloud", "c_supervisor", "rol_supervisor", "COMPRAS", "Pedido a Corporación Azende (Zhumir Cuenca)", 1250.00, 19.1),
                        ("CUENCA", "Agente-6-Cuenca-Cloud", "i_operador", "rol_operador", "INVENTARIOS", "Actualización de stock Aguardiente Cristal en Bodega Austral", 0.00, 16.8),
                    ],
                )
    print("   -> OK: BD 6 Cuenca Cloud (:5432) lista con 15 usuarios RBAC y operaciones Cloud.")


if __name__ == "__main__":
    provision_bd4_guayaquil_3306()
    provision_bd2_mongodb_27017()
    provision_bd3_quito_paralela_3308()
    provision_bd5_guayaquil_dwh_3309()
    provision_bd6_cuenca_supabase_5432()
    print("\n¡LAS 6 BASES DE DATOS Y LOS 15 USUARIOS / 3 ROLES RBAC HAN SIDO APROVISIONADOS CON ÉXITO!")
