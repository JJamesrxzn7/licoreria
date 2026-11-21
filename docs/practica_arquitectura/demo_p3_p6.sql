-- =====================================================================
--  PRÁCTICA ARQUITECTURA - PREGUNTAS 3 y 6
--  Proyecto: Licorería La Cava  |  BD: licoreriadatabase (MariaDB :3307)
--  Ejecutar en HeidiSQL bloque por bloque (seleccionar + F9 / Ctrl+F9)
-- =====================================================================
USE licoreriadatabase;

-- #####################################################################
--  PREGUNTA 3  -  MECANISMOS DE ESCALABILIDAD:
--                 PARTICIONAMIENTO FÍSICO EN BD (RANGO, HASH, ROTATIVO),
--                 SPEED-UP, SCALE-UP vs. SCALE-OUT EN LA CAPA DE APP (SI)
-- #####################################################################

-- 3.1  Inspeccionar cómo el motor MariaDB repartió físicamente las 10,000
--      transacciones en las 3 estrategias de particionamiento:
--      1) demo_ventas_rango    -> PARTITION BY RANGE (YEAR(fecha_venta))
--      2) demo_ventas_hash     -> PARTITION BY HASH (id_sucursal_num) PARTITIONS 4
--      3) demo_ventas_rotativo -> PARTITION BY HASH (id_transaccion)  PARTITIONS 4 (Round-Robin)
SELECT TABLE_NAME           AS tabla_particionada,
       PARTITION_NAME       AS particion_fisica,
       PARTITION_METHOD     AS mecanismo,
       PARTITION_EXPRESSION AS clave_particion,
       PARTITION_DESCRIPTION AS limite_rango,
       TABLE_ROWS           AS filas_en_particion,
       ROUND(DATA_LENGTH / 1024, 1) AS datos_kb
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = 'licoreriadatabase'
  AND TABLE_NAME LIKE 'demo_ventas_%'
ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION;

-- 3.2  DEMOSTRACIÓN 1: PARTICIONAMIENTO POR RANGO (Range Partitioning)
--      Observa la columna "partitions" en el resultado de EXPLAIN PARTITIONS:
--      Al filtrar por el año 2025, el optimizador aplica PARTITION PRUNING
--      (poda de particiones) y SOLO lee en disco la partición física [p_2025]
--      (4,000 filas), ignorando por completo p_2024, p_2026 y p_futuro.
EXPLAIN PARTITIONS
SELECT ciudad,
       COUNT(*)         AS num_transacciones,
       SUM(cantidad)    AS botellas_vendidas,
       SUM(total_venta) AS ingresos_2025
FROM demo_ventas_rango
WHERE fecha_venta BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY ciudad
ORDER BY ingresos_2025 DESC;

-- Ejecución real sobre la partición p_2025:
SELECT ciudad,
       COUNT(*)         AS num_transacciones,
       SUM(cantidad)    AS botellas_vendidas,
       SUM(total_venta) AS ingresos_2025
FROM demo_ventas_rango
WHERE fecha_venta BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY ciudad
ORDER BY ingresos_2025 DESC;

-- 3.3  DEMOSTRACIÓN 2: PARTICIONAMIENTO POR ASOCIACIÓN / HASH (Hash Partitioning)
--      El motor aplica una función hash determinística sobre `id_sucursal_num`.
--      Al consultar la Sucursal #2 (Costa: Guayaquil/Machala), MariaDB calcula
--      (2 MOD 4 = 2) y lee ÚNICAMENTE la partición física [p2] (2,500 filas).
EXPLAIN PARTITIONS
SELECT ciudad,
       id_producto,
       COUNT(*)         AS ventas,
       SUM(total_venta) AS total_sucursal_2
FROM demo_ventas_hash
WHERE id_sucursal_num = 2
GROUP BY ciudad, id_producto
ORDER BY total_sucursal_2 DESC
LIMIT 10;

-- 3.4  DEMOSTRACIÓN 3: PARTICIONAMIENTO EN TURNO ROTATIVO (Round-Robin)
--      Al aplicar HASH sobre una clave secuencial monótona (`id_transaccion` = 1, 2, 3...),
--      la tupla i se asigna a la partición (i MOD 4).
--      Resultado: balanceo de carga matemático exacto -> 2,500 filas exactas en p0, p1, p2 y p3.
--      Observa que para una búsqueda puntual por ID (#2501 -> 2501 MOD 4 = 1), lee solo [p1],
--      pero para un rango de fechas debe escanear las 4 particiones [p0,p1,p2,p3]:
EXPLAIN PARTITIONS
SELECT * FROM demo_ventas_rotativo WHERE id_transaccion = 2501;

EXPLAIN PARTITIONS
SELECT ciudad, SUM(total_venta)
FROM demo_ventas_rotativo
WHERE fecha_venta BETWEEN '2025-06-01' AND '2025-06-30'
GROUP BY ciudad;

-- 3.5  CONTRASTE CON SCALE-OUT EN LA CAPA DE APLICACIONES (SI)
--      Cuando levantamos múltiples instancias de la API FastAPI (:8000, :8001) o
--      ejecutamos el benchmark concurrente (`benchmark_p3_escalabilidad.py`),
--      todas las conexiones paralelas se ven aquí compartiendo el mismo motor:
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, LEFT(INFO, 65) AS consulta_activa
FROM information_schema.PROCESSLIST
WHERE DB = 'licoreriadatabase'
ORDER BY ID;


-- #####################################################################
--  PREGUNTA 6  -  BASE DE DATOS OPERACIONAL (OLTP - 3FN)
--                 vs. DATA WAREHOUSE (OLAP - ESQUEMA EN ESTRELLA) + ETL
-- #####################################################################

-- 6.1  CONSULTA OPERACIONAL OLTP (3ra Forma Normal - 3FN)
--      Características:
--      * Orientada a la operación diaria (facturación en caja, control de stock).
--      * Alta normalización para evitar redundancia y anomalías de actualización:
--        para ver una factura completa hay que hacer JOIN de 6 tablas normalizadas
--        (FACTURAS -> CLIENTES -> CIUDADES -> PROXFAC -> PRODUCTOS -> CATEGORIAS -> MARCAS).
SELECT f.id_Factura,
       f.fac_Fecha,
       f.ESTADO_FAC,
       c.cli_Nombre          AS cliente,
       ci.ciu_Descripcion    AS ciudad,
       ci.ciu_Region         AS region,
       p.pro_Descripcion     AS producto,
       cat.cat_Nombre        AS categoria,
       m.mar_Nombre          AS marca,
       pf.pxf_Cantidad       AS cantidad,
       pf.pxf_Precio         AS precio_unit,
       pf.pxf_Subtotal       AS subtotal_linea
FROM facturas f
INNER JOIN clientes c     ON f.id_Cliente    = c.id_Cliente
INNER JOIN ciudades ci    ON c.id_Ciudad     = ci.id_Ciudad
INNER JOIN proxfac pf     ON f.id_Factura    = pf.id_Factura
INNER JOIN productos p    ON pf.id_Producto  = p.id_Producto
INNER JOIN categorias cat ON p.id_Categoria  = cat.id_Categoria
INNER JOIN marcas m       ON p.id_Marca      = m.id_Marca
WHERE f.id_Factura IN ('FAC-000001', 'FAC-000002', 'FAC-000003')
ORDER BY f.id_Factura, p.id_Producto;

-- 6.2  EJECUCIÓN DEL PROCESO ETL (Extract - Transform - Load)
--      El procedimiento almacenado `SP_ETL_CARGAR_DWH_VENTAS()`:
--      1) EXTRAER: Lee de las tablas operacionales OLTP (`FACTURAS`, `PROXFAC`,
--         `PRODUCTOS`, `CATEGORIAS`, `MARCAS`, `CLIENTES`, `CIUDADES`).
--      2) TRANSFORMAR: Limpia cadenas (`TRIM`), desnormaliza `CATEGORIAS` y `MARCAS`
--         dentro de `dwh_dim_producto`, desnormaliza `CIUDADES` dentro de `dwh_dim_cliente`,
--         clasifica clientes en Jurídicos (`JUR`, RUC 13 dígitos) vs Naturales (`NAT`, Cédula 10 dígitos),
--         desglosa fechas en Año/Trimestre/Mes/DíaSemana y calcula Costo Total y Margen de Ganancia.
--      3) CARGAR: Pobla las 3 Dimensiones y la Tabla de Hechos Central (`dwh_fact_ventas`).
CALL SP_ETL_CARGAR_DWH_VENTAS();

-- Verificar el Esquema en Estrella cargado (1 Tabla de Hechos + 3 Dimensiones):
SELECT 'dwh_dim_tiempo'   AS tabla_dwh, 'DIMENSIÓN CALENDARIO'           AS rol_estrella, COUNT(*) AS total_filas FROM dwh_dim_tiempo
UNION ALL
SELECT 'dwh_dim_producto' AS tabla_dwh, 'DIMENSIÓN PRODUCTO (3FN->1FN)'  AS rol_estrella, COUNT(*) AS total_filas FROM dwh_dim_producto
UNION ALL
SELECT 'dwh_dim_cliente'  AS tabla_dwh, 'DIMENSIÓN CLIENTE/GEOGRAFÍA'    AS rol_estrella, COUNT(*) AS total_filas FROM dwh_dim_cliente
UNION ALL
SELECT 'dwh_fact_ventas'  AS tabla_dwh, 'TABLA DE HECHOS CENTRAL (FACT)' AS rol_estrella, COUNT(*) AS total_filas FROM dwh_fact_ventas;

-- 6.3  Inspeccionar las Dimensiones Desnormalizadas del Esquema en Estrella
--      Observa que `dwh_dim_producto` ya incluye `categoria` y `marca` en la misma fila,
--      y `dwh_dim_cliente` ya incluye `tipo_cliente` (JUR/NAT), `ciudad`, `provincia` y `region`:
SELECT sk_producto, id_producto_oltp, descripcion, categoria, marca, um_venta, costo_actual, precio_actual
FROM dwh_dim_producto
ORDER BY sk_producto
LIMIT 10;

SELECT sk_cliente, id_cliente_oltp, nombre_cliente, tipo_cliente, ruc_ced, ciudad, provincia, region
FROM dwh_dim_cliente
ORDER BY sk_cliente;

-- 6.4  CONSULTA ANALÍTICA OLAP #1 (Roll-up Multidimensional por Región, Año y Trimestre)
--      Sobre el Esquema en Estrella para toma de decisiones gerenciales:
--      Solo requiere unir la tabla central de hechos (`dwh_fact_ventas`) con las dimensiones.
SELECT dt.anio,
       CONCAT('T', dt.trimestre)               AS trimestre,
       dc.region                               AS region_geografica,
       COUNT(DISTINCT fv.id_factura_oltp)      AS num_operaciones,
       SUM(fv.cantidad_vendida)                AS unidades_vendidas,
       SUM(fv.ingreso_bruto)                   AS ingresos_brutos_usd,
       SUM(fv.costo_total)                     AS costo_mercaderia_usd,
       SUM(fv.margen_ganancia)                 AS utilidad_neta_usd,
       ROUND(100 * SUM(fv.margen_ganancia) / NULLIF(SUM(fv.ingreso_bruto), 0), 2) AS rentabilidad_pct
FROM dwh_fact_ventas fv
INNER JOIN dwh_dim_tiempo  dt ON fv.sk_tiempo  = dt.sk_tiempo
INNER JOIN dwh_dim_cliente dc ON fv.sk_cliente = dc.sk_cliente
GROUP BY dt.anio, dt.trimestre, dc.region
ORDER BY dt.anio, dt.trimestre, utilidad_neta_usd DESC;

-- 6.5  CONSULTA ANALÍTICA OLAP #2 (Slice & Dice por Categoría, Marca y Tipo de Cliente B2B vs B2C)
--      ¿Qué categorías y marcas generan mayor margen de ganancia en clientes corporativos (JUR)
--      frente a consumidores finales (NAT)?
SELECT dp.categoria,
       dp.marca,
       dc.tipo_cliente                         AS segmento_cliente,
       SUM(fv.cantidad_vendida)                AS unidades,
       SUM(fv.ingreso_bruto)                   AS ventas_usd,
       SUM(fv.margen_ganancia)                 AS ganancia_usd,
       ROUND(100 * SUM(fv.margen_ganancia) / NULLIF(SUM(fv.ingreso_bruto), 0), 2) AS margen_pct
FROM dwh_fact_ventas fv
INNER JOIN dwh_dim_producto dp ON fv.sk_producto = dp.sk_producto
INNER JOIN dwh_dim_cliente  dc ON fv.sk_cliente  = dc.sk_cliente
GROUP BY dp.categoria, dp.marca, dc.tipo_cliente
ORDER BY ganancia_usd DESC
LIMIT 15;
