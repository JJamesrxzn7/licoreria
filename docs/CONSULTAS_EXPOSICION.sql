-- =====================================================================================
-- CONSULTAS PARA LA EXPOSICIÓN (pegar en HeidiSQL, en la sesión indicada)
-- Las 3 sedes tienen el MISMO ERP (el sistema transaccional completo de "La Cava"):
--   "1 - BD1 Quito ERP"      PC de Escritorio · MariaDB  :3307 · lacava_quito
--   "4 - BD4 Guayaquil ERP"  Laptop           · MariaDB  :3307 · licoreriadatabase (el ERP original)
--   "6 - BD6 Cuenca ERP"     Laptop           · PostgreSQL 18 :5432 · lacava_cuenca
-- Bases de apoyo: "3 - BD3 Quito Particionada" (:3308) y "5 - BD5 Guayaquil DWH" (:3309).
-- BD 2 (MongoDB) se muestra en la app: Terminal DBA -> BD 2.
-- La contraseña se pide al conectar (root / postgres: las de API/.env).
-- Las consultas de las secciones A, B y C valen en las TRES sesiones ERP (MariaDB y PostgreSQL).
-- =====================================================================================


-- =====================================================================================
-- A. EL ERP DE CADA SEDE (correr en las sesiones 1, 4 y 6)
-- =====================================================================================
-- A.1 Ventas de la sede (las hacen los cajeros en el POS y los agentes 1, 4 y 6 con la app)
SELECT f.id_factura, c.cli_nombre AS cliente, f.fac_fecha, f.fac_subtotal, f.fac_iva, f.fac_total, f.estado_fac
FROM facturas f LEFT JOIN clientes c ON c.id_cliente = f.id_cliente ORDER BY f.fac_fecha DESC LIMIT 15;

-- A.2 Detalle de una venta y su entrega en bodega (cambiar el id por uno de A.1)
SELECT d.id_factura, d.id_producto, p.pro_descripcion, d.pxf_cantidad, d.pxf_precio, d.pxf_subtotal
FROM proxfac d JOIN productos p ON p.id_producto = d.id_producto ORDER BY d.id_factura DESC LIMIT 15;
SELECT id_entrega, id_factura, ent_fechahora, estado_ent FROM entregas ORDER BY ent_fechahora DESC LIMIT 10;

-- A.3 Compras aprobadas -> recepciones en bodega
SELECT id_recibo, id_compra, rec_fechahora, estado_rec FROM recepciones ORDER BY rec_fechahora DESC LIMIT 10;

-- A.4 Bitácora del agente de la sede: qué documento tocó (en Cuenca la tabla es operaciones_agentes_cloud)
SELECT id_op, fecha_hora, agente_nombre, usuario_rbac, modulo, tabla_ref, documento_ref, operacion
FROM operaciones_agentes_ia ORDER BY id_op DESC LIMIT 15;
--     En Cuenca (sesión 6):
SELECT id_op, fecha_hora, agente_nombre, usuario_rbac, modulo, tabla_ref, documento_ref, latencia_wan_ms, operacion
FROM operaciones_agentes_cloud ORDER BY id_op DESC LIMIT 15;

-- A.5 Los 5 módulos del ERP
SELECT 'Compras' AS modulo, COUNT(*) FROM compras UNION ALL SELECT 'Productos', COUNT(*) FROM productos
UNION ALL SELECT 'Recepciones', COUNT(*) FROM recepciones UNION ALL SELECT 'Entregas', COUNT(*) FROM entregas
UNION ALL SELECT 'Facturas', COUNT(*) FROM facturas UNION ALL SELECT 'Empleados', COUNT(*) FROM empleados
UNION ALL SELECT 'Asientos', COUNT(*) FROM asientos;


-- =====================================================================================
-- B. AUDITORÍA TOTAL: TODA acción queda en LOG_AUDITORIA (sesiones 1, 4 y 6)
-- =====================================================================================
-- B.1 Últimos cambios: log_seq es el orden del cambio (como la posición de un binlog), log_sede la sede
SELECT log_seq, log_fechahora, id_usuario, log_tablaafectada, log_accion, log_sede, log_ip
FROM log_auditoria ORDER BY log_seq DESC LIMIT 20;

-- B.2 Quién hizo qué
SELECT COALESCE(id_usuario, '(sin usuario)') AS usuario, log_tablaafectada, log_accion, COUNT(*) AS acciones
FROM log_auditoria GROUP BY id_usuario, log_tablaafectada, log_accion ORDER BY acciones DESC LIMIT 30;

-- B.3 La historia completa de UN documento (pegar un id de factura de A.1): venta, entrega, despacho...
SELECT log_seq, log_fechahora, id_usuario, log_tablaafectada, log_accion, log_valoranterior, log_valornuevo
FROM log_auditoria WHERE log_valornuevo LIKE '%FAC_PEGAR_ID%' OR log_valoranterior LIKE '%FAC_PEGAR_ID%' ORDER BY log_seq;

-- B.4 (MariaDB: sesiones 1 y 4) Cuántas tablas están auditadas: 3 triggers TRG_AUD_* por tabla
SELECT EVENT_OBJECT_TABLE, COUNT(*) AS triggers FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME LIKE 'TRG\_AUD\_%' GROUP BY EVENT_OBJECT_TABLE ORDER BY 1;
-- B.4 (PostgreSQL: sesión 6) el mismo trigger genérico fn_trg_auditoria_general en cada tabla
SELECT event_object_table, COUNT(*) FROM information_schema.triggers WHERE action_statement LIKE '%fn_trg_auditoria_general%'
GROUP BY event_object_table ORDER BY 1;


-- =====================================================================================
-- C. REPLICACIÓN EN ANILLO (log shipping): Quito -> Guayaquil -> Cuenca -> Quito
--    Cada sede guarda el LOG_AUDITORIA de la anterior, con su etiqueta "RÉPLICA de <sede>".
-- =====================================================================================
-- C.1 En la sesión 4 (Guayaquil): la RÉPLICA de Quito  ← LA RECOMENDADA PARA MOSTRAR
SELECT etiqueta_replica, log_seq_origen, fecha_origen, replicado_en, id_usuario, tabla, accion, LEFT(valor_nuevo, 120) AS valor_nuevo
FROM replica_quito_log ORDER BY log_seq_origen DESC LIMIT 15;
--     Comparar con el origen: en la sesión 1 (Quito), SELECT MAX(log_seq) FROM log_auditoria;
SELECT COUNT(*) AS cambios_replicados, MAX(log_seq_origen) AS marca_de_agua FROM replica_quito_log;

-- C.2 En la sesión 6 (Cuenca): la RÉPLICA de Guayaquil
SELECT etiqueta_replica, log_seq_origen, fecha_origen, replicado_en, id_usuario, tabla, accion FROM replica_guayaquil_log
ORDER BY log_seq_origen DESC LIMIT 15;

-- C.3 En la sesión 1 (Quito): la RÉPLICA de Cuenca (cierra el anillo)
SELECT etiqueta_replica, log_seq_origen, fecha_origen, replicado_en, id_usuario, tabla, accion FROM replica_cuenca_log
ORDER BY log_seq_origen DESC LIMIT 15;

-- C.4 DR: si Quito se cae, sus facturas siguen en Guayaquil (sesión 4): cada INSERT/UPDATE de FACTURAS replicado
SELECT log_seq_origen, accion, JSON_VALUE(valor_nuevo, '$.id_Factura') AS factura, JSON_VALUE(valor_nuevo, '$.fac_Total') AS total,
       JSON_VALUE(valor_nuevo, '$.ESTADO_FAC') AS estado FROM replica_quito_log WHERE tabla = 'FACTURAS' ORDER BY log_seq_origen DESC LIMIT 10;

-- C.5 La replicación también se audita: cada corrida queda en el log de la BD que recibe la copia
SELECT log_fechahora, id_usuario, log_tablaafectada, log_valornuevo FROM log_auditoria
WHERE log_tablaafectada LIKE 'REPLICA%' ORDER BY log_seq DESC LIMIT 5;


-- =====================================================================================
-- D. 2PC sobre los ERP (después de correr el 2PC en la app, pestaña Arquitectura)
-- =====================================================================================
-- D.1 El traslado quedó en la bitácora de las 3 sedes con el mismo id de transacción (documento_ref = 2PC-...)
SELECT id_op, fecha_hora, usuario_rbac, operacion, documento_ref FROM operaciones_agentes_ia
WHERE agente_nombre = 'Coordinador-2PC' ORDER BY id_op DESC LIMIT 10;
--     En Cuenca (sesión 6):
SELECT id_op, fecha_hora, usuario_rbac, operacion, documento_ref FROM operaciones_agentes_cloud
WHERE agente_nombre = 'Coordinador-2PC' ORDER BY id_op DESC LIMIT 10;
-- D.2 Y el cambio de stock en el log (ajuste en PRODUCTOS hecho por i_jefe)
SELECT log_seq, log_fechahora, id_usuario, log_accion, log_valoranterior, log_valornuevo FROM log_auditoria
WHERE log_tablaafectada = 'PRODUCTOS' ORDER BY log_seq DESC LIMIT 6;
-- D.3 (MariaDB) transacciones XA que quedaron preparadas sin decisión (debe salir vacío)
XA RECOVER;


-- =====================================================================================
-- SESIÓN "3 - BD3 Quito Particionada"  (PC de Escritorio, MariaDB :3308, quito_paralela_db)
-- =====================================================================================
SHOW CREATE TABLE historico_transacciones;
SELECT PARTITION_NAME, PARTITION_METHOD, PARTITION_EXPRESSION, TABLE_ROWS
FROM information_schema.PARTITIONS WHERE TABLE_SCHEMA = 'quito_paralela_db' AND TABLE_NAME = 'historico_transacciones';
SELECT particion_hash, COUNT(*) AS filas, SUM(monto_usd) AS monto FROM historico_transacciones GROUP BY particion_hash ORDER BY particion_hash;
-- PODA de particiones: una búsqueda por id lee UNA sola partición (columna "partitions"); sin filtro lee las 4
EXPLAIN PARTITIONS SELECT * FROM historico_transacciones WHERE id = 42;
EXPLAIN PARTITIONS SELECT COUNT(*) FROM historico_transacciones;


-- =====================================================================================
-- SESIÓN "5 - BD5 Guayaquil DWH estrella"  (Laptop, MariaDB :3309, db_gye_dwh)
-- =====================================================================================
-- 5.1 Hechos que vienen de las ventas REALES de los 3 ERP (fuente_dato = 'ERP', con su factura de origen)
SELECT f.id_fact, s.nombre_sede, f.id_factura, p.nombre_producto, p.categoria, t.nombre_mes, f.cantidad_botellas,
       f.total_venta_usd, f.usuario_rbac, f.etl_lote
FROM fact_ventas f JOIN dim_sede s ON s.id_sede = f.id_sede JOIN dim_producto p ON p.id_producto = f.id_producto
JOIN dim_tiempo t ON t.id_tiempo = f.id_tiempo WHERE f.fuente_dato = 'ERP' ORDER BY f.id_fact DESC LIMIT 15;

-- 5.2 Consulta OLAP: ventas por sede y categoría
SELECT s.nombre_sede, p.categoria, SUM(f.cantidad_botellas) AS botellas, ROUND(SUM(f.total_venta_usd), 2) AS ventas
FROM fact_ventas f JOIN dim_sede s ON s.id_sede = f.id_sede JOIN dim_producto p ON p.id_producto = f.id_producto
WHERE f.fuente_dato = 'ERP' GROUP BY s.nombre_sede, p.categoria ORDER BY ventas DESC;

-- 5.3 ETL incremental por CDC: marca de agua = log_seq del LOG_AUDITORIA de cada ERP
SELECT * FROM etl_control WHERE fuente LIKE '%\_ERP';
SELECT * FROM etl_corridas ORDER BY id DESC LIMIT 10;


-- =====================================================================================
-- SESIÓN 6 (Cuenca, PostgreSQL) — lo propio del motor
-- OJO: es un PostgreSQL 18 LOCAL en la Laptop (el proyecto de Supabase original ya no existe).
-- =====================================================================================
SELECT version(), current_database(), inet_server_port();
SHOW max_parallel_workers_per_gather;
SHOW min_parallel_table_scan_size;
SHOW max_prepared_transactions;   -- 0 = el 2PC nativo (PREPARE TRANSACTION) está desactivado en este servidor
EXPLAIN SELECT log_tablaafectada, COUNT(*) FROM log_auditoria GROUP BY log_tablaafectada;
