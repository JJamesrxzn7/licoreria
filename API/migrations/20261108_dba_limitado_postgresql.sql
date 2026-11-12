-- PostgreSQL. Revisar antes de ejecutar con una cuenta autorizada.
-- Crea un rol de grupo sin LOGIN: no se asigna a ninguna cuenta.
-- Fallará si el rol ya existe; no modifica ni reutiliza un rol preexistente.
-- Los permisos directos, membresías y privilegios de PUBLIC se suman.
-- Esta configuración no impide DELETE ni cambios en datos de seguridad.
BEGIN;

CREATE ROLE licoreria_dba_limitado
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

GRANT USAGE ON SCHEMA public TO licoreria_dba_limitado;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO licoreria_dba_limitado;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO licoreria_dba_limitado;

COMMIT;

-- Antes de asignar el rol, revisar ownership, membresías, privilegios
-- efectivos, funciones SECURITY DEFINER, permisos de PUBLIC y políticas RLS.
-- La cuenta receptora no debe ser propietaria de las tablas ni del esquema.
-- El propietario de objetos futuros debe conceder sus privilegios por separado.
