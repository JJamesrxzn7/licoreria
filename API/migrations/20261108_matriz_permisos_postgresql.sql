-- PostgreSQL. Revisar y respaldar antes de ejecutar; no se ejecuta desde la API.
-- Los roles y permisos deben existir, estar activos y no tener duplicados.
-- La matriz solo modifica los 15 roles indicados y agrega permisos al
-- Administrador. No asigna roles a usuarios ni modifica otros roles.
BEGIN;

LOCK TABLE public.roles, public.permisos, public.rolesxpermisos
    IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMPORARY TABLE licoreria_roles_matriz (
    nombre text PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO licoreria_roles_matriz (nombre) VALUES
    ('JEFE_COMPRAS'), ('AUXILIAR_COMPRAS'), ('OPERATIVO_COMPRAS'),
    ('JEFE_INVENTARIOS'), ('AUXILIAR_INVENTARIOS'), ('OPERATIVO_INVENTARIOS'),
    ('JEFE_VENTAS'), ('AUXILIAR_VENTAS'), ('OPERATIVO_VENTAS'),
    ('JEFE_TALENTO_HUMANO'), ('AUXILIAR_TALENTO_HUMANO'), ('OPERATIVO_TALENTO_HUMANO'),
    ('JEFE_CONTABILIDAD'), ('AUXILIAR_CONTABILIDAD'), ('OPERATIVO_CONTABILIDAD'),
    ('ADMINISTRADOR');

DO $$
BEGIN
    IF (SELECT count(*) FROM public.roles r
        JOIN licoreria_roles_matriz t ON t.nombre = upper(trim(r.rol_nombre))) <> 16
       OR (SELECT count(DISTINCT t.nombre) FROM public.roles r
           JOIN licoreria_roles_matriz t ON t.nombre = upper(trim(r.rol_nombre))
           WHERE r.estado_rol = 'ACT') <> 16 THEN
        RAISE EXCEPTION 'Faltan roles, estan inactivos o sus nombres estan duplicados.';
    END IF;

    IF (SELECT count(*) FROM public.permisos
        WHERE prm_modulo IN ('COMPRAS', 'INVENTARIOS', 'VENTAS', 'TALENTO_HUMANO', 'CONTABILIDAD')
          AND prm_accion IN ('CREAR', 'VER', 'APROBAR', 'ANULAR')) <> 20
       OR (SELECT count(DISTINCT (prm_modulo, prm_accion)) FROM public.permisos
           WHERE prm_modulo IN ('COMPRAS', 'INVENTARIOS', 'VENTAS', 'TALENTO_HUMANO', 'CONTABILIDAD')
             AND prm_accion IN ('CREAR', 'VER', 'APROBAR', 'ANULAR')
             AND estado_prm = 'ACT') <> 20 THEN
        RAISE EXCEPTION 'Faltan permisos, estan inactivos o existen permisos duplicados.';
    END IF;
END $$;

CREATE TEMPORARY TABLE licoreria_permisos_matriz (
    id_rol char(10) NOT NULL,
    id_permiso char(10) NOT NULL,
    PRIMARY KEY (id_rol, id_permiso)
) ON COMMIT DROP;

INSERT INTO licoreria_permisos_matriz (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso
FROM public.roles r
JOIN licoreria_roles_matriz t ON t.nombre = upper(trim(r.rol_nombre))
JOIN public.permisos p
  ON p.prm_modulo IN ('COMPRAS', 'INVENTARIOS', 'VENTAS', 'TALENTO_HUMANO', 'CONTABILIDAD')
 AND p.prm_accion IN ('CREAR', 'VER', 'APROBAR', 'ANULAR')
 AND p.estado_prm = 'ACT'
WHERE t.nombre = 'ADMINISTRADOR'
   OR (
       p.prm_modulo = substring(t.nombre from position('_' in t.nombre) + 1)
       AND (
           p.prm_accion = 'VER'
           OR (split_part(t.nombre, '_', 1) = 'JEFE' AND p.prm_accion = 'ANULAR')
           OR (split_part(t.nombre, '_', 1) = 'AUXILIAR' AND p.prm_accion = 'APROBAR')
           OR (split_part(t.nombre, '_', 1) = 'OPERATIVO' AND p.prm_accion = 'CREAR')
       )
   );

DO $$
BEGIN
    IF (SELECT count(*) FROM licoreria_permisos_matriz) <> 50 THEN
        RAISE EXCEPTION 'La matriz generada no contiene las 50 asignaciones esperadas.';
    END IF;
END $$;

UPDATE public.rolesxpermisos rp
SET estado_rxp = 'INA'
FROM public.roles r
JOIN licoreria_roles_matriz t ON t.nombre = upper(trim(r.rol_nombre))
WHERE rp.id_rol = r.id_rol
  AND t.nombre <> 'ADMINISTRADOR'
  AND rp.estado_rxp IS DISTINCT FROM 'INA'
  AND NOT EXISTS (
      SELECT 1 FROM licoreria_permisos_matriz e
      WHERE e.id_rol = rp.id_rol AND e.id_permiso = rp.id_permiso
  );

INSERT INTO public.rolesxpermisos (id_rol, id_permiso, estado_rxp)
SELECT id_rol, id_permiso, 'ACT' FROM licoreria_permisos_matriz
ON CONFLICT (id_rol, id_permiso) DO UPDATE SET estado_rxp = EXCLUDED.estado_rxp
WHERE public.rolesxpermisos.estado_rxp IS DISTINCT FROM EXCLUDED.estado_rxp;

COMMIT;
