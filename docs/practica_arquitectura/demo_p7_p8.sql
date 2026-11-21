-- =====================================================================
--  PRÁCTICA ARQUITECTURA DE BASES DE DATOS — PREGUNTAS 7 y 8
--  Proyecto: Licorería La Cava  |  BD: licoreriadatabase (MariaDB :3307)
--  Ejecutar en HeidiSQL bloque por bloque (seleccionar + F9) o completo (Ctrl+F9)
-- =====================================================================
USE licoreriadatabase;

-- #####################################################################
--  PREGUNTA 7 — PARADIGMAS DE SERVICIO EN LA NUBE (DBaaS vs. IaaS/PaaS/SaaS),
--               CONTROL DEL SISTEMA Y VENDOR LOCK-IN
-- #####################################################################

-- =====================================================================
--  BLOQUE 7.1: Control del Sistema (IaaS / Local Bare-Metal vs. DBaaS)
-- =====================================================================
-- EXPLICACIÓN ARQUITECTÓNICA:
-- * En IaaS / On-Premise (nuestro MariaDB local en puerto 3307 o un VPS EC2):
--   El DBA posee el privilegio SUPER / root, acceso directo al sistema operativo
--   (version_compile_os) y al sistema de archivos físico (datadir, basedir,
--   secure_file_priv), pudiendo dimensionar buffers (innodb_buffer_pool_size)
--   y durabilidad (innodb_flush_log_at_trx_commit). A cambio, el DBA asume la
--   carga operativa manual de parches, respaldos, failover y discos.
-- * En DBaaS (nuestro Supabase PostgreSQL configurado en API/.env con el pooler
--   aws-0-us-east-1.pooler.supabase.com:5432 y certificado TLS API/prod-ca-2021.crt):
--   El proveedor abstrae el hardware, automatiza backups, alta disponibilidad (HA)
--   y connection pooling (PgBouncer/Supavisor), pero NOS QUITA el control del SO
--   y los privilegios de superusuario (como valida API/postgres_connection.py,
--   donde rolsuper, rolbypassrls, rolcreatedb, rolcreaterole y rolreplication
--   están estrictamente prohibidos para la aplicación).

SHOW VARIABLES WHERE Variable_name IN (
    'datadir',
    'basedir',
    'innodb_buffer_pool_size',
    'innodb_flush_log_at_trx_commit',
    'max_connections',
    'secure_file_priv',
    'log_bin',
    'version_compile_os'
);

SELECT USER()         AS usuario_sesion_cliente,
       CURRENT_USER() AS cuenta_privilegios_efectiva,
       @@hostname     AS nodo_servidor_fisico,
       @@version      AS version_motor_bd,
       'IaaS / On-Premise: Control Total (root + filesystem)' AS paradigma_actual;


-- =====================================================================
--  BLOQUE 7.2: Análisis de Vendor Lock-in en la Capa de Datos
--              (Por qué migrar entre motores o DBaaS cuesta tanto)
-- =====================================================================
-- EXPLICACIÓN ARQUITECTÓNICA:
-- El Vendor Lock-in en bases de datos no ocurre en las tablas planas ANSI SQL,
-- sino en la lógica procedural y de seguridad acoplada al motor:
-- 1. En MariaDB (licoreriadatabase): Tenemos 33 rutinas (28 procedimientos +
--    5 funciones) en dialecto SQL/PSM de MariaDB (DELIMITER //, SIGNAL SQLSTATE,
--    variables de sesión @auditoria_usuario) y 130 triggers (TRG_AUD_*, etc.).
-- 2. Al migrar a nuestro DBaaS Supabase PostgreSQL (ver API/migrations/*_postgresql.sql):
--    Tuvimos que reescribir la lógica de negocio a PL/pgSQL (RETURNS trigger
--    LANGUAGE plpgsql AS $$), reemplazar variables @auditoria_usuario por
--    current_setting('app.auditoria_usuario', true), e implementar políticas
--    RLS (Row-Level Security) propias de PostgreSQL/Supabase.

-- 7.2.A: Resumen cuantitativo de objetos con Vendor Lock-in en nuestro MariaDB
SELECT 'PROCEDIMIENTOS ALMACENADOS (SQL/PSM MariaDB)' AS categoria_objeto,
       COUNT(*)                                       AS total_objetos,
       'Alto (DELIMITER, SIGNAL SQLSTATE, @vars -> PL/pgSQL)' AS nivel_vendor_lock_in
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'licoreriadatabase' AND ROUTINE_TYPE = 'PROCEDURE'
UNION ALL
SELECT 'FUNCIONES ALMACENADAS (SQL/PSM MariaDB)',
       COUNT(*),
       'Alto (Reescritura obligatoria a funciones PL/pgSQL)'
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'licoreriadatabase' AND ROUTINE_TYPE = 'FUNCTION'
UNION ALL
SELECT 'TRIGGERS DE AUDITORÍA Y NEGOCIO (TRG_*)',
       COUNT(*),
       'Crítico (En PG un trigger exige FUNCTION + CREATE TRIGGER separado)'
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'licoreriadatabase'
UNION ALL
SELECT 'VISTAS DEL ESQUEMA (VW_*)',
       COUNT(*),
       'Medio (Funciones de fecha/texto y collations utf8mb4 vs UTF-8)'
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = 'licoreriadatabase';

-- 7.2.B: Muestra de rutinas y triggers acoplados al dialecto MariaDB vs Migraciones PG
SELECT ROUTINE_TYPE          AS tipo,
       ROUTINE_NAME          AS nombre_objeto_mariadb,
       DATA_TYPE             AS retorno,
       SECURITY_TYPE         AS modelo_seguridad,
       'Requiere reescritura a PL/pgSQL + RLS en API/migrations/*_postgresql.sql' AS impacto_migracion_dbaas
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = 'licoreriadatabase'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME
LIMIT 12;

SELECT TRIGGER_NAME          AS nombre_trigger,
       ACTION_TIMING         AS momento,
       EVENT_MANIPULATION    AS evento,
       EVENT_OBJECT_TABLE    AS tabla_objetivo,
       'Usa @auditoria_usuario / SIGNAL SQLSTATE (exclusivo MariaDB/MySQL)' AS dependencia_motor
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = 'licoreriadatabase'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME
LIMIT 12;


-- =====================================================================
--  BLOQUE 7.3: Mapa de Capas Cloud en Nuestro Proyecto (IaaS, DBaaS, PaaS, SaaS)
-- =====================================================================
-- Consulta resumen que mapea cada pieza real del repositorio Licorería La Cava:
SELECT '1. IaaS (Infrastructure as a Service)' AS modelo_cloud,
       'AWS EC2 / VPS / Servidor Local (:3307)' AS componente_proyecto,
       'API/.env (MARIADB_HOST=localhost:3307)' AS archivo_evidencia,
       'DBA administra SO, discos, mariadbd, my.ini, backups y red' AS control_y_responsabilidad,
       'Bajo en infraestructura, Alto en dialecto SQL/PSM (130 triggers y 33 rutinas)' AS vendor_lock_in
UNION ALL
SELECT '2. DBaaS (Database as a Service)',
       'Supabase PostgreSQL + Pooler Gestionado',
       'API/.env + API/prod-ca-2021.crt + API/postgres_connection.py',
       'Proveedor gestiona HA, TLS, backups y PgBouncer - DBA pierde rolsuper y SO',
       'Alto (PL/pgSQL, Row-Level Security RLS, pooler aws-0-us-east-1.pooler.supabase.com)'
UNION ALL
SELECT '3. PaaS (Platform as a Service)',
       'Render Blueprint (licoreria-api + licoreria-frontend)',
       'render.yaml (runtime: python / uvicorn + runtime: static / Vite)',
       'Render gestiona contenedores, build, SSL y healthCheckPath /readyz',
       'Medio (Especificación declarativa render.yaml y secretos /etc/secrets/)'
UNION ALL
SELECT '4. SaaS (Software as a Service)',
       'Sistema Web Licorería La Cava (POS, Inventario, Nómina, Contabilidad)',
       'frontend/src/App.jsx consumido vía navegador HTTPS',
       'Usuario final (cajero/contador/gerente) solo usa el navegador sin instalar nada',
       'Nulo para el usuario final, total dependencia de disponibilidad del proveedor';


-- =====================================================================
--  BLOQUE 7.4: Contraste de Seguridad IaaS vs. DBaaS (Política Zero-Trust en Cloud)
-- =====================================================================
-- En MariaDB local (IaaS) nos conectamos como root@localhost con todos los privilegios.
-- En Supabase (DBaaS), API/postgres_connection.py ejecuta _validate_database_role()
-- y aborta la conexión si detecta rolsuper, rolbypassrls, rolcreatedb o propiedad en public.
SELECT 'MariaDB Local (IaaS / Dev)'       AS entorno,
       'root@localhost'                   AS rol_conexion,
       'SUPER, GRANT OPTION, ALL ON *.*'  AS privilegios_activos,
       'TLS Opcional (Loopback local)'    AS cifrado_transporte,
       'Control total de máquina y motor' AS filosofia_control
UNION ALL
SELECT 'Supabase Cloud (DBaaS / Prod)',
       'licoreria_api_login (hereda licoreria_api_access)',
       'NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, RLS obligatorio en 43 tablas',
       'TLS Obligatorio (sslmode=verify-full + prod-ca-2021.crt)',
       'Mínimo privilegio estricto validado en API/postgres_connection.py';


-- #####################################################################
--  PREGUNTA 8 — TOPOLOGÍAS DE RED (BUS, MALLA, HIPERCUBO, ÁRBOL),
--               INTERCONEXIÓN FÍSICA (INFINIBAND / SAN), LATENCIA Y ANCHO DE BANDA
-- #####################################################################

-- =====================================================================
--  BLOQUE 8.1: Parámetros de Red y Paquetes en el Motor de BD
--              (Ancho de Banda de Canal, Buffers y Timeouts TCP)
-- =====================================================================
-- EXPLICACIÓN ARQUITECTÓNICA:
-- El motor de BD regula físicamente cómo empaqueta y transmite filas por la red:
-- * max_allowed_packet: Tamaño máximo de un paquete/fila o lote enviado por red.
-- * net_buffer_length: Tamaño inicial del buffer TCP entre motor y cliente.
-- * net_read_timeout / net_write_timeout: Tiempo límite antes de cortar un canal lento.
-- * skip_name_resolve: Evita latencia extra de DNS Lookup en cada handshake TCP.

SHOW VARIABLES WHERE Variable_name IN (
    'max_allowed_packet',
    'net_buffer_length',
    'net_read_timeout',
    'net_write_timeout',
    'connect_timeout',
    'skip_name_resolve',
    'bind_address',
    'port'
);


-- =====================================================================
--  BLOQUE 8.2: Tráfico de Red Real Acumulado en el Canal Cliente-Motor
--              (Bytes_received vs. Bytes_sent y Salud de Conexiones)
-- =====================================================================
-- EXPLICACIÓN ARQUITECTÓNICA:
-- * Bytes_received: Tráfico entrante (sentencias SQL enviadas desde FastAPI / HeidiSQL).
-- * Bytes_sent: Tráfico saliente (resultsets, filas y metadatos devueltos por MariaDB).
-- En sistemas OLTP/DWH, Bytes_sent suele ser de 5x a 50x mayor que Bytes_received.
-- Si el canal físico tiene bajo ancho de banda o se hacen SELECT * masivos,
-- Bytes_sent satura la interfaz de red y congela la aplicación cliente.

SELECT MAX(CASE WHEN VARIABLE_NAME = 'BYTES_RECEIVED' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END)          AS bytes_recibidos_sql,
       ROUND(MAX(CASE WHEN VARIABLE_NAME = 'BYTES_RECEIVED' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END) / 1024, 2) AS kb_recibidos_sql,
       MAX(CASE WHEN VARIABLE_NAME = 'BYTES_SENT' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END)              AS bytes_enviados_resultados,
       ROUND(MAX(CASE WHEN VARIABLE_NAME = 'BYTES_SENT' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END) / 1024 / 1024, 2) AS mb_enviados_resultados,
       ROUND(
           MAX(CASE WHEN VARIABLE_NAME = 'BYTES_SENT' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END) /
           NULLIF(MAX(CASE WHEN VARIABLE_NAME = 'BYTES_RECEIVED' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END), 0),
           2
       )                                                                                                  AS ratio_salida_vs_entrada,
       MAX(CASE WHEN VARIABLE_NAME = 'ABORTED_CONNECTS' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END)        AS conexiones_abortadas,
       MAX(CASE WHEN VARIABLE_NAME = 'ABORTED_CLIENTS' THEN CAST(VARIABLE_VALUE AS UNSIGNED) END)         AS clientes_abortados_timeout
FROM information_schema.GLOBAL_STATUS
WHERE VARIABLE_NAME IN ('BYTES_RECEIVED', 'BYTES_SENT', 'ABORTED_CONNECTS', 'ABORTED_CLIENTS');


-- =====================================================================
--  BLOQUE 8.3: Impacto del Ancho de Banda (Payload Size) en el Canal de Red
-- =====================================================================
-- EXPLICACIÓN ARQUITECTÓNICA:
-- Comparación entre dos diseños para alimentar un gráfico gerencial de ventas por región:
-- 1. Anti-patrón (Saturación de Ancho de Banda): Hacer SELECT * de hechos + dimensiones
--    (dwh_fact_ventas JOIN dwh_dim_producto JOIN dwh_dim_cliente JOIN dwh_dim_tiempo)
--    para transferir cientos o miles de filas anchas por el socket TCP y agrupar en Python/React.
-- 2. Patrón Optimizado (Proyección + Agregación en el Motor): El motor filtra y suma
--    internamente cerca del disco/RAM (SAN/Buffer Pool) y transmite solo 3-4 filas por la red.

-- 8.3.A: Medición cuantitativa del ahorro de Ancho de Banda (Bytes en el cable)
SELECT '1. Anti-Patrón: SELECT * (660 filas x 27 cols DWH hacia la API)' AS estrategia_consulta,
       COUNT(*)                                                          AS filas_transmitidas_por_red,
       SUM(
           LENGTH(CONCAT_WS('|',
               f.id_hecho, f.sk_tiempo, f.sk_producto, f.sk_cliente, f.id_factura_oltp,
               f.cantidad_vendida, f.precio_unitario, f.costo_unitario, f.ingreso_bruto,
               f.costo_total, f.margen_ganancia,
               p.id_producto_oltp, p.descripcion, p.categoria, p.marca, p.um_venta,
               c.id_cliente_oltp, c.nombre_cliente, c.tipo_cliente, c.ruc_ced, c.ciudad, c.provincia, c.region,
               t.fecha, t.anio, t.nombre_mes, t.dia_semana
           ))
       )                                                                 AS payload_estimado_bytes,
       'Desperdicia >99% del ancho de banda TCP serializando texto repetido' AS impacto_en_red
FROM dwh_fact_ventas f
JOIN dwh_dim_producto p ON p.sk_producto = f.sk_producto
JOIN dwh_dim_cliente  c ON c.sk_cliente  = f.sk_cliente
JOIN dwh_dim_tiempo   t ON t.sk_tiempo   = f.sk_tiempo
UNION ALL
SELECT '2. Optimizado: GROUP BY en Motor (Solo resumen regional hacia la API)',
       COUNT(*),
       SUM(LENGTH(CONCAT_WS('|', region, total_transacciones, unidades, ingresos_usd, margen_usd))),
       'Reducción >99% del tráfico de red: ideal para enlaces WAN / DBaaS'
FROM (
    SELECT c.region                          AS region,
           COUNT(*)                          AS total_transacciones,
           SUM(f.cantidad_vendida)           AS unidades,
           ROUND(SUM(f.ingreso_bruto), 2)    AS ingresos_usd,
           ROUND(SUM(f.margen_ganancia), 2)  AS margen_usd
    FROM dwh_fact_ventas f
    JOIN dwh_dim_cliente c ON c.sk_cliente = f.sk_cliente
    GROUP BY c.region
) resumen_optimizado;

-- 8.3.B: Resultado real de la consulta optimizada (solo estas filas viajan a FastAPI/React)
SELECT c.region                          AS region_geografica,
       COUNT(*)                          AS hechos_procesados_en_motor,
       SUM(f.cantidad_vendida)           AS botellas_vendidas,
       ROUND(SUM(f.ingreso_bruto), 2)    AS ingresos_brutos_usd,
       ROUND(SUM(f.margen_ganancia), 2)  AS margen_neto_usd
FROM dwh_fact_ventas f
JOIN dwh_dim_cliente c ON c.sk_cliente = f.sk_cliente
GROUP BY c.region
ORDER BY ingresos_brutos_usd DESC;


-- =====================================================================
--  BLOQUE 8.4: El Problema N+1 y el Efecto Multiplicador de la Latencia (RTT)
-- =====================================================================
-- EXPLICACIÓN ARQUITECTÓNICA:
-- Para mostrar en React las 40 facturas con sus líneas de detalle (160 filas en proxfac):
-- * Si el backend ejecuta el patrón N+1:
--   - 1 consulta para traer las 40 cabeceras de `facturas`
--   - + 40 consultas individuales (`SELECT * FROM proxfac WHERE id_Factura = ?`)
--   = 41 Round-Trips (viajes de ida y vuelta por la red).
-- * En Infiniband/RDMA (RTT ~ 0.002 ms): 41 * 0.002 ms = 0.08 ms (invisible).
-- * En Localhost / LAN (RTT ~ 0.3 ms):   41 * 0.3 ms   = 12.3 ms (parece rápido en desarrollo).
-- * En WAN hacia DBaaS Supabase us-east-1 Virginia desde Ecuador (RTT ~ 85 ms):
--   41 * 85 ms = 3,485 ms (3.5 SEGUNDOS solo esperando paquetes en el cable submarino).
-- * Con 1 solo JOIN (1 Round-Trip): 1 * 85 ms = 85 ms (41x más rápido en la nube).

-- 8.4.A: Consulta Única Optimizada (1 Solo Round-Trip de Red: Facturas + Detalles + Producto)
SELECT f.id_Factura,
       f.fac_Fecha,
       f.id_Cliente,
       f.fac_Total,
       f.ESTADO_FAC,
       pf.id_Producto,
       p.pro_Descripcion,
       pf.pxf_Cantidad,
       pf.pxf_Precio,
       pf.pxf_Subtotal
FROM facturas f
JOIN proxfac   pf ON pf.id_Factura  = f.id_Factura
JOIN productos p  ON p.id_Producto  = pf.id_Producto
ORDER BY f.id_Factura, pf.id_Producto
LIMIT 25;

-- 8.4.B: Matriz de Simulación de Tiempo de Respuesta (40 Facturas: N+1 vs. 1 JOIN)
SELECT interconexion.medio_fisico_y_topologia,
       interconexion.rtt_ms                                     AS latencia_rtt_ms,
       interconexion.ancho_banda_gbps                           AS ancho_banda,
       ROUND(1  * interconexion.rtt_ms + 1.5, 2)                AS tiempo_1_join_ms,
       ROUND(41 * interconexion.rtt_ms + 4.5, 2)                AS tiempo_n_mas_1_41_queries_ms,
       CASE
           WHEN (41 * interconexion.rtt_ms + 4.5) < 100  THEN 'Instantáneo (<100 ms): UX fluida'
           WHEN (41 * interconexion.rtt_ms + 4.5) < 1000 THEN 'Perceptible (100-1000 ms): UX degradada'
           ELSE 'CRÍTICO (>3.4 seg): Spinner lento en React / Timeout percibido'
       END                                                      AS impacto_experiencia_usuario_ux
FROM (
    SELECT '1. Infiniband HDR / RDMA (Clúster BD Paralela / Hipercubo)' AS medio_fisico_y_topologia,
           0.002 AS rtt_ms, '200 Gbps' AS ancho_banda_gbps
    UNION ALL
    SELECT '2. SAN Fibre Channel / NVMe-oF (Almacenamiento Shared-Disk)',
           0.050 AS rtt_ms, '32-64 Gbps' AS ancho_banda_gbps
    UNION ALL
    SELECT '3. Loopback Localhost (:3307 en la misma máquina de desarrollo)',
           0.300 AS rtt_ms, '40+ Gbps (Memoria IPC)' AS ancho_banda_gbps
    UNION ALL
    SELECT '4. LAN Ethernet Gigabit (Servidor BD On-Premise en Licorería)',
           0.500 AS rtt_ms, '1 - 10 Gbps' AS ancho_banda_gbps
    UNION ALL
    SELECT '5. WAN Internet Ecuador -> DBaaS Supabase (aws-0-us-east-1 Virginia)',
           85.000 AS rtt_ms, '0.05 - 0.1 Gbps (50-100 Mbps)' AS ancho_banda_gbps
) AS interconexion;
