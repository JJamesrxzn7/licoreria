-- =====================================================================
--  PRÁCTICA ARQUITECTURA - PREGUNTAS 1 y 2
--  Proyecto: Licorería La Cava  |  BD: licoreriadatabase (MariaDB :3307)
--  Ejecutar en HeidiSQL bloque por bloque (seleccionar + F9 / Ctrl+F9)
-- =====================================================================
USE licoreriadatabase;

-- #####################################################################
--  PREGUNTA 1  -  CAPA DEL DBA  (lo que decide el DBA dentro del motor)
-- #####################################################################

-- 1.1  Diseño FÍSICO: motor de almacenamiento, filas y tamaño de cada tabla
SELECT TABLE_NAME                                   AS tabla,
       ENGINE                                       AS motor,
       TABLE_ROWS                                   AS filas_aprox,
       ROUND(DATA_LENGTH  / 1024, 1)                AS datos_kb,
       ROUND(INDEX_LENGTH / 1024, 1)                AS indices_kb,
       TABLE_COLLATION                              AS collation
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'licoreriadatabase'
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC;

-- 1.2  Diseño LÓGICO: integridad referencial (FK) que solo controla el DBA
SELECT TABLE_NAME            AS tabla_hija,
       COLUMN_NAME           AS columna,
       REFERENCED_TABLE_NAME AS tabla_padre,
       REFERENCED_COLUMN_NAME AS columna_padre,
       CONSTRAINT_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'licoreriadatabase'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY tabla_hija;

-- 1.3  Índices (decisión de rendimiento del DBA)
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,
       GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columnas
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'licoreriadatabase'
GROUP BY TABLE_NAME, INDEX_NAME, NON_UNIQUE
ORDER BY TABLE_NAME;

-- 1.4  Objetos programados en el motor (triggers, procedimientos, vistas)
SELECT 'TRIGGER' AS tipo, TRIGGER_NAME AS nombre, EVENT_OBJECT_TABLE AS sobre
FROM information_schema.TRIGGERS  WHERE TRIGGER_SCHEMA = 'licoreriadatabase'
UNION ALL
SELECT ROUTINE_TYPE, ROUTINE_NAME, NULL
FROM information_schema.ROUTINES  WHERE ROUTINE_SCHEMA = 'licoreriadatabase'
UNION ALL
SELECT 'VIEW', TABLE_NAME, NULL
FROM information_schema.VIEWS     WHERE TABLE_SCHEMA = 'licoreriadatabase';

-- 1.5  Infraestructura que configura el DBA (memoria, logs, durabilidad)
SHOW VARIABLES WHERE Variable_name IN (
  'version', 'datadir', 'port', 'default_storage_engine',
  'innodb_buffer_pool_size', 'innodb_log_file_size',
  'innodb_flush_log_at_trx_commit', 'max_connections',
  'transaction_isolation', 'tx_isolation', 'log_bin', 'slow_query_log',
  'long_query_time');

-- 1.6  MÉTRICAS CLAVE DEL DBA (salud del motor)
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM information_schema.GLOBAL_STATUS
WHERE VARIABLE_NAME IN ('UPTIME','QUESTIONS','THREADS_CONNECTED',
      'MAX_USED_CONNECTIONS','SLOW_QUERIES','COM_COMMIT','COM_ROLLBACK',
      'INNODB_ROW_LOCK_WAITS','INNODB_DEADLOCKS',
      'INNODB_BUFFER_POOL_READ_REQUESTS','INNODB_BUFFER_POOL_READS');

-- Hit ratio del buffer pool (%)  -> meta del DBA: > 99 %
SELECT ROUND(100 * (1 - r.v / NULLIF(q.v,0)), 2) AS buffer_pool_hit_ratio_pct,
       ROUND(qs.v / NULLIF(u.v,0), 2)            AS consultas_por_segundo_QPS
FROM (SELECT VARIABLE_VALUE v FROM information_schema.GLOBAL_STATUS WHERE VARIABLE_NAME='INNODB_BUFFER_POOL_READS') r,
     (SELECT VARIABLE_VALUE v FROM information_schema.GLOBAL_STATUS WHERE VARIABLE_NAME='INNODB_BUFFER_POOL_READ_REQUESTS') q,
     (SELECT VARIABLE_VALUE v FROM information_schema.GLOBAL_STATUS WHERE VARIABLE_NAME='QUESTIONS') qs,
     (SELECT VARIABLE_VALUE v FROM information_schema.GLOBAL_STATUS WHERE VARIABLE_NAME='UPTIME') u;

-- 1.7  SEGURIDAD: principio de mínimo privilegio (decisión del DBA)
--      El DBA crea un usuario EXCLUSIVO para la API (no root).
CREATE USER IF NOT EXISTS 'app_licoreria'@'localhost' IDENTIFIED BY 'App.Licoreria2026';
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE
      ON licoreriadatabase.* TO 'app_licoreria'@'localhost';
FLUSH PRIVILEGES;
SHOW GRANTS FOR 'app_licoreria'@'localhost';
--  DEMO: conectarse en HeidiSQL con app_licoreria y probar:
--      DROP TABLE cualquier_tabla;   -> ERROR 1142 (denegado: DDL es del DBA)
--      CREATE TABLE x (id INT);      -> ERROR 1142

-- 1.8  Plan de ejecución (optimización: tarea del DBA, invisible al usuario)
--      Compara una búsqueda usando índice (key = PRIMARY / IDX_PRODUCTOS_CATEGORIA) vs full scan
EXPLAIN SELECT * FROM productos WHERE id_Producto = 'PRD-000001';
EXPLAIN SELECT * FROM productos WHERE id_Categoria = 'CAT-001';


-- #####################################################################
--  PREGUNTA 2  -  CLIENTE-SERVIDOR  ≠  ARQUITECTURA INTERNA DEL DBMS
-- #####################################################################

-- 2.1  Ver los CLIENTES conectados al servidor de BD.
--      Con la API (uvicorn) corriendo y el frontend abierto, ejecutar:
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, LEFT(INFO,60) AS consulta
FROM information_schema.PROCESSLIST
ORDER BY ID;
--  Se verá: la sesión de HeidiSQL (cliente 2 capas) y la(s) sesión(es) de la
--  API FastAPI (cliente del motor en arquitectura 3 capas). El NAVEGADOR
--  NUNCA aparece aquí: no habla con la BD, habla con la API por HTTP.
--  => Cliente-Servidor describe QUIÉN se conecta a QUIÉN (despliegue lógico).

-- 2.2  Arquitectura FÍSICA interna del servidor: UN solo proceso mariadbd,
--      hilos que comparten la MISMA memoria (buffer pool) y el MISMO disco
--      (datadir) => equivale a SHARED MEMORY / shared-everything (SMP).
SHOW VARIABLES WHERE Variable_name IN
  ('datadir','innodb_buffer_pool_size','thread_handling',
   'innodb_read_io_threads','innodb_write_io_threads','thread_pool_size');

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM information_schema.GLOBAL_STATUS
WHERE VARIABLE_NAME IN ('THREADS_CONNECTED','THREADS_RUNNING','THREADS_CREATED');

-- 2.3  Prueba: dos clientes distintos comparten el mismo buffer pool.
--      Ejecute la misma consulta desde HeidiSQL y desde la app; observe que
--      INNODB_BUFFER_POOL_READS (lecturas a disco) casi no sube la 2da vez:
--      la página ya está en la memoria COMPARTIDA del servidor.
SELECT VARIABLE_VALUE AS lecturas_fisicas_disco
FROM information_schema.GLOBAL_STATUS
WHERE VARIABLE_NAME = 'INNODB_BUFFER_POOL_READS';
