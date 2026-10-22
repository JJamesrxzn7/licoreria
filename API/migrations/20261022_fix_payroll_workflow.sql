-- Repair payroll approval/accounting and use only valid audit actions.
DROP PROCEDURE IF EXISTS SP_PAGO_APROBAR;
DROP PROCEDURE IF EXISTS SP_PAGO_ANULAR;
DROP TRIGGER IF EXISTS TRG_PAGO_APR;

DELIMITER //
CREATE PROCEDURE SP_PAGO_APROBAR(IN p_id_Pago CHAR(10), IN p_id_Usuario CHAR(16))
BEGIN
    DECLARE v_estado CHAR(3);

    SELECT ESTADO_PAG INTO v_estado
    FROM PAGOS
    WHERE id_Pago = p_id_Pago
    FOR UPDATE;

    IF v_estado = 'ABI' THEN
        UPDATE PAGOS SET ESTADO_PAG = 'APR' WHERE id_Pago = p_id_Pago;
        UPDATE PAGxEMP SET ESTADO_PxE = 'APR' WHERE id_Pago = p_id_Pago;
        CALL SP_REGISTRAR_LOG(p_id_Usuario, 'PAGOS', 'UPDATE', '{"estado":"ABI"}', '{"estado":"APR"}');
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Solo se pueden aprobar roles de pago abiertos (ABI).';
    END IF;
END //

CREATE PROCEDURE SP_PAGO_ANULAR(IN p_id_Pago CHAR(10), IN p_id_Usuario CHAR(16))
BEGIN
    DECLARE v_estado CHAR(3);

    SELECT ESTADO_PAG INTO v_estado
    FROM PAGOS
    WHERE id_Pago = p_id_Pago
    FOR UPDATE;

    IF v_estado = 'ABI' THEN
        UPDATE PAGOS SET ESTADO_PAG = 'ANU' WHERE id_Pago = p_id_Pago;
        UPDATE PAGxEMP SET ESTADO_PxE = 'ANU' WHERE id_Pago = p_id_Pago;
        CALL SP_REGISTRAR_LOG(p_id_Usuario, 'PAGOS', 'UPDATE', '{"estado":"ABI"}', '{"estado":"ANU"}');
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Solo se pueden anular roles de pago abiertos (ABI).';
    END IF;
END //

CREATE TRIGGER TRG_PAGO_APR
AFTER UPDATE ON PAGOS
FOR EACH ROW
BEGIN
    DECLARE v_total_sueldo DECIMAL(10,2);
    DECLARE v_total_bonos DECIMAL(10,2);
    DECLARE v_total_nomina DECIMAL(10,2);
    DECLARE v_id_asiento CHAR(10);
    DECLARE v_id_centro_costo CHAR(10);
    DECLARE v_id_cuenta_gasto CHAR(15);
    DECLARE v_id_cuenta_pasivo CHAR(15);

    IF OLD.ESTADO_PAG = 'ABI' AND NEW.ESTADO_PAG = 'APR' THEN
        SET v_id_asiento = CONCAT('NP', RIGHT(NEW.id_Pago, 8));

        SELECT IFNULL(SUM(pxe_Sueldo), 0), IFNULL(SUM(pxe_Bonificaciones), 0)
        INTO v_total_sueldo, v_total_bonos
        FROM PAGxEMP
        WHERE id_Pago = NEW.id_Pago;

        SET v_total_nomina = v_total_sueldo + v_total_bonos;

        SET v_id_centro_costo = (
            SELECT CC.id_CentroCosto
            FROM PAGxEMP PE
            INNER JOIN EMPLEADOS E ON E.id_Empleado = PE.id_Empleado
            INNER JOIN CENTROS_COSTOS CC ON CC.id_Departamento = E.id_Departamento
            WHERE PE.id_Pago = NEW.id_Pago
              AND CC.ESTADO_CCO = 'ACT'
            ORDER BY CC.id_CentroCosto
            LIMIT 1
        );

        SELECT MIN(CASE
            WHEN LOWER(cue_Descripcion) LIKE '%nomina%'
              OR id_Cuenta LIKE '5.1.04%' THEN id_Cuenta
        END),
        MIN(CASE
            WHEN LOWER(cue_Descripcion) LIKE '%laboral%'
              OR id_Cuenta LIKE '2.1.04%' THEN id_Cuenta
        END)
        INTO v_id_cuenta_gasto, v_id_cuenta_pasivo
        FROM CUENTAS
        WHERE cue_Tipo = 'DET'
          AND ESTADO_CUE = 'ACT';

        IF v_id_centro_costo IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'No hay un centro de costo activo para el departamento del empleado.';
        END IF;
        IF v_id_cuenta_gasto IS NULL OR v_id_cuenta_pasivo IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Configure cuentas activas de gasto de nómina y obligaciones laborales.';
        END IF;

        INSERT INTO ASIENTOS (
            id_Asiento, asi_Descripcion, asi_Total_Debe, asi_Total_Haber,
            asi_FechaHora, USER_ID, ESTADO_ASI
        )
        VALUES (
            v_id_asiento, CONCAT('Nomina ', NEW.id_Pago),
            v_total_nomina, v_total_nomina, NOW(), 'SYS-AUTO', 'PEN'
        );

        INSERT INTO CTAxASI (
            id_Asiento, id_Cuenta, id_CentroCosto, cxa_Debe, cxa_Haber, ESTADO_CXA
        )
        VALUES
            (v_id_asiento, v_id_cuenta_gasto, v_id_centro_costo, v_total_nomina, 0, 'ACT'),
            (v_id_asiento, v_id_cuenta_pasivo, v_id_centro_costo, 0, v_total_nomina, 'ACT');
    END IF;
END //
DELIMITER ;
