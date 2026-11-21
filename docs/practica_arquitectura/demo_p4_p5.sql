-- ============================================================================
-- DEMOSTRACIÓN SQL PRÁCTICA — PREGUNTAS 4 Y 5 (BASES DE DATOS II - PUCE)
-- Proyecto: Licorería "La Cava" — Arquitectura Multi-Sitio y Multi-Motor
-- ============================================================================
-- Topología física activa:
--   * SEDE QUITO (UIO):
--       1. Puerto :3307 (MariaDB 12.3) -> `licoreriadatabase` (5 Módulos: C, I, V, TH, Ctbl)
--       2. Puerto :3307 (MariaDB JSON) -> `quito_nosql_db` (+ `API/data/quito_nosql.db`)
--       3. Puerto :5432 (PostgreSQL 18)-> `quito_otras_dwh` (DWH Estrella & Auditoría 2PC)
--   * SEDE GUAYAQUIL (GYE):
--       4. Puerto :3308 (MariaDB 12.3) -> `licoreria_guayaquil` (Fragmento Costa GYE/MNT/MCH)
--       5. Puerto :3309 (MariaDB 12.3) -> `licoreria_guayaquil_bodega` (Bodega Puerto & Réplica)
--   * SEDE NUBE CUENCA & LOJA (CLOUD DB):
--       6. Puerto :5432 (PostgreSQL 18)-> `cloud_cuenca_loja` / Supabase Cloud Pooler us-east-1
-- ============================================================================

-- ============================================================================
-- PARTE 1: PREGUNTA 4 — TRANSPARENCIA DE LOCALIZACIÓN Y FRAGMENTACIÓN
-- ============================================================================

-- 1.1. En NODO 1 QUITO (:3307 - Base `licoreriadatabase`):
-- Los 5 módulos funcionales de la pizarra (C, I, V, TH, Ctbl) están expuestos como vistas:
USE licoreriadatabase;

SELECT 'C - Compras' AS modulo_pizarra, COUNT(*) AS registros FROM mod_c_compras
UNION ALL
SELECT 'I - Inventarios', COUNT(*) FROM mod_i_inventarios
UNION ALL
SELECT 'V - Ventas', COUNT(*) FROM mod_v_ventas
UNION ALL
SELECT 'TH - Talento Humano', COUNT(*) FROM mod_th_talento_humano
UNION ALL
SELECT 'Ctbl - Contabilidad', COUNT(*) FROM mod_ctbl_contabilidad;

-- Fragmento Horizontal Primario en Quito (Clientes y Facturas de la Sierra Norte: UIO, IBR, AMB):
SELECT id_Cliente, cedula_ruc, nombre_completo, id_Ciudad, ciudad, nodo_origen
FROM frag_quito_clientes
ORDER BY id_Cliente;

-- 1.2. En NODO 4 GUAYAQUIL (:3308 - Base `licoreria_guayaquil`):
-- Fragmento Horizontal Primario en Guayaquil (Clientes y Facturas de la Costa: GYE, MNT, MCH):
-- (Ejecutar conectado al Puerto TCP 3308 en HeidiSQL o en el Prompt DBA de la interfaz web)
USE licoreria_guayaquil;

SELECT @@port AS puerto_instancia_guayaquil, @@datadir AS datadir_guayaquil, DATABASE() AS bd_activa;

SELECT id_Cliente, cedula_ruc, nombre_completo, id_Ciudad, sede_fragmento
FROM frag_gye_clientes
ORDER BY id_Ciudad, id_Cliente;

-- 1.3. En NODO 6 NUBE CUENCA & LOJA (:5432 - Base PostgreSQL `cloud_cuenca_loja`):
-- Fragmento Horizontal Primario en la Nube Austral (Clientes y Proveedores de Cuenca CUE y Loja LJA):
-- (Ejecutar conectado a PostgreSQL :5432 base `cloud_cuenca_loja`)
SELECT id_cliente, cedula_ruc, nombre_completo, id_ciudad, sucursal_nube
FROM frag_austral_clientes
ORDER BY id_ciudad, id_cliente;

-- 1.4. RECONSTRUCCIÓN GLOBAL CON TRANSPARENCIA DE FRAGMENTACIÓN (PREGUNTA 4):
-- El usuario o cajero en el Frontend React NO necesita saber en qué puerto (:3307, :3308 o :5432)
-- ni en qué motor (MariaDB vs PostgreSQL) reside cada cliente. El Middleware / Enrutador Distribuido
-- ejecuta la unión algebraica de los fragmentos disjuntos:
--   CLIENTES_GLOBAL = frag_quito_clientes (:3307) ∪ frag_gye_clientes (:3308) ∪ frag_austral_clientes (:5432)


-- ============================================================================
-- PARTE 2: PREGUNTA 5 — CONCURRENCIA DISTRIBUIDA Y PROTOCOLO 2PC (TWO-PHASE COMMIT)
-- ============================================================================
-- Escenario: Transferencia interregional o Venta Corporativa Nacional que descuenta
-- 15 botellas de Aguardiente Zhumir (PRO-004) en Bodega Guayaquil (:3308) y las ingresa
-- en Sede Matriz Quito (:3307), registrando la trazabilidad en Cuenca Cloud (:5432).

-- ----------------------------------------------------------------------------
-- CASO A: EJECUCIÓN EXITOSA DEL PROTOCOLO 2PC (UNANIMIDAD EN FASE 1 -> COMMIT EN FASE 2)
-- ----------------------------------------------------------------------------

-- [FASE 1: PREPARE / VOTACIÓN]
-- En Nodo 1 Quito (:3307 - MariaDB XA):
XA START 'tx_lacava_2pc_001_quito';
UPDATE licoreriadatabase.productos
SET pro_Qty_Ingresos = COALESCE(pro_Qty_Ingresos, 0) + 15,
    pro_Saldo_Final  = COALESCE(pro_Saldo_Final, 0) + 15
WHERE id_Producto = 'PRO-004';
XA END 'tx_lacava_2pc_001_quito';
XA PREPARE 'tx_lacava_2pc_001_quito'; -- Nodo Quito escribe en redo/XA log y vota: VOTE_COMMIT

-- En Nodo 4 Guayaquil (:3308 - MariaDB XA):
XA START 'tx_lacava_2pc_001_guayaquil';
UPDATE licoreria_guayaquil.frag_gye_inventario
SET stock_guayaquil = stock_guayaquil - 15
WHERE id_Producto = 'PRO-004' AND stock_guayaquil >= 15;
XA END 'tx_lacava_2pc_001_guayaquil';
XA PREPARE 'tx_lacava_2pc_001_guayaquil'; -- Nodo Guayaquil valida stock y vota: VOTE_COMMIT

-- [FASE 2: GLOBAL COMMIT]
-- Al recibir VOTE_COMMIT de todos los participantes, el Coordinador Middleware (:8000) ordena:
XA COMMIT 'tx_lacava_2pc_001_quito';
XA COMMIT 'tx_lacava_2pc_001_guayaquil';


-- ----------------------------------------------------------------------------
-- CASO B: ANÁLISIS DE FALLO EN FASE PREPARE (RESPUESTA EXACTA A LA PREGUNTA 5)
-- ¿Qué ocurre si el Nodo Guayaquil (:3308) sufre una caída de red, timeout o violación
-- de restricción durante la Fase 1 (PREPARE)?
-- ----------------------------------------------------------------------------

-- 1. Nodo Quito (:3307) ejecuta su PREPARE exitosamente y queda en estado PREPARED (bloqueando la fila):
XA START 'tx_lacava_2pc_002_fail_demo';
UPDATE licoreriadatabase.productos
SET pro_Saldo_Final = pro_Saldo_Final + 15
WHERE id_Producto = 'PRO-004';
XA END 'tx_lacava_2pc_002_fail_demo';
XA PREPARE 'tx_lacava_2pc_002_fail_demo'; -- Quito vota VOTE_COMMIT y espera decisión del Coordinador.

-- 2. Nodo Guayaquil (:3308) FALLA durante la Fase PREPARE (ej. caída del enlace WAN o VOTE_ABORT).
-- 3. El Coordinador 2PC detecta la falta de unanimidad en Fase 1 y decide GLOBAL_ABORT.
-- 4. El Coordinador envía XA ROLLBACK a Quito (:3307) y Cuenca (:5432), liberando los bloqueos
--    y revirtiendo el incremento de stock en Quito para preservar la Atomicidad ACID:
XA ROLLBACK 'tx_lacava_2pc_002_fail_demo';

-- 5. Bitácora global del Coordinador 2PC en el Nodo 3 de Quito (PostgreSQL :5432 `quito_otras_dwh`):
-- (Ejecutar en PostgreSQL :5432 base `quito_otras_dwh`)
SELECT tx_id, coordinador, nodos_involucrados, fase_alcanzada, decision_global, detalle_operacion, fecha_hora
FROM auditoria_transacciones_2pc
ORDER BY fecha_hora DESC;
