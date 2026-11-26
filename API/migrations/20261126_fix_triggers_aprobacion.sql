-- =====================================================================================
-- Corrige los triggers de APROBACIÓN del ERP MariaDB (Quito y Guayaquil)
--
-- 1) TRG_FAC_APR generaba id_Asiento = 'ASI-' + 8 caracteres = 12 > CHAR(10)
--    -> error 1406 "Data too long for column id_Asiento": NINGUNA factura se podía aprobar.
--    Además creaba una segunda ENTREGA aunque el POS ya la había creado al vender.
-- 2) TRG_AJUSTE_APR generaba id_Asiento = 'ASI-AJ-' + 5 = 12 > CHAR(10): mismo error al aprobar un ajuste.
--
-- 3) asi_Descripcion es CHAR(30): 'Ingreso por Factura: ' + id (34) tampoco cabía; ahora 'Venta ' + id.
--
-- Ahora: el asiento usa 'AF'/'AJ' + los últimos 8 caracteres del documento (10 en total) y la
-- entrega automática solo se crea si la factura todavía no tiene una.
-- =====================================================================================

DELIMITER $$

DROP TRIGGER IF EXISTS TRG_FAC_APR $$
CREATE TRIGGER TRG_FAC_APR AFTER UPDATE ON FACTURAS FOR EACH ROW
BEGIN
    IF OLD.ESTADO_FAC = 'ABI' AND NEW.ESTADO_FAC = 'APR' THEN
        IF NOT EXISTS (SELECT 1 FROM ENTREGAS WHERE id_Factura = NEW.id_Factura) THEN
            INSERT INTO ENTREGAS (id_Entrega, id_Factura, ent_Descripcion, ent_FechaHora, ent_Num_Produc, ESTADO_ENT)
            VALUES (CONCAT('E-', RIGHT(NEW.id_Factura, 8)), NEW.id_Factura, 'Despacho por Venta Aprobada', NOW(), 0, 'PEN');
        END IF;

        INSERT INTO ASIENTOS (id_Asiento, asi_Descripcion, asi_Total_Debe, asi_Total_Haber, asi_FechaHora, USER_ID, ESTADO_ASI)
        VALUES (CONCAT('AF', RIGHT(NEW.id_Factura, 8)), CONCAT('Venta ', NEW.id_Factura),
                NEW.fac_Total, NEW.fac_Total, NOW(), 'SYS-AUTO', 'PEN');
    END IF;
END $$

DROP TRIGGER IF EXISTS TRG_AJUSTE_APR $$
CREATE TRIGGER TRG_AJUSTE_APR AFTER UPDATE ON AJUSTES FOR EACH ROW
BEGIN
    DECLARE v_valor_perdida NUMERIC(7,2);
    IF OLD.ESTADO_AJU = 'ABI' AND NEW.ESTADO_AJU = 'APR' THEN
        UPDATE PRODUCTOS P
        INNER JOIN PROxAJU PA ON P.id_Producto = PA.id_Producto
        SET P.pro_Qty_Ajustes = P.pro_Qty_Ajustes + PA.pxa_Cantidad,
            P.pro_Saldo_Final = P.pro_Saldo_Final + PA.pxa_Cantidad
        WHERE PA.id_Ajuste = NEW.id_Ajuste;

        SELECT IFNULL(SUM(ABS(PA.pxa_Cantidad) * P.pro_Valor_Compra), 0) INTO v_valor_perdida
        FROM PROxAJU PA
        INNER JOIN PRODUCTOS P ON PA.id_Producto = P.id_Producto
        WHERE PA.id_Ajuste = NEW.id_Ajuste;

        INSERT INTO ASIENTOS (id_Asiento, asi_Descripcion, asi_Total_Debe, asi_Total_Haber, asi_FechaHora, USER_ID, ESTADO_ASI)
        VALUES (CONCAT('AJ', RIGHT(NEW.id_Ajuste, 8)), CONCAT('Ajuste inventario ', NEW.id_Ajuste),
                v_valor_perdida, v_valor_perdida, NOW(), 'SYS-AUTO', 'PEN');
    END IF;
END $$

DELIMITER ;
