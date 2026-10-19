-- Apply this migration to databases where TRG_PAGO_APR is already installed.
DROP TRIGGER IF EXISTS TRG_PAGO_APR;

DELIMITER //
CREATE TRIGGER TRG_PAGO_APR
AFTER UPDATE ON PAGOS
FOR EACH ROW
BEGIN
    DECLARE v_total_sueldo NUMERIC(10,2);
    DECLARE v_total_bonos NUMERIC(10,2);
    DECLARE v_total_desc NUMERIC(10,2);
    DECLARE v_total_neto NUMERIC(10,2);
    DECLARE v_total_nomina NUMERIC(10,2);
    DECLARE v_id_asiento CHAR(10);
    DECLARE v_id_centro_costo CHAR(10);

    IF OLD.ESTADO_PAG = 'ABI' AND NEW.ESTADO_PAG = 'APR' THEN
        SET v_id_asiento = CONCAT('AS-', RIGHT(NEW.id_Pago, 7));

        SELECT IFNULL(SUM(pxe_Sueldo), 0),
               IFNULL(SUM(pxe_Bonificaciones), 0),
               IFNULL(SUM(pxe_Descuentos), 0),
               IFNULL(SUM(pxe_Valor_Neto), 0)
        INTO v_total_sueldo, v_total_bonos, v_total_desc, v_total_neto
        FROM PAGxEMP
        WHERE id_Pago = NEW.id_Pago;

        SET v_total_nomina = v_total_sueldo + v_total_bonos;

        SET v_id_centro_costo = (
            SELECT CC.id_CentroCosto
            FROM PAGxEMP PE
            INNER JOIN EMPLEADOS E ON E.id_Empleado = PE.id_Empleado
            INNER JOIN CENTROS_COSTOS CC ON CC.id_Departamento = E.id_Departamento
            WHERE PE.id_Pago = NEW.id_Pago
              AND (CC.ESTADO_CCO = 'ACT' OR CC.ESTADO_CCO IS NULL)
            ORDER BY CC.id_CentroCosto
            LIMIT 1
        );

        IF v_id_centro_costo IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'No hay un centro de costo activo asociado al departamento del empleado.';
        END IF;

        INSERT INTO ASIENTOS (
            id_Asiento, asi_Descripcion, asi_Total_Debe, asi_Total_Haber,
            asi_FechaHora, USER_ID, ESTADO_ASI
        )
        VALUES (
            v_id_asiento, CONCAT('Nómina ', NEW.id_Pago),
            v_total_nomina, v_total_nomina, NOW(), 'SYS-AUTO', 'PEN'
        );

        INSERT INTO CTAxASI (
            id_Asiento, id_Cuenta, id_CentroCosto, cxa_Debe, cxa_Haber, ESTADO_CXA
        )
        VALUES
            (v_id_asiento, 'CTA-GASTO', v_id_centro_costo, v_total_nomina, 0, 'ACT'),
            (v_id_asiento, 'CTA-PASIV', v_id_centro_costo, 0, v_total_desc, 'ACT'),
            (v_id_asiento, 'CTA-BANCO', v_id_centro_costo, 0, v_total_neto, 'ACT');
    END IF;
END //
DELIMITER ;
