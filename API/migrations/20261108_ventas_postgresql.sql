-- Aplicar manualmente en una transacción, tras respaldo y conciliación.
-- No actualiza documentos históricos ni deduce su IVA o movimientos de stock.
-- La API nueva sólo opera facturas inscritas en ventas_control.
BEGIN;

ALTER TABLE facturas ADD COLUMN fac_tasa_iva numeric(5,2)
    CHECK (fac_tasa_iva BETWEEN 0 AND 100);

CREATE TABLE ventas_control (
    id_factura char(15) PRIMARY KEY REFERENCES facturas(id_factura),
    id_asiento char(10) UNIQUE REFERENCES asientos(id_asiento),
    id_entrega char(15) UNIQUE REFERENCES entregas(id_entrega),
    id_usuario char(16) NOT NULL REFERENCES usuarios(id_usuario),
    id_solicitud varchar(64) NOT NULL,
    huella char(64) NOT NULL,
    UNIQUE (id_usuario, id_solicitud)
);
ALTER TABLE ventas_control ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE ventas_control FROM PUBLIC;
CREATE POLICY ventas_control_lectura ON ventas_control
    FOR SELECT TO PUBLIC USING (true);
CREATE POLICY ventas_control_insercion ON ventas_control
    FOR INSERT TO PUBLIC WITH CHECK (true);
CREATE POLICY ventas_control_actualizacion ON ventas_control
    FOR UPDATE TO PUBLIC USING (true) WITH CHECK (true);

-- No se validan ni modifican históricos; sí se impide introducir nuevas
-- cantidades negativas o superiores a la cantidad facturada.
ALTER TABLE proxent ADD CONSTRAINT proxent_cantidad_ciclo_ventas
    CHECK (pxe_cantidad > 0 AND pxe_qty_entregada >= 0
           AND pxe_qty_entregada <= pxe_cantidad) NOT VALID;

-- Una sola operación atómica valida y descuenta stock. La cabecera debe existir
-- y estar marcada como creada por el flujo nuevo, para no reinterpretar históricos.
CREATE OR REPLACE FUNCTION fn_trg_before_insert_proxfac() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_estado char(3);
BEGIN
    SELECT f.estado_fac INTO v_estado
      FROM facturas f JOIN ventas_control c ON c.id_factura = f.id_factura
     WHERE f.id_factura = NEW.id_factura FOR UPDATE OF f;
    IF NOT FOUND OR v_estado IS DISTINCT FROM 'ABI' THEN
        RAISE EXCEPTION 'Factura no gestionada por el nuevo ciclo o no abierta'
            USING ERRCODE = 'P0001';
    END IF;
    IF NEW.pxf_cantidad <= 0 THEN
        RAISE EXCEPTION 'Cantidad de venta inválida' USING ERRCODE = 'P0001';
    END IF;
    UPDATE productos
       SET pro_qty_egresos = pro_qty_egresos + NEW.pxf_cantidad,
           pro_saldo_final = pro_saldo_final - NEW.pxf_cantidad
     WHERE id_producto = NEW.id_producto AND estado_prod = 'ACT'
       AND pro_saldo_final >= NEW.pxf_cantidad;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Producto inexistente, inactivo o con stock insuficiente'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

-- El AFTER heredado aplicaba un segundo movimiento y recalculaba IVA al 15%.
DROP TRIGGER trg_after_insert_proxfac ON proxfac;

-- La entrega sólo registra cantidades físicas: el stock salió al facturar.
CREATE OR REPLACE FUNCTION fn_trg_ent_conf() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estado_ent = 'ENT' AND OLD.estado_ent IS DISTINCT FROM 'ENT' THEN
        IF NOT EXISTS (SELECT 1 FROM proxent WHERE id_entrega = NEW.id_entrega)
           OR EXISTS (SELECT 1 FROM proxent WHERE id_entrega = NEW.id_entrega
                       AND pxe_qty_entregada <> pxe_cantidad)
           OR NOT EXISTS (SELECT 1 FROM facturas
                           WHERE id_factura = NEW.id_factura AND estado_fac = 'APR') THEN
            RAISE EXCEPTION 'No se puede completar una entrega incompleta o sin factura aprobada'
                USING ERRCODE = 'P0001';
        END IF;
    END IF;
    RETURN NEW;
END $$;

-- La API genera una sola entrega al crear y el asiento pendiente al aprobar.
-- Evitar que el trigger heredado cree duplicados o asientos sin control.
CREATE OR REPLACE FUNCTION fn_trg_fac_apr() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estado_fac = 'APR' AND OLD.estado_fac IS DISTINCT FROM 'APR'
       AND NOT EXISTS (
           SELECT 1 FROM ventas_control c JOIN asientos a ON a.id_asiento = c.id_asiento
            WHERE c.id_factura = NEW.id_factura AND c.id_entrega IS NOT NULL
              AND a.estado_asi = 'PEN'
       ) THEN
        RAISE EXCEPTION 'La aprobación requiere el ciclo de ventas actualizado'
            USING ERRCODE = 'P0001';
    END IF;
    IF NEW.estado_fac = 'ANU' AND OLD.estado_fac IS DISTINCT FROM 'ANU'
       AND current_setting('app.venta_anulacion', true) IS DISTINCT FROM TRIM(NEW.id_factura) THEN
        RAISE EXCEPTION 'La anulación requiere el ciclo de ventas actualizado'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

-- Las rutinas anteriores anulan sin devolver stock o crean entregas duplicadas.
-- No dejar un camino paralelo que evite las comprobaciones del nuevo ciclo.
CREATE OR REPLACE PROCEDURE sp_factura_aprobar(IN p_id_factura character, IN p_id_usuario character)
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Use el ciclo de ventas PostgreSQL actualizado' USING ERRCODE = 'P0001';
END $$;

CREATE OR REPLACE PROCEDURE sp_factura_anular(IN p_id_factura character, IN p_id_usuario character)
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Use el ciclo de ventas PostgreSQL actualizado' USING ERRCODE = 'P0001';
END $$;

COMMIT;
