-- API PostgreSQL: rol de grupo restringido para el backend.
-- Ejecutar solo tras respaldo y prueba en una copia aislada del esquema.
-- Concede acceso de filas a la API de confianza; la matriz de negocio se
-- aplica en el servidor. No conceder este rol a usuarios finales.
BEGIN;

CREATE ROLE licoreria_api_access
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

GRANT USAGE ON SCHEMA public TO licoreria_api_access;

DO $$
DECLARE
    table_name text;
    procedure_record record;
    procedure_count integer := 0;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'asientos', 'bancos', 'bonificaciones', 'bonxempxpag', 'cargos',
        'cargosxempleado', 'categorias', 'centros_costos', 'ciudades',
        'clientes', 'cargas', 'cuentas', 'ctaxasi', 'descuentos',
        'departamentos', 'desxempxpag', 'empleados', 'entregas', 'facturas',
        'log_auditoria', 'marcas', 'pagos', 'pagxemp', 'perchas', 'permisos',
        'productos', 'proxaju', 'proxent', 'proxfac', 'proxoc', 'proxrec',
        'proveedores', 'recepciones', 'roles', 'rolesxpermisos', 'compras',
        'sesiones_revocadas', 'tipo_cuenta', 'unidades_medidas', 'usuarios',
        'usuariosxroles', 'ajustes', 'ventas_control'
    ] LOOP
        IF to_regclass(format('public.%I', table_name)) IS NULL THEN
            RAISE EXCEPTION 'Falta la tabla requerida public.%', table_name;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'GRANT SELECT ON TABLE public.%I TO licoreria_api_access', table_name
        );
        EXECUTE format(
            'CREATE POLICY licoreria_api_access_select ON public.%I '
            'FOR SELECT TO licoreria_api_access USING (true)', table_name
        );
    END LOOP;

    FOREACH table_name IN ARRAY ARRAY[
        'ajustes', 'asientos', 'bancos', 'bonificaciones', 'bonxempxpag',
        'cargosxempleado', 'compras', 'cuentas', 'ctaxasi', 'descuentos',
        'desxempxpag', 'empleados', 'entregas', 'facturas', 'log_auditoria',
        'pagos', 'pagxemp', 'productos', 'proxaju', 'proxent', 'proxfac',
        'proxrec', 'recepciones', 'sesiones_revocadas', 'usuarios',
        'ventas_control', 'proxoc'
    ] LOOP
        EXECUTE format(
            'GRANT INSERT, UPDATE ON TABLE public.%I TO licoreria_api_access',
            table_name
        );
        EXECUTE format(
            'CREATE POLICY licoreria_api_access_insert ON public.%I '
            'FOR INSERT TO licoreria_api_access WITH CHECK (true)', table_name
        );
        EXECUTE format(
            'CREATE POLICY licoreria_api_access_update ON public.%I '
            'FOR UPDATE TO licoreria_api_access USING (true) WITH CHECK (true)',
            table_name
        );
    END LOOP;

    FOR procedure_record IN
        SELECT n.nspname, p.proname,
               pg_get_function_identity_arguments(p.oid) AS identity_arguments,
               p.prosecdef
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.prokind = 'p'
          AND p.proname = ANY (ARRAY[
              'sp_registrar_log',
              'sp_compra_crear', 'sp_compra_agregar_producto',
              'sp_compra_aprobar', 'sp_compra_anular'
          ])
    LOOP
        IF procedure_record.prosecdef THEN
            RAISE EXCEPTION
                'El procedimiento public.% es SECURITY DEFINER; requiere revisión manual.',
                procedure_record.proname;
        END IF;
        EXECUTE format(
            'GRANT EXECUTE ON PROCEDURE %I.%I(%s) TO licoreria_api_access',
            procedure_record.nspname, procedure_record.proname,
            procedure_record.identity_arguments
        );
        procedure_count := procedure_count + 1;
    END LOOP;

    IF procedure_count <> 5 THEN
        RAISE EXCEPTION
            'Se esperaban 5 procedimientos de compras/auditoría de seguridad invoker; encontrados: %.',
            procedure_count;
    END IF;
END $$;

COMMIT;

-- Después de crear una cuenta LOGIN dedicada, concederle únicamente este rol.
-- La cuenta LOGIN debe heredar la membresía para que apliquen los GRANT y RLS.
-- No usar el rol propietario/administrador actual ni el rol DBA limitado.
-- Ejemplo intencionalmente comentado; sustituir por el nombre del LOGIN:
-- GRANT licoreria_api_access TO nombre_login_api;
--
-- Esta política confía en el backend para toda fila de las tablas autorizadas.
-- No concede DELETE, TRUNCATE, DDL, propiedad, BYPASSRLS ni privilegios sobre
-- secuencias. Los objetos nuevos requieren una migración/grant revisado.
