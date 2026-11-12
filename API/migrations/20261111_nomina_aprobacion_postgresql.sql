-- Probar en una base aislada antes de aplicar. No modifica asientos existentes.
-- Replica la regla de MariaDB: sueldo + bonos como gasto y deuda;
-- los descuentos no se registran por separado en este asiento.
BEGIN;

CREATE OR REPLACE FUNCTION public.fn_nomina_aprobacion_v1()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    total_nomina numeric;
    asiento_id char(10);
    centro_id char(10);
    gasto_id char(15);
    pasivo_id char(15);
BEGIN
    IF OLD.estado_pag = 'ABI' AND NEW.estado_pag = 'APR' THEN
        SELECT COALESCE(SUM(pxe_sueldo + pxe_bonificaciones), 0)
        INTO total_nomina FROM public.pagxemp WHERE id_pago = NEW.id_pago;

        SELECT cc.id_centrocosto INTO centro_id
        FROM public.pagxemp pe
        JOIN public.empleados e ON e.id_empleado = pe.id_empleado
        JOIN public.centros_costos cc ON cc.id_departamento = e.id_departamento
        WHERE pe.id_pago = NEW.id_pago AND cc.estado_cco = 'ACT'
        ORDER BY cc.id_centrocosto LIMIT 1;

        SELECT MIN(CASE WHEN LOWER(cue_descripcion) LIKE '%nomina%'
                            OR id_cuenta LIKE '5.1.04%' THEN id_cuenta END),
               MIN(CASE WHEN LOWER(cue_descripcion) LIKE '%laboral%'
                            OR id_cuenta LIKE '2.1.04%' THEN id_cuenta END)
        INTO gasto_id, pasivo_id
        FROM public.cuentas WHERE cue_tipo = 'DET' AND estado_cue = 'ACT';

        IF centro_id IS NULL THEN
            RAISE EXCEPTION 'No hay centro de costo activo para el departamento del empleado.';
        END IF;
        IF gasto_id IS NULL OR pasivo_id IS NULL OR gasto_id = pasivo_id THEN
            RAISE EXCEPTION 'Configure cuentas activas distintas de gasto de nomina y obligaciones laborales.';
        END IF;
        IF total_nomina <= 0 THEN
            RAISE EXCEPTION 'El total de la nomina debe ser positivo.';
        END IF;

        asiento_id := CONCAT('NP', RIGHT(TRIM(NEW.id_pago), 8));
        INSERT INTO public.asientos
            (id_asiento, asi_descripcion, asi_total_debe, asi_total_haber,
             asi_fechahora, user_id, estado_asi)
        VALUES (asiento_id, CONCAT('Nomina ', TRIM(NEW.id_pago)), total_nomina,
                total_nomina, NOW(), NEW.user_id, 'PEN');
        INSERT INTO public.ctaxasi
            (id_asiento, id_cuenta, id_centrocosto, cxa_debe, cxa_haber, estado_cxa)
        VALUES (asiento_id, gasto_id, centro_id, total_nomina, 0, 'ACT'),
               (asiento_id, pasivo_id, centro_id, 0, total_nomina, 'ACT');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_pago_apr ON public.pagos;
CREATE TRIGGER trg_pago_apr AFTER UPDATE ON public.pagos
FOR EACH ROW EXECUTE FUNCTION public.fn_nomina_aprobacion_v1();

COMMIT;
