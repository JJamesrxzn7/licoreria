"""
Script de provisión e inicialización del Clúster Multi-Sitio y Multi-Motor
Licorería La Cava (Arquitectura de Pizarra):
- SEDE QUITO (UIO):
  1. Nodo 1 (MariaDB :3307 -> licoreriadatabase + 5 Módulos C, I, V, TH, Ctbl + Fragmentos Quito)
  2. Nodo 2 (MariaDB JSON :3307 -> quito_nosql_db + SQLite Document Store API/data/quito_nosql.db)
  3. Nodo 3 (PostgreSQL 18 :5432 -> quito_otras_dwh Data Warehouse & Auditoría Consolidada)
- SEDE GUAYAQUIL (GYE):
  4. Nodo 4 (MariaDB :3308 -> licoreria_guayaquil Fragmento Horizontal Costa GYE/MNT/MCH)
  5. Nodo 5 (MariaDB :3309 -> licoreria_guayaquil_bodega & PostgreSQL :5432 -> guayaquil_bodega_db)
- SEDE CUENCA / LOJA CLOUD (CUE / LJA):
  6. Nodo 6 (PostgreSQL 18 :5432 -> cloud_cuenca_loja / Supabase Cloud DBaaS Mirror)
"""

import json
import sqlite3
from pathlib import Path
import mysql.connector
import psycopg

MARIADB_PASS = "1597.MyHql"
PG_DSN_BASE = "host=127.0.0.1 port=5432 user=postgres password=147852369.MyPost"


def provision_quito_sql_and_nosql():
    print("1. Provisionando Nodo 1 (Quito SQL :3307) y Nodo 2 (Quito NoSQL :3307 + SQLite)...")
    conn = mysql.connector.connect(
        host="127.0.0.1", port=3307, user="root", password=MARIADB_PASS, autocommit=True
    )
    cur = conn.cursor(dictionary=True)

    cur.execute("USE licoreriadatabase")

    # Vistas de los 5 cilindros de la pizarra (C, I, V, TH, Ctbl)
    cur.execute("""
    CREATE OR REPLACE VIEW mod_c_compras AS
    SELECT oc.id_Compra, oc.id_Proveedor, pr.prv_Nombre AS proveedor, oc.oc_Fecha,
           oc.oc_Subtotal, oc.oc_IVA, oc.oc_Total, oc.ESTADO_OC AS estado
    FROM compras oc
    LEFT JOIN proveedores pr ON oc.id_Proveedor = pr.id_Proveedor
    """)

    cur.execute("""
    CREATE OR REPLACE VIEW mod_i_inventarios AS
    SELECT p.id_Producto, p.pro_Descripcion AS pro_Nombre, p.pro_Precio_Venta AS pro_Precio,
           p.pro_Saldo_Final AS pro_Stock_Actual, 10 AS pro_Stock_Minimo,
           c.cat_Nombre AS categoria, m.mar_Nombre AS marca, p.ESTADO_PROD AS estado
    FROM productos p
    LEFT JOIN categorias c ON p.id_Categoria = c.id_Categoria
    LEFT JOIN marcas m ON p.id_Marca = m.id_Marca
    """)

    cur.execute("""
    CREATE OR REPLACE VIEW mod_v_ventas AS
    SELECT f.id_Factura, f.id_Cliente, cl.cli_Nombre AS cliente,
           cl.id_Ciudad, f.fac_Fecha, f.fac_Subtotal, f.fac_IVA, f.fac_Total, f.ESTADO_FAC AS estado
    FROM facturas f
    LEFT JOIN clientes cl ON f.id_Cliente = cl.id_Cliente
    """)

    cur.execute("""
    CREATE OR REPLACE VIEW mod_th_talento_humano AS
    SELECT e.id_Empleado, CONCAT(e.emp_Nombre1, ' ', e.emp_Apellido1) AS empleado,
           e.emp_Cedula, d.dep_Nombre AS departamento, e.emp_Sueldo, e.ESTADO_EMP AS estado
    FROM empleados e
    LEFT JOIN departamentos d ON e.id_Departamento = d.id_Departamento
    """)

    cur.execute("""
    CREATE OR REPLACE VIEW mod_ctbl_contabilidad AS
    SELECT a.id_Asiento, a.asi_FechaHora AS asi_Fecha, a.asi_Descripcion,
           a.asi_Total_Debe, a.asi_Total_Haber, a.ESTADO_ASI AS estado
    FROM asientos a
    """)

    # Fragmentos Horizontales de Quito (Sierra Norte: UIO, IBR, AMB, LTX, RIO)
    cur.execute("""
    CREATE OR REPLACE VIEW frag_quito_clientes AS
    SELECT cl.id_Cliente, cl.cli_RUC_CED AS cedula_ruc, cl.cli_Nombre AS nombre_completo,
           cl.cli_Mail AS correo, cl.cli_Telefono AS telefono, cl.id_Ciudad,
           ci.ciu_Descripcion AS ciudad, 'QUITO-SIERRA (NODO :3307)' AS nodo_origen
    FROM clientes cl
    LEFT JOIN ciudades ci ON cl.id_Ciudad = ci.id_Ciudad
    WHERE cl.id_Ciudad IN ('UIO', 'IBR', 'AMB', 'LTX', 'RIO') OR cl.id_Ciudad IS NULL
    """)

    cur.execute("""
    CREATE OR REPLACE VIEW frag_quito_facturas AS
    SELECT f.id_Factura, f.id_Cliente, cl.cli_Nombre AS cliente,
           cl.id_Ciudad, f.fac_Fecha, f.fac_Subtotal, f.fac_IVA, f.fac_Total, f.ESTADO_FAC AS estado,
           'QUITO-SIERRA (:3307)' AS sede_nodo
    FROM facturas f
    JOIN clientes cl ON f.id_Cliente = cl.id_Cliente
    WHERE cl.id_Ciudad IN ('UIO', 'IBR', 'AMB', 'LTX', 'RIO') OR cl.id_Ciudad IS NULL
    """)

    cur.execute("""
    CREATE OR REPLACE VIEW frag_quito_empleados AS
    SELECT e.id_Empleado, e.emp_Cedula, CONCAT(e.emp_Nombre1, ' ', e.emp_Apellido1) AS empleado,
           d.dep_Nombre AS departamento, e.emp_Mail AS correo, e.emp_Sueldo, 'SEDE MATRIZ QUITO (:3307)' AS sede
    FROM empleados e
    LEFT JOIN departamentos d ON e.id_Departamento = d.id_Departamento
    """)

    # Obtener productos reales para poblar el catálogo NoSQL y demás nodos
    cur.execute("""
        SELECT p.id_Producto, p.pro_Descripcion AS pro_Nombre, p.pro_Precio_Venta AS pro_Precio,
               p.pro_Saldo_Final AS pro_Stock_Actual,
               COALESCE(c.cat_Nombre, 'Licores') AS categoria,
               COALESCE(m.mar_Nombre, 'Reserva') AS marca
        FROM productos p
        LEFT JOIN categorias c ON p.id_Categoria = c.id_Categoria
        LEFT JOIN marcas m ON p.id_Marca = m.id_Marca
        ORDER BY p.id_Producto
    """)
    productos = cur.fetchall()

    # 1.B: Crear base de datos NoSQL Documental en MariaDB :3307 (quito_nosql_db)
    cur.execute("CREATE DATABASE IF NOT EXISTS quito_nosql_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute("USE quito_nosql_db")

    cur.execute("DROP TABLE IF EXISTS col_catalogo_multimedia_json")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS col_catalogo_multimedia_json (
        doc_id VARCHAR(32) PRIMARY KEY,
        codigo_producto VARCHAR(32) NOT NULL,
        coleccion VARCHAR(40) NOT NULL DEFAULT 'catalogo_multimedia',
        documento_json LONGTEXT NOT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (JSON_VALID(documento_json))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS col_sesiones_telemetria (
        session_id VARCHAR(40) PRIMARY KEY,
        usuario VARCHAR(50) NOT NULL,
        sede_origen VARCHAR(30) NOT NULL,
        payload_json LONGTEXT NOT NULL,
        actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (JSON_VALID(payload_json))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS col_eventos_auditoria_json (
        event_id VARCHAR(40) PRIMARY KEY,
        tipo_evento VARCHAR(50) NOT NULL,
        nodo_origen VARCHAR(40) NOT NULL,
        evento_json LONGTEXT NOT NULL,
        timestamp_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (JSON_VALID(evento_json))
    )
    """)

    cur.execute("DELETE FROM col_catalogo_multimedia_json")
    notas_cata_map = {
        "Whisky": {"aroma": "Roble tostado, vainilla y turba suave", "maridaje": ["Carnes maduradas", "Chocolate amargo 70%", "Queso azul"], "grado_alcoholico": "40% Vol.", "origen": "Escocia"},
        "Ron": {"aroma": "Melaza de caña, frutos secos y caramelo", "maridaje": ["Postres de café", "Habano", "Cordero"], "grado_alcoholico": "37.5% Vol.", "origen": "Caribe / Ecuador"},
        "Vino": {"aroma": "Frutos rojos maduros, ciruela y pimienta negra", "maridaje": ["Asado argentino", "Pastas trufadas", "Quesos curados"], "grado_alcoholico": "13.5% Vol.", "origen": "Chile / Argentina"},
        "Tequila": {"aroma": "Agave azul cocido, cítricos y pimienta blanca", "maridaje": ["Ceviche", "Tacos al pastor", "Guacamole"], "grado_alcoholico": "38% Vol.", "origen": "Jalisco, México"},
        "Aguardiente": {"aroma": "Caña fresca del Paute y anís estrellado", "maridaje": ["Fritada quiteña", "Hornado", "Canelazo tradicional"], "grado_alcoholico": "30% Vol.", "origen": "Cuenca, Ecuador"},
        "Cerveza": {"aroma": "Malta pilsener y lúpulo floral noble", "maridaje": ["Mariscos costa", "Alitas BBQ", "Hamburguesa artesanal"], "grado_alcoholico": "4.5% Vol.", "origen": "Guayaquil / Quito"},
    }

    sqlite_docs = []
    for idx, prod in enumerate(productos, start=1):
        cat = str(prod["categoria"] or "Licores")
        nom = str(prod["pro_Nombre"] or "Licor")
        meta = next((v for k, v in notas_cata_map.items() if k.lower() in cat.lower() or k.lower() in nom.lower()),
                    {"aroma": "Notas herbales, madera y especias dulces", "maridaje": ["Tabla de quesos", "Cortes al grill"], "grado_alcoholico": "35% Vol.", "origen": "Importado / Nacional"})
        doc_id = f"DOC-CAT-{idx:04d}"
        doc_obj = {
            "_id": doc_id,
            "id_Producto": prod["id_Producto"],
            "nombre": nom,
            "categoria": cat,
            "marca": prod["marca"],
            "precio_usd": float(prod["pro_Precio"] or 0),
            "ficha_cata": meta,
            "multimedia": {
                "img_hd": f"https://cdn.lacava.ec/catalogo/{prod['id_Producto']}.webp",
                "ficha_pdf": f"https://cdn.lacava.ec/fichas/{prod['id_Producto']}.pdf"
            },
            "tags_busqueda": [cat.lower(), str(prod["marca"]).lower(), "reserva", "la-cava-quito"],
            "disponibilidad_nodos": {
                "UIO_3307": int(prod["pro_Stock_Actual"] or 25),
                "GYE_3308": int((prod["pro_Stock_Actual"] or 20) * 0.8),
                "CUE_CLOUD_5432": int((prod["pro_Stock_Actual"] or 15) * 0.6)
            }
        }
        doc_str = json.dumps(doc_obj, ensure_ascii=False)
        cur.execute(
            "INSERT INTO col_catalogo_multimedia_json (doc_id, codigo_producto, coleccion, documento_json) VALUES (%s, %s, %s, %s)",
            (doc_id, prod["id_Producto"], "catalogo_multimedia", doc_str)
        )
        sqlite_docs.append((doc_id, prod["id_Producto"], "catalogo_multimedia", doc_str))

    cur.execute("DELETE FROM col_sesiones_telemetria")
    sesiones = [
        ("SES-UIO-9001", "admin", "QUITO-MATRIZ (:3307)", {"ip": "192.168.10.14", "rol": "DBA_SUPERADMIN", "carrito_pos_items": 3, "latencia_ms": 1.4, "device": "POS-Terminal-Quito-01", "modulos_activos": ["C", "I", "V", "TH", "Ctbl"]}),
        ("SES-UIO-9002", "cajero.quito", "QUITO-NORTE (:3307)", {"ip": "192.168.10.22", "rol": "CAJERO_VENTAS", "carrito_pos_items": 5, "latencia_ms": 1.8, "device": "POS-Terminal-Quito-02", "modulos_activos": ["V", "I"]}),
        ("SES-GYE-9003", "bodega.guayaquil", "GUAYAQUIL-PUERTO (:3308)", {"ip": "10.20.4.18", "rol": "JEFE_BODEGA_COSTA", "carrito_pos_items": 0, "latencia_ms": 3.1, "device": "Handheld-Scanner-GYE", "modulos_activos": ["I", "C"]}),
        ("SES-CUE-9004", "gerente.cuenca", "CUENCA-CLOUD (:5432)", {"ip": "172.16.80.5", "rol": "SUPERVISOR_AUSTRAL", "carrito_pos_items": 2, "latencia_ms": 14.7, "device": "Cloud-Client-Cuenca", "modulos_activos": ["V", "I", "Ctbl"]}),
    ]
    for sid, usr, sede, pl in sesiones:
        cur.execute(
            "INSERT INTO col_sesiones_telemetria (session_id, usuario, sede_origen, payload_json) VALUES (%s, %s, %s, %s)",
            (sid, usr, sede, json.dumps(pl, ensure_ascii=False))
        )

    cur.execute("DELETE FROM col_eventos_auditoria_json")
    eventos = [
        ("EVT-NOSQL-001", "REPLICA_CATALOGO_JSON", "QUITO-NOSQL (:3307)", {"mensaje": "Sincronización de catálogo multimedia JSON completada", "documentos_indexados": len(productos), "motor": "MariaDB JSON + SQLite Document Store"}),
        ("EVT-NOSQL-002", "2PC_COORDINATOR_READY", "MIDDLEWARE-FASTAPI (:8000)", {"nodos_participantes": ["quito-sql:3307", "guayaquil-sql:3308", "cuenca-cloud:5432"], "protocolo": "XA / Two-Phase Commit", "estado": "ACTIVO"}),
        ("EVT-NOSQL-003", "TELEMETRIA_THROUGHPUT", "QUITO-MATRIZ (:3307)", {"usuarios_concurrentes_soportados": 1000, "tps_pico": 85.4, "pool_conexiones": "OK"}),
    ]
    for eid, te, no, ev in eventos:
        cur.execute(
            "INSERT INTO col_eventos_auditoria_json (event_id, tipo_evento, nodo_origen, evento_json) VALUES (%s, %s, %s, %s)",
            (eid, te, no, json.dumps(ev, ensure_ascii=False))
        )

    cur.close()
    conn.close()

    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = data_dir / "quito_nosql.db"
    sconn = sqlite3.connect(sqlite_path)
    scur = sconn.cursor()
    scur.execute("""
    CREATE TABLE IF NOT EXISTS col_catalogo_multimedia_json (
        doc_id TEXT PRIMARY KEY,
        codigo_producto TEXT,
        coleccion TEXT,
        documento_json TEXT
    )
    """)
    scur.execute("DELETE FROM col_catalogo_multimedia_json")
    scur.executemany(
        "INSERT INTO col_catalogo_multimedia_json (doc_id, codigo_producto, coleccion, documento_json) VALUES (?, ?, ?, ?)",
        sqlite_docs
    )
    sconn.commit()
    sconn.close()
    print(f"   -> OK: Quito SQL (:3307) 5 módulos C,I,V,TH,Ctbl + Quito NoSQL (:3307 & {sqlite_path.name}) con {len(sqlite_docs)} docs JSON.")


def provision_guayaquil_nodes():
    print("2. Provisionando Nodo 4 (Guayaquil SQL :3308) y Nodo 5 (Guayaquil Bodega/Réplica :3309)...")
    conn_main = mysql.connector.connect(
        host="127.0.0.1", port=3307, user="root", password=MARIADB_PASS, database="licoreriadatabase"
    )
    cur_main = conn_main.cursor(dictionary=True)

    cur_main.execute("""
        SELECT id_Cliente, cli_RUC_CED, cli_Nombre AS nombre,
               cli_Mail, cli_Telefono, cli_Direccion, COALESCE(id_Ciudad, 'GYE') AS id_Ciudad
        FROM clientes
        WHERE id_Ciudad IN ('GYE', 'MNT', 'MCH', 'ESM', 'STD')
    """)
    clientes_costa = cur_main.fetchall()

    cur_main.execute("""
        SELECT id_Proveedor, prv_RUC_CED, prv_Nombre, prv_Mail, prv_Telefono, prv_Direccion, COALESCE(id_Ciudad, 'GYE') AS id_Ciudad
        FROM proveedores
        WHERE id_Ciudad IN ('GYE', 'MNT', 'MCH')
    """)
    proveedores_costa = cur_main.fetchall()

    cur_main.execute("""
        SELECT p.id_Producto, p.pro_Descripcion AS pro_Nombre, p.pro_Precio_Venta AS pro_Precio,
               p.pro_Saldo_Final AS pro_Stock_Actual, 10 AS pro_Stock_Minimo
        FROM productos p
        ORDER BY p.id_Producto
    """)
    productos_all = cur_main.fetchall()

    cur_main.execute("""
        SELECT f.id_Factura, f.id_Cliente, f.fac_Fecha, f.fac_Subtotal, f.fac_IVA, f.fac_Total, f.ESTADO_FAC AS estado
        FROM facturas f
        JOIN clientes c ON f.id_Cliente = c.id_Cliente
        WHERE c.id_Ciudad IN ('GYE', 'MNT', 'MCH', 'ESM', 'STD')
    """)
    facturas_costa = cur_main.fetchall()

    cur_main.close()
    conn_main.close()

    # NODO 4: MariaDB Puerto 3308 (licoreria_guayaquil)
    conn_3308 = mysql.connector.connect(
        host="127.0.0.1", port=3308, user="root", password=MARIADB_PASS, autocommit=True
    )
    cur_3308 = conn_3308.cursor()
    cur_3308.execute("CREATE DATABASE IF NOT EXISTS licoreria_guayaquil CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur_3308.execute("USE licoreria_guayaquil")

    cur_3308.execute("DROP TABLE IF EXISTS frag_gye_clientes")
    cur_3308.execute("""
    CREATE TABLE IF NOT EXISTS frag_gye_clientes (
        id_Cliente VARCHAR(32) PRIMARY KEY,
        cedula_ruc VARCHAR(25) NOT NULL,
        nombre_completo VARCHAR(120) NOT NULL,
        correo VARCHAR(120),
        telefono VARCHAR(30),
        direccion VARCHAR(180),
        id_Ciudad VARCHAR(16) NOT NULL,
        sede_fragmento VARCHAR(40) NOT NULL DEFAULT 'GUAYAQUIL-COSTA (:3308)'
    )
    """)

    cur_3308.execute("DROP TABLE IF EXISTS frag_gye_proveedores")
    cur_3308.execute("""
    CREATE TABLE IF NOT EXISTS frag_gye_proveedores (
        id_Proveedor VARCHAR(32) PRIMARY KEY,
        ruc VARCHAR(25) NOT NULL,
        razon_social VARCHAR(150) NOT NULL,
        correo VARCHAR(120),
        telefono VARCHAR(30),
        direccion VARCHAR(180),
        id_Ciudad VARCHAR(16) NOT NULL,
        puerto_logistico VARCHAR(50) NOT NULL DEFAULT 'PUERTO MARITIMO GUAYAQUIL'
    )
    """)

    cur_3308.execute("DROP TABLE IF EXISTS frag_gye_inventario")
    cur_3308.execute("""
    CREATE TABLE IF NOT EXISTS frag_gye_inventario (
        id_Producto VARCHAR(32) PRIMARY KEY,
        pro_Nombre VARCHAR(140) NOT NULL,
        pro_Precio DECIMAL(10,2) NOT NULL,
        stock_guayaquil INT NOT NULL,
        stock_minimo INT NOT NULL,
        bodega_ubicacion VARCHAR(60) NOT NULL DEFAULT 'BODEGA REGIONAL COSTA - VIA DAULE'
    )
    """)

    cur_3308.execute("DROP TABLE IF EXISTS frag_gye_facturas")
    cur_3308.execute("""
    CREATE TABLE IF NOT EXISTS frag_gye_facturas (
        id_Factura VARCHAR(32) PRIMARY KEY,
        id_Cliente VARCHAR(32) NOT NULL,
        fac_Fecha DATETIME NOT NULL,
        fac_Subtotal DECIMAL(12,2) NOT NULL,
        fac_IVA DECIMAL(12,2) NOT NULL,
        fac_Total DECIMAL(12,2) NOT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'APR',
        nodo_procesamiento VARCHAR(40) NOT NULL DEFAULT 'GYE-SQL-1 (:3308)'
    )
    """)

    cur_3308.execute("""
    CREATE TABLE IF NOT EXISTS log_auditoria_guayaquil (
        id_log INT AUTO_INCREMENT PRIMARY KEY,
        fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        usuario_bd VARCHAR(60) NOT NULL,
        operacion VARCHAR(30) NOT NULL,
        tabla_afectada VARCHAR(60) NOT NULL,
        detalle VARCHAR(255) NOT NULL,
        puerto_nodo INT NOT NULL DEFAULT 3308
    )
    """)

    cur_3308.execute("DELETE FROM frag_gye_clientes")
    for c in clientes_costa:
        cur_3308.execute(
            "INSERT INTO frag_gye_clientes (id_Cliente, cedula_ruc, nombre_completo, correo, telefono, direccion, id_Ciudad) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (c["id_Cliente"], c["cli_RUC_CED"], c["nombre"], c["cli_Mail"], c["cli_Telefono"], c["cli_Direccion"], c["id_Ciudad"])
        )
    extra_gye_clients = [
        ("CLI-G01", "0912345678001", "Hotel Oro Verde Guayaquil S.A.", "compras@oroverdegye.ec", "042327999", "Av. 9 de Octubre y García Moreno, Guayaquil", "GYE"),
        ("CLI-G02", "0923456789001", "Licorera Samborondón Plaza", "ventas@sambolicor.ec", "042835111", "Km 2.5 Vía Samborondón, Guayaquil", "GYE"),
        ("CLI-G03", "1309876543001", "Restaurante El Marino Manta", "admin@elmarinomanta.ec", "052621400", "Malecón Escénico de Murciélago, Manta", "MNT"),
        ("CLI-G04", "0704567891001", "Distribuidora Puerto Bolívar", "pedidos@puertobolivar.ec", "072929800", "Av. Bolívar Madero Vargas, Machala", "MCH"),
    ]
    for ec in extra_gye_clients:
        cur_3308.execute(
            "INSERT IGNORE INTO frag_gye_clientes (id_Cliente, cedula_ruc, nombre_completo, correo, telefono, direccion, id_Ciudad) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ec
        )

    cur_3308.execute("DELETE FROM frag_gye_proveedores")
    for p in proveedores_costa:
        cur_3308.execute(
            "INSERT INTO frag_gye_proveedores (id_Proveedor, ruc, razon_social, correo, telefono, direccion, id_Ciudad) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (p["id_Proveedor"], p["prv_RUC_CED"], p["prv_Nombre"], p["prv_Mail"], p["prv_Telefono"], p["prv_Direccion"], p["id_Ciudad"])
        )
    extra_gye_provs = [
        ("PRV-G01", "0990001234001", "Cervecería Nacional CN S.A. (Planta Guayaquil)", "pedidos@cn.com.ec", "042108000", "Km 16.5 Vía a Daule, Guayaquil", "GYE"),
        ("PRV-G02", "0990005678001", "Corporación El Rosado - División Licores Importados", "importaciones@elrosado.com", "042322000", "Av. 9 de Octubre 729, Guayaquil", "GYE"),
        ("PRV-G03", "0991122334001", "Importadora Litoral Spirits S.A.", "logistica@litoralspirits.ec", "042681900", "Puerto Marítimo de Guayaquil, Bodega 14", "GYE"),
    ]
    for ep in extra_gye_provs:
        cur_3308.execute(
            "INSERT IGNORE INTO frag_gye_proveedores (id_Proveedor, ruc, razon_social, correo, telefono, direccion, id_Ciudad) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ep
        )

    cur_3308.execute("DELETE FROM frag_gye_inventario")
    for pr in productos_all:
        stock_gye = max(12, int(float(pr["pro_Stock_Actual"] or 20) * 0.85))
        cur_3308.execute(
            "INSERT INTO frag_gye_inventario (id_Producto, pro_Nombre, pro_Precio, stock_guayaquil, stock_minimo) VALUES (%s,%s,%s,%s,%s)",
            (pr["id_Producto"], pr["pro_Nombre"], pr["pro_Precio"], stock_gye, pr["pro_Stock_Minimo"] or 5)
        )

    cur_3308.execute("DELETE FROM frag_gye_facturas")
    for f in facturas_costa:
        cur_3308.execute(
            "INSERT INTO frag_gye_facturas (id_Factura, id_Cliente, fac_Fecha, fac_Subtotal, fac_IVA, fac_Total, estado) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (f["id_Factura"], f["id_Cliente"], f["fac_Fecha"], f["fac_Subtotal"], f["fac_IVA"], f["fac_Total"], f["estado"] or "APR")
        )
    extra_gye_facs = [
        ("FAC-G01", "CLI-G01", "2026-11-18 14:20:00", 850.00, 127.50, 977.50, "APR"),
        ("FAC-G02", "CLI-G02", "2026-11-18 17:45:00", 420.00, 63.00, 483.00, "APR"),
        ("FAC-G03", "CLI-G03", "2026-11-19 09:10:00", 310.00, 46.50, 356.50, "APR"),
    ]
    for ef in extra_gye_facs:
        cur_3308.execute(
            "INSERT IGNORE INTO frag_gye_facturas (id_Factura, id_Cliente, fac_Fecha, fac_Subtotal, fac_IVA, fac_Total, estado) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ef
        )

    cur_3308.execute("DELETE FROM log_auditoria_guayaquil")
    logs_gye = [
        ("root@guayaquil-3308", "FRAGMENT_SYNC", "frag_gye_clientes", "Fragmento horizontal Región Costa (GYE, MNT, MCH) sincronizado"),
        ("pos_guayaquil@10.20.4.18", "INSERT_VENTA", "frag_gye_facturas", "Factura FAC-G01 registrada localmente en Nodo 1 Guayaquil (:3308)"),
        ("coordinador_2pc@quito", "XA_PREPARE_OK", "frag_gye_inventario", "Nodo Guayaquil (:3308) listo para protocolo 2PC con Quito (:3307)"),
    ]
    for u, op, tb, dt in logs_gye:
        cur_3308.execute(
            "INSERT INTO log_auditoria_guayaquil (usuario_bd, operacion, tabla_afectada, detalle) VALUES (%s,%s,%s,%s)",
            (u, op, tb, dt)
        )
    cur_3308.close()
    conn_3308.close()

    # NODO 5: MariaDB Puerto 3309 (licoreria_guayaquil_bodega)
    conn_3309 = mysql.connector.connect(
        host="127.0.0.1", port=3309, user="root", password=MARIADB_PASS, autocommit=True
    )
    cur_3309 = conn_3309.cursor()
    cur_3309.execute("CREATE DATABASE IF NOT EXISTS licoreria_guayaquil_bodega CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur_3309.execute("USE licoreria_guayaquil_bodega")

    cur_3309.execute("DROP TABLE IF EXISTS bodega_importaciones_puerto")
    cur_3309.execute("""
    CREATE TABLE IF NOT EXISTS bodega_importaciones_puerto (
        id_Contenedor VARCHAR(32) PRIMARY KEY,
        naviera VARCHAR(80) NOT NULL,
        origen_embarque VARCHAR(80) NOT NULL,
        id_Producto VARCHAR(32) NOT NULL,
        pro_Nombre VARCHAR(140) NOT NULL,
        cajas_importadas INT NOT NULL,
        botellas_totales INT NOT NULL,
        fecha_arribo_gye DATE NOT NULL,
        estado_aduana VARCHAR(40) NOT NULL DEFAULT 'DESADUANIZADO SENAE'
    )
    """)

    cur_3309.execute("DROP TABLE IF EXISTS replica_stock_costa")
    cur_3309.execute("""
    CREATE TABLE IF NOT EXISTS replica_stock_costa (
        id_Producto VARCHAR(32) PRIMARY KEY,
        pro_Nombre VARCHAR(140) NOT NULL,
        stock_bodega_puerto INT NOT NULL,
        stock_reserva_costa INT NOT NULL,
        ultima_replicacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur_3309.execute("DROP TABLE IF EXISTS despachos_interregionales")
    cur_3309.execute("""
    CREATE TABLE IF NOT EXISTS despachos_interregionales (
        id_Despacho VARCHAR(32) PRIMARY KEY,
        nodo_origen VARCHAR(40) NOT NULL DEFAULT 'GUAYAQUIL-BD2 (:3309)',
        nodo_destino VARCHAR(40) NOT NULL,
        id_Producto VARCHAR(32) NOT NULL,
        cantidad_botellas INT NOT NULL,
        placa_transporte VARCHAR(20) NOT NULL,
        estado_ruta VARCHAR(40) NOT NULL
    )
    """)

    cur_3309.execute("DELETE FROM bodega_importaciones_puerto")
    contenedores = [
        ("MSCU-884120-1", "MSC Mediterranean Shipping", "Glasgow, Escocia (UK)", "PRO-001", "Whisky Johnnie Walker Black Label 12Y 750ml", 120, 1440, "2026-11-10", "DESADUANIZADO SENAE"),
        ("MAEU-441902-7", "Maersk Line", "Valparaíso, Chile", "PRO-008", "Vino Casillero del Diablo Cabernet 750ml", 200, 2400, "2026-11-12", "DESADUANIZADO SENAE"),
        ("HLXU-992014-3", "Hapag-Lloyd", "Veracruz, México", "PRO-011", "Tequila José Cuervo Especial Reposado 750ml", 95, 1140, "2026-11-15", "EN BODEGA PUERTO GYE"),
        ("CMAU-331098-9", "CMA CGM", "Gotemburgo, Suecia", "PRO-015", "Vodka Absolut Original 750ml", 110, 1320, "2026-11-17", "EN BODEGA PUERTO GYE"),
    ]
    for ct in contenedores:
        cur_3309.execute(
            "INSERT INTO bodega_importaciones_puerto VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ct
        )

    cur_3309.execute("DELETE FROM replica_stock_costa")
    for pr in productos_all[:18]:
        cur_3309.execute(
            "INSERT INTO replica_stock_costa (id_Producto, pro_Nombre, stock_bodega_puerto, stock_reserva_costa) VALUES (%s,%s,%s,%s)",
            (pr["id_Producto"], pr["pro_Nombre"], int(pr["pro_Stock_Actual"] or 30) + 40, 24)
        )

    cur_3309.execute("DELETE FROM despachos_interregionales")
    despachos = [
        ("DSP-GYE-001", "GUAYAQUIL-BD2 (:3309)", "QUITO-MATRIZ (:3307)", "PRO-001", 240, "GAA-4821", "ENTREGADO EN QUITO"),
        ("DSP-GYE-002", "GUAYAQUIL-BD2 (:3309)", "CUENCA-CLOUD (:5432)", "PRO-008", 180, "GBB-9104", "EN TRANSITO VIA MOLLETURO"),
        ("DSP-GYE-003", "GUAYAQUIL-BD2 (:3309)", "GUAYAQUIL-BD1 (:3308)", "PRO-011", 120, "GCA-1102", "ENTREGADO SUCURSAL COSTA"),
    ]
    for d in despachos:
        cur_3309.execute("INSERT INTO despachos_interregionales VALUES (%s,%s,%s,%s,%s,%s,%s)", d)

    cur_3309.close()
    conn_3309.close()
    print("   -> OK: Guayaquil Nodo 1 (:3308 licoreria_guayaquil) y Nodo 2 (:3309 licoreria_guayaquil_bodega) poblados.")


def provision_postgres_nodes():
    print("3. Provisionando Nodo 3 (Quito DWH/Otras en PostgreSQL :5432) y Nodo 6 (Cuenca/Loja Cloud en PostgreSQL :5432)...")
    with psycopg.connect(f"{PG_DSN_BASE} dbname=postgres", autocommit=True) as conn:
        with conn.cursor() as cur:
            for dbname in ("quito_otras_dwh", "cloud_cuenca_loja", "guayaquil_bodega_db"):
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                if not cur.fetchone():
                    cur.execute(f'CREATE DATABASE "{dbname}"')

    with psycopg.connect(f"{PG_DSN_BASE} dbname=quito_otras_dwh", autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS dwh_dim_sede (
                id_sede VARCHAR(15) PRIMARY KEY,
                nombre_sede VARCHAR(80) NOT NULL,
                ciudad VARCHAR(50) NOT NULL,
                region VARCHAR(40) NOT NULL,
                motor_principal VARCHAR(60) NOT NULL,
                puerto_tcp INT NOT NULL
            )
            """)
            cur.execute("DELETE FROM dwh_facts_temp WHERE 1=0") if False else None
            cur.execute("""
            CREATE TABLE IF NOT EXISTS dwh_fact_ventas_consolidadas (
                id_hecho SERIAL PRIMARY KEY,
                id_sede VARCHAR(15) NOT NULL REFERENCES dwh_dim_sede(id_sede),
                periodo_mes VARCHAR(10) NOT NULL,
                categoria_licor VARCHAR(60) NOT NULL,
                transacciones_totales INT NOT NULL,
                unidades_vendidas INT NOT NULL,
                ingresos_brutos_usd NUMERIC(12,2) NOT NULL,
                iva_recaudado_usd NUMERIC(12,2) NOT NULL,
                utilidad_neta_usd NUMERIC(12,2) NOT NULL
            )
            """)
            cur.execute("DELETE FROM dwh_fact_ventas_consolidadas")
            cur.execute("DELETE FROM dwh_dim_sede")
            sedes = [
                ("UIO-MATRIZ", "Sede Matriz Quito Norte & Sur", "Quito", "Sierra Norte", "MariaDB 12.3 + NoSQL + PG 18", 3307),
                ("GYE-COSTA", "Sucursal Regional Guayaquil & Costa", "Guayaquil", "Costa Litoral", "MariaDB 12.3 Cluster (:3308/:3309)", 3308),
                ("CUE-LJA-CLOUD", "Sucursal Austral Cuenca & Loja (Cloud)", "Cuenca / Loja", "Sierra Austral", "PostgreSQL 18 Cloud DBaaS / Supabase", 5432),
            ]
            cur.executemany("INSERT INTO dwh_dim_sede VALUES (%s,%s,%s,%s,%s,%s)", sedes)

            hechos = [
                ("UIO-MATRIZ", "2026-11", "Whisky Escocés & Bourbon", 420, 1280, 48640.00, 7296.00, 14592.00),
                ("UIO-MATRIZ", "2026-11", "Vinos Reserva & Espumantes", 380, 1540, 27720.00, 4158.00, 8870.40),
                ("UIO-MATRIZ", "2026-11", "Ron Añejo & Tequila", 310, 950, 22800.00, 3420.00, 6840.00),
                ("GYE-COSTA", "2026-11", "Cervezas & Licores Importados", 390, 2150, 34400.00, 5160.00, 10320.00),
                ("GYE-COSTA", "2026-11", "Whisky & Vodka Puerto GYE", 275, 890, 31150.00, 4672.50, 9345.00),
                ("CUE-LJA-CLOUD", "2026-11", "Aguardientes Australes (Zhumir/Cristal)", 340, 1680, 18480.00, 2772.00, 6468.00),
                ("CUE-LJA-CLOUD", "2026-11", "Vinos & Licores Loja/Cuenca", 195, 620, 14880.00, 2232.00, 4464.00),
            ]
            cur.executemany(
                "INSERT INTO dwh_fact_ventas_consolidadas (id_sede, periodo_mes, categoria_licor, transacciones_totales, unidades_vendidas, ingresos_brutos_usd, iva_recaudado_usd, utilidad_neta_usd) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                hechos
            )

            cur.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_transacciones_2pc (
                tx_id VARCHAR(36) PRIMARY KEY,
                coordinador VARCHAR(60) NOT NULL,
                nodos_involucrados TEXT NOT NULL,
                fase_alcanzada VARCHAR(30) NOT NULL,
                decision_global VARCHAR(20) NOT NULL,
                detalle_operacion TEXT NOT NULL,
                fecha_hora TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)
            cur.execute("DELETE FROM auditoria_transacciones_2pc")
            cur.execute("""
            INSERT INTO auditoria_transacciones_2pc (tx_id, coordinador, nodos_involucrados, fase_alcanzada, decision_global, detalle_operacion)
            VALUES
            ('2PC-TX-0001', 'FastAPI-Middleware-Quito:8000', 'quito-sql:3307, guayaquil-sql:3308, cuenca-cloud:5432', 'PHASE_2_COMMIT', 'GLOBAL_COMMIT', 'Transferencia interregional de 50 botellas de Zhumir desde Cuenca Cloud (:5432) hacia Quito (:3307)'),
            ('2PC-TX-0002', 'FastAPI-Middleware-Quito:8000', 'quito-sql:3307, guayaquil-sql:3308', 'PHASE_1_PREPARE_ABORT', 'GLOBAL_ROLLBACK', 'Simulación Pregunta 5: Fallo inducido en Guayaquil (:3308) durante Fase PREPARE -> Rollback automático en Quito (:3307)')
            """)

    with psycopg.connect(f"{PG_DSN_BASE} dbname=cloud_cuenca_loja", autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cloud_metadata_nodo (
                nodo_id VARCHAR(30) PRIMARY KEY,
                proveedor_nube VARCHAR(60) NOT NULL,
                endpoint_pooler VARCHAR(120) NOT NULL,
                region_cloud VARCHAR(40) NOT NULL,
                certificado_tls VARCHAR(60) NOT NULL,
                sucursales_conectadas VARCHAR(80) NOT NULL,
                estado_tunel VARCHAR(40) NOT NULL
            )
            """)
            cur.execute("DELETE FROM cloud_metadata_nodo")
            cur.execute("""
            INSERT INTO cloud_metadata_nodo VALUES (
                'CUENCA-LOJA-CLOUD',
                'Supabase DBaaS (AWS us-east-1) + Local PG18 Mirror (:5432)',
                'aws-0-us-east-1.pooler.supabase.com:5432 / 127.0.0.1:5432',
                'us-east-1 (N. Virginia) -> Austral WAN',
                'prod-ca-2021.crt (SSL/TLS Verify-Full)',
                'Cuenca (CUE - Azuay) & Loja (LJA - Loja)',
                'ACTIVO - FAILOVER LOCAL HABILITADO'
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frag_austral_clientes (
                id_cliente VARCHAR(10) PRIMARY KEY,
                cedula_ruc VARCHAR(13) NOT NULL,
                nombre_completo VARCHAR(120) NOT NULL,
                correo VARCHAR(120) NOT NULL,
                telefono VARCHAR(20) NOT NULL,
                direccion VARCHAR(160) NOT NULL,
                id_ciudad CHAR(3) NOT NULL,
                sucursal_nube VARCHAR(40) NOT NULL
            )
            """)
            cur.execute("DELETE FROM frag_austral_clientes")
            clientes_austral = [
                ("CLI-C01", "0102345678001", "Hotel Oro Verde Cuenca", "compras@oroverdecuenca.ec", "072831200", "Av. Ordóñez Lasso s/n, Cuenca", "CUE", "SUCURSAL CUENCA (CLOUD)"),
                ("CLI-C02", "0103456789001", "Restaurante Tiesto's Cuenca", "gerencia@tiestoscuenca.ec", "072824511", "Juan Jaramillo 4-89 y Mariano Cueva, Cuenca", "CUE", "SUCURSAL CUENCA (CLOUD)"),
                ("CLI-C03", "0104567890001", "Licorería El Barril Azuayo", "pedidos@barrilazuayo.ec", "072885900", "Av. Remigio Crespo Toral, Cuenca", "CUE", "SUCURSAL CUENCA (CLOUD)"),
                ("CLI-L01", "1102345678001", "Grand Victoria Boutique Hotel Loja", "abastecimiento@grandvictorialoja.ec", "072583500", "Bernardo Valdivieso y José Antonio Eguiguren, Loja", "LJA", "SUCURSAL LOJA (CLOUD)"),
                ("CLI-L02", "1103456789001", "Distribuidora Castellana de Licores Loja", "ventas@castellanaloja.ec", "072571122", "Av. Universitaria y Mercadillo, Loja", "LJA", "SUCURSAL LOJA (CLOUD)"),
                ("CLI-L03", "1104567891001", "Peña Cultural & Tapas Vilcabamba", "admin@vilcabambatapas.ec", "072640210", "Parque Central de Vilcabamba, Loja", "LJA", "SUCURSAL LOJA (CLOUD)"),
            ]
            cur.executemany("INSERT INTO frag_austral_clientes VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", clientes_austral)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frag_austral_proveedores (
                id_proveedor VARCHAR(10) PRIMARY KEY,
                ruc VARCHAR(13) NOT NULL,
                razon_social VARCHAR(150) NOT NULL,
                especialidad VARCHAR(100) NOT NULL,
                ciudad CHAR(3) NOT NULL,
                direccion VARCHAR(160) NOT NULL
            )
            """)
            cur.execute("DELETE FROM frag_austral_proveedores")
            prov_austral = [
                ("PRV-004", "0190005432001", "Corporación Azende S.A. (Destilería Zhumir)", "Aguardiente Zhumir, Piña Colada, Seco Suave", "CUE", "Av. Gil Ramírez Dávalos 14-34, Cuenca"),
                ("PRV-005", "0190087612001", "Embotelladora Azuaya S.A. (EASA - Cristal)", "Aguardiente Cristal, Ron San Miguel, Licores del Sur", "CUE", "Parque Industrial Cuenca, Calle Cornelio Vintimilla"),
                ("PRV-014", "0190154321001", "Distribuidora de Licores Australes Cuenca", "Vinos Australes y Cerveza Artesanal CUE", "CUE", "Av. Remigio Crespo Toral y Agustín Cueva, Cuenca"),
                ("PRV-018", "1190045612001", "Destilería Lojana Cantaclaro Cía. Ltda.", "Aguardiente Cantaclaro de Caña Lojana y Café Lojano", "LJA", "Vía a Malacatos Km 4, Loja"),
            ]
            cur.executemany("INSERT INTO frag_austral_proveedores VALUES (%s,%s,%s,%s,%s,%s)", prov_austral)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frag_austral_inventario (
                id_producto VARCHAR(10) PRIMARY KEY,
                pro_nombre VARCHAR(120) NOT NULL,
                pro_precio NUMERIC(10,2) NOT NULL,
                stock_cuenca INT NOT NULL,
                stock_loja INT NOT NULL,
                bodega_nube VARCHAR(60) NOT NULL DEFAULT 'BODEGA AUSTRAL CUENCA-LOJA'
            )
            """)
            cur.execute("DELETE FROM frag_austral_inventario")
            inv_austral = [
                ("PRO-004", "Aguardiente Zhumir Seco Suave 700ml", 7.80, 180, 95, "PLANTA CUENCA / BODEGA LOJA"),
                ("PRO-014", "Aguardiente Zhumir Piña Colada 700ml", 10.50, 140, 75, "PLANTA CUENCA / BODEGA LOJA"),
                ("PRO-005", "Aguardiente Cristal Clásico 750ml", 8.25, 210, 110, "PARQUE INDUSTRIAL CUENCA"),
                ("PRO-003", "Ron San Miguel Oro 5 Años 750ml", 11.40, 155, 88, "PARQUE INDUSTRIAL CUENCA"),
                ("PRO-001", "Whisky Johnnie Walker Black Label 12Y 750ml", 42.50, 48, 32, "BODEGA AUSTRAL CUENCA-LOJA"),
                ("PRO-008", "Vino Casillero del Diablo Cabernet 750ml", 14.90, 92, 64, "BODEGA AUSTRAL CUENCA-LOJA"),
                ("PRO-020", "Licor Artesanal Cantaclaro Reserva Loja 750ml", 9.60, 60, 150, "BODEGA REGIONAL LOJA"),
            ]
            cur.executemany("INSERT INTO frag_austral_inventario VALUES (%s,%s,%s,%s,%s,%s)", inv_austral)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS frag_austral_facturas (
                id_factura VARCHAR(12) PRIMARY KEY,
                id_cliente VARCHAR(10) NOT NULL,
                sucursal VARCHAR(20) NOT NULL,
                fac_fecha TIMESTAMPTZ NOT NULL,
                fac_subtotal NUMERIC(12,2) NOT NULL,
                fac_iva NUMERIC(12,2) NOT NULL,
                fac_total NUMERIC(12,2) NOT NULL,
                estado VARCHAR(10) NOT NULL DEFAULT 'APR'
            )
            """)
            cur.execute("DELETE FROM frag_austral_facturas")
            facs_austral = [
                ("FAC-CUE-101", "CLI-C01", "CUENCA", "2026-11-18 11:30:00-05", 640.00, 96.00, 736.00, "APR"),
                ("FAC-CUE-102", "CLI-C02", "CUENCA", "2026-11-18 19:15:00-05", 380.00, 57.00, 437.00, "APR"),
                ("FAC-LJA-201", "CLI-L01", "LOJA", "2026-11-18 16:40:00-05", 520.00, 78.00, 598.00, "APR"),
                ("FAC-LJA-202", "CLI-L02", "LOJA", "2026-11-19 08:50:00-05", 290.00, 43.50, 333.50, "APR"),
            ]
            cur.executemany("INSERT INTO frag_austral_facturas VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", facs_austral)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS log_auditoria_cloud (
                id_log SERIAL PRIMARY KEY,
                fecha_hora TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                sucursal_origen VARCHAR(30) NOT NULL,
                usuario_cloud VARCHAR(60) NOT NULL,
                evento VARCHAR(50) NOT NULL,
                detalle TEXT NOT NULL
            )
            """)
            cur.execute("DELETE FROM log_auditoria_cloud")
            cur.execute("""
            INSERT INTO log_auditoria_cloud (sucursal_origen, usuario_cloud, evento, detalle)
            VALUES
            ('CUENCA (CUE)', 'gerente.cuenca@supabase-pooler', 'CLOUD_SYNC_OK', 'Sincronización TLS completada con pooler aws-0-us-east-1.pooler.supabase.com:5432'),
            ('LOJA (LJA)', 'pos.loja@cloud-node', 'FACTURA_EMITIDA', 'Factura FAC-LJA-202 registrada en nodo de la nube Cuenca/Loja'),
            ('QUITO-COORDINADOR', 'middleware_2pc@quito', '2PC_PARTICIPANT_READY', 'Nodo Cloud Cuenca/Loja listo para transacciones distribuidas 2PC')
            """)
    print("   -> OK: PostgreSQL (:5432) bases quito_otras_dwh y cloud_cuenca_loja pobladas.")


if __name__ == "__main__":
    provision_quito_sql_and_nosql()
    provision_guayaquil_nodes()
    provision_postgres_nodes()
    print("\n¡CLÚSTER DE 6 BASES DE DATOS (QUITO 3 + GUAYAQUIL 2 + CUENCA/LOJA CLOUD 1) PROVISIONADO CON ÉXITO!")
