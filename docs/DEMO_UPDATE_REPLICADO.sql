-- =====================================================================================
-- DEMO: un UPDATE en Quito y su copia en Guayaquil (anillo Quito -> Guayaquil)
-- =====================================================================================

-- ------------------------------------------------------------------
-- PASO 1 · Sesión "1 - BD1 Quito ERP" (lacava_quito)
-- ------------------------------------------------------------------
-- Quién hace el cambio (el trigger de auditoría lo guarda en el log)
SET @auditoria_usuario = 'USR-DBA0001', @auditoria_ip = 'HeidiSQL-demo';

-- Antes
SELECT id_Cliente, cli_Nombre, cli_Telefono FROM clientes WHERE id_Cliente = 'CLI-000001';

-- El cambio (cambia el número si lo repites, para ver otro valor)
UPDATE clientes SET cli_Telefono = '022-555-0101' WHERE id_Cliente = 'CLI-000001';

-- Después, y cómo quedó en el log de Quito (anota el log_Seq)
SELECT id_Cliente, cli_Nombre, cli_Telefono FROM clientes WHERE id_Cliente = 'CLI-000001';
SELECT log_Seq, log_FechaHora, id_Usuario, log_TablaAfectada, log_Accion, log_ValorAnterior, log_ValorNuevo
FROM log_auditoria WHERE log_TablaAfectada = 'CLIENTES' ORDER BY log_Seq DESC LIMIT 1;


-- ------------------------------------------------------------------
-- PASO 2 · Esperar la ronda de replicación (máx. 1 minuto)
--          o en la app: Arquitectura -> pestaña 7 -> «Sincronizar ahora»
-- ------------------------------------------------------------------


-- ------------------------------------------------------------------
-- PASO 3 · Sesión "4 - BD4 Guayaquil ERP" (licoreriadatabase)
-- ------------------------------------------------------------------
-- El mismo cambio, con la etiqueta «RÉPLICA de Quito (BD 1)», el mismo log_seq y cuánto tardó en llegar
SELECT etiqueta_replica, log_seq_origen, id_usuario, tabla, accion,
       JSON_VALUE(valor_anterior, '$.cli_Telefono') AS telefono_antes,
       JSON_VALUE(valor_nuevo,    '$.cli_Telefono') AS telefono_despues,
       fecha_origen, replicado_en, TIMESTAMPDIFF(SECOND, fecha_origen, replicado_en) AS segundos_en_llegar
FROM replica_quito_log WHERE tabla = 'CLIENTES' ORDER BY log_seq_origen DESC LIMIT 1;
