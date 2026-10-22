-- Use the active warehouse cost center for purchase accounting entries.
DROP TRIGGER IF EXISTS TRG_COMPRA_APR;

DELIMITER //
CREATE TRIGGER TRG_COMPRA_APR
AFTER UPDATE ON COMPRAS
FOR EACH ROW
BEGIN
    DECLARE v_id_asiento CHAR(10);
    DECLARE v_id_centro_costo CHAR(10);

    IF OLD.ESTADO_OC = 'ABI' AND NEW.ESTADO_OC = 'APR' THEN
        SET v_id_centro_costo = COALESCE(
            (
                SELECT CC.id_CentroCosto
                FROM CENTROS_COSTOS CC
                WHERE CC.id_Departamento = 'DEP-000003'
                  AND (CC.ESTADO_CCO = 'ACT' OR CC.ESTADO_CCO IS NULL)
                ORDER BY CC.id_CentroCosto
                LIMIT 1
            ),
            (
                SELECT CC.id_CentroCosto
                FROM CENTROS_COSTOS CC
                WHERE CC.ESTADO_CCO = 'ACT' OR CC.ESTADO_CCO IS NULL
                ORDER BY CC.id_CentroCosto
                LIMIT 1
            )
        );

        IF v_id_centro_costo IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'No hay un centro de costo activo para contabilizar la compra.';
        END IF;

        INSERT INTO RECEPCIONES (
            id_Recibo, id_Compra, rec_Descripcion, rec_FechaHora,
            rec_Num_Produc, ESTADO_REC
        )
        VALUES (
            CONCAT('REC-', RIGHT(NEW.id_Compra, 6)), NEW.id_Compra,
            'Recepción automática OC', NOW(), 0, 'PEN'
        );

        SET v_id_asiento = CONCAT('AS-', RIGHT(NEW.id_Compra, 7));

        INSERT INTO ASIENTOS (
            id_Asiento, asi_Descripcion, asi_Total_Debe, asi_Total_Haber,
            asi_FechaHora, USER_ID, ESTADO_ASI
        )
        VALUES (
            v_id_asiento, CONCAT('Compra OC: ', NEW.id_Compra),
            NEW.oc_Total, NEW.oc_Total, NOW(), 'SYS-AUTO', 'PEN'
        );

        INSERT INTO CTAxASI (
            id_Asiento, id_Cuenta, id_CentroCosto,
            cxa_Debe, cxa_Haber, ESTADO_CXA
        )
        VALUES
            (v_id_asiento, '1.1.03.01.01', v_id_centro_costo, NEW.oc_Subtotal, 0, 'ACT'),
            (v_id_asiento, '1.1.05.01.01', v_id_centro_costo, NEW.oc_IVA, 0, 'ACT'),
            (v_id_asiento, '2.1.03.01.01', v_id_centro_costo, 0, NEW.oc_Total, 'ACT');
    END IF;
END //
DELIMITER ;

DROP TRIGGER IF EXISTS TRG_AJUSTE_APR;

DELIMITER //
CREATE TRIGGER TRG_AJUSTE_APR
AFTER UPDATE ON AJUSTES
FOR EACH ROW
BEGIN
    DECLARE v_valor_perdida NUMERIC(7,2);
    DECLARE v_id_asiento CHAR(10);

    IF OLD.ESTADO_AJU = 'ABI' AND NEW.ESTADO_AJU = 'APR' THEN
        UPDATE PRODUCTOS P
        INNER JOIN PROxAJU PA ON P.id_Producto = PA.id_Producto
        SET P.pro_Qty_Ajustes = P.pro_Qty_Ajustes + PA.pxa_Qty_Ajustada,
            P.pro_Saldo_Final = P.pro_Saldo_Final + PA.pxa_Qty_Ajustada
        WHERE PA.id_Ajuste = NEW.id_Ajuste;

        SELECT IFNULL(SUM(ABS(PA.pxa_Cantidad) * P.pro_Valor_Compra), 0)
        INTO v_valor_perdida
        FROM PROxAJU PA
        INNER JOIN PRODUCTOS P ON PA.id_Producto = P.id_Producto
        WHERE PA.id_Ajuste = NEW.id_Ajuste;

        SET v_id_asiento = CONCAT('AJ-', RIGHT(NEW.id_Ajuste, 7));

        INSERT INTO ASIENTOS (
            id_Asiento, asi_Descripcion, asi_Total_Debe, asi_Total_Haber,
            asi_FechaHora, USER_ID, ESTADO_ASI
        )
        VALUES (
            v_id_asiento, CONCAT('Ajuste ', NEW.id_Ajuste),
            v_valor_perdida, v_valor_perdida, NOW(), 'SYS-AUTO', 'PEN'
        );
    END IF;
END //
DELIMITER ;

DROP PROCEDURE IF EXISTS SP_AJUSTE_APROBAR;

DELIMITER //
CREATE PROCEDURE SP_AJUSTE_APROBAR(
    IN p_id_Ajuste CHAR(15),
    IN p_id_Usuario CHAR(16)
)
BEGIN
    DECLARE v_estado CHAR(3);

    SELECT ESTADO_AJU
    INTO v_estado
    FROM AJUSTES
    WHERE id_Ajuste = p_id_Ajuste;

    IF v_estado = 'ABI' THEN
        UPDATE AJUSTES
        SET ESTADO_AJU = 'APR'
        WHERE id_Ajuste = p_id_Ajuste;

        UPDATE PROxAJU
        SET ESTADO_PxAJU = 'APR'
        WHERE id_Ajuste = p_id_Ajuste;

        CALL SP_REGISTRAR_LOG(
            p_id_Usuario,
            'AJUSTES',
            'UPDATE',
            '{"Estado": "ABI"}',
            '{"Estado": "APR"}'
        );
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'El ajuste no está en estado Abierto.';
    END IF;
END //
DELIMITER ;

-- The audit table only accepts the canonical CRUD action names.
DROP PROCEDURE IF EXISTS SP_COMPRA_APROBAR;

DELIMITER //
CREATE PROCEDURE SP_COMPRA_APROBAR(
    IN p_id_Compra CHAR(10),
    IN p_id_Usuario CHAR(16)
)
BEGIN
    DECLARE v_estado CHAR(3);

    SELECT ESTADO_OC
    INTO v_estado
    FROM COMPRAS
    WHERE id_Compra = p_id_Compra;

    IF v_estado = 'ABI' THEN
        UPDATE COMPRAS
        SET ESTADO_OC = 'APR'
        WHERE id_Compra = p_id_Compra;

        UPDATE PROxOC
        SET ESTADO_PxOC = 'APR'
        WHERE id_Compra = p_id_Compra;

        CALL SP_REGISTRAR_LOG(
            p_id_Usuario,
            'COMPRAS',
            'UPDATE',
            '{"Estado": "ABI"}',
            '{"Estado": "APR"}'
        );
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'La orden no está Abierta (ABI).';
    END IF;
END //
DELIMITER ;
