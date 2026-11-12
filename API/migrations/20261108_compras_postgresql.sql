-- PostgreSQL. Revisar y probar en una copia antes de ejecutar en Supabase.
-- No modifica los totales históricos. La tasa histórica se estima a partir
-- del IVA y subtotal registrados; cuando el subtotal es cero se usa cero.
BEGIN;

LOCK TABLE public.compras, public.proxoc IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.compras ADD COLUMN IF NOT EXISTS oc_tasaiva numeric;

UPDATE public.compras
SET oc_tasaiva = CASE
    WHEN oc_subtotal = 0 THEN 0
    ELSE oc_iva * 100 / oc_subtotal
END
WHERE oc_tasaiva IS NULL;

ALTER TABLE public.compras ALTER COLUMN oc_tasaiva SET DEFAULT 15;
ALTER TABLE public.compras ALTER COLUMN oc_tasaiva SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.compras'::regclass
          AND conname = 'compras_oc_tasaiva_check'
    ) THEN
        ALTER TABLE public.compras ADD CONSTRAINT compras_oc_tasaiva_check
            CHECK (oc_tasaiva >= 0 AND oc_tasaiva <= 100) NOT VALID;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.fn_trg_after_insert_proxoc()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_subtotal numeric;
    v_tasa numeric;
    v_iva numeric;
BEGIN
    SELECT oc_tasaiva INTO STRICT v_tasa
    FROM public.compras WHERE id_compra = NEW.id_compra FOR UPDATE;

    SELECT COALESCE(SUM(pxo_subtotal), 0) INTO v_subtotal
    FROM public.proxoc WHERE id_compra = NEW.id_compra;

    v_iva := round(v_subtotal * v_tasa / 100, 2);
    UPDATE public.compras
    SET oc_subtotal = v_subtotal, oc_iva = v_iva, oc_total = v_subtotal + v_iva
    WHERE id_compra = NEW.id_compra;
    RETURN NEW;
END $$;

COMMIT;
