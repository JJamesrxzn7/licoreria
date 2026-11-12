-- MariaDB. Ejecutar en una conexion dedicada, con un cliente que admita
-- DELIMITER y se detenga ante errores (sin --force).
-- Requiere el catalogo existente de roles y permisos y una copia de seguridad.
-- Este script no crea usuarios ni asigna roles a usuarios.
-- Los permisos de multiples roles activos se suman.
-- Solo actualiza los 15 roles indicados y agrega permisos al Administrador;
-- no modifica otros roles, como SuperAdministrador o los roles heredados.
-- La API debe comprobar estas autorizaciones: el catalogo no las impone.
USE licoreriadatabase;

DELIMITER //
BEGIN NOT ATOMIC
    DECLARE v_roles_tmp_creada BOOLEAN DEFAULT FALSE;
    DECLARE v_permisos_tmp_creada BOOLEAN DEFAULT FALSE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        IF v_permisos_tmp_creada THEN
            DROP TEMPORARY TABLE tmp_licoreria_permisos_matriz;
        END IF;
        IF v_roles_tmp_creada THEN
            DROP TEMPORARY TABLE tmp_licoreria_roles_matriz;
        END IF;
        RESIGNAL;
    END;

    IF (SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND UPPER(TABLE_NAME) IN ('ROLES', 'PERMISOS', 'ROLESXPERMISOS', 'LOG_AUDITORIA')
          AND ENGINE = 'InnoDB') <> 4 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Se requieren las tablas de permisos y auditoria con motor InnoDB.';
    END IF;

    CREATE TEMPORARY TABLE tmp_licoreria_roles_matriz (
        nombre VARCHAR(50) NOT NULL PRIMARY KEY
    );
    SET v_roles_tmp_creada = TRUE;
    INSERT INTO tmp_licoreria_roles_matriz (nombre) VALUES
        ('Jefe_COMPRAS'), ('Auxiliar_COMPRAS'), ('Operativo_COMPRAS'),
        ('Jefe_INVENTARIOS'), ('Auxiliar_INVENTARIOS'), ('Operativo_INVENTARIOS'),
        ('Jefe_VENTAS'), ('Auxiliar_VENTAS'), ('Operativo_VENTAS'),
        ('Jefe_TALENTO_HUMANO'), ('Auxiliar_TALENTO_HUMANO'), ('Operativo_TALENTO_HUMANO'),
        ('Jefe_CONTABILIDAD'), ('Auxiliar_CONTABILIDAD'), ('Operativo_CONTABILIDAD'),
        ('Administrador');

    IF (SELECT COUNT(*) FROM ROLES r
        JOIN tmp_licoreria_roles_matriz t ON t.nombre = r.rol_Nombre) <> 16
       OR (SELECT COUNT(DISTINCT t.nombre) FROM ROLES r
           JOIN tmp_licoreria_roles_matriz t ON t.nombre = r.rol_Nombre
           WHERE r.ESTADO_ROL = 'ACT') <> 16 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Faltan roles, estan inactivos o sus nombres estan duplicados.';
    END IF;

    IF (SELECT COUNT(*) FROM PERMISOS
        WHERE prm_Modulo IN ('COMPRAS', 'INVENTARIOS', 'VENTAS', 'TALENTO_HUMANO', 'CONTABILIDAD')
          AND prm_Accion IN ('CREAR', 'VER', 'APROBAR', 'ANULAR')) <> 20
       OR (SELECT COUNT(DISTINCT prm_Modulo, prm_Accion) FROM PERMISOS
           WHERE prm_Modulo IN ('COMPRAS', 'INVENTARIOS', 'VENTAS', 'TALENTO_HUMANO', 'CONTABILIDAD')
             AND prm_Accion IN ('CREAR', 'VER', 'APROBAR', 'ANULAR')
             AND ESTADO_PRM = 'ACT') <> 20 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Faltan permisos, estan inactivos o existen permisos duplicados.';
    END IF;

    CREATE TEMPORARY TABLE tmp_licoreria_permisos_matriz (
        id_Rol CHAR(10) NOT NULL,
        id_Permiso CHAR(10) NOT NULL,
        PRIMARY KEY (id_Rol, id_Permiso)
    );
    SET v_permisos_tmp_creada = TRUE;
    INSERT INTO tmp_licoreria_permisos_matriz (id_Rol, id_Permiso)
    SELECT r.id_Rol, p.id_Permiso
    FROM ROLES r
    JOIN tmp_licoreria_roles_matriz t ON t.nombre = r.rol_Nombre
    JOIN PERMISOS p
      ON p.prm_Modulo IN ('COMPRAS', 'INVENTARIOS', 'VENTAS', 'TALENTO_HUMANO', 'CONTABILIDAD')
     AND p.prm_Accion IN ('CREAR', 'VER', 'APROBAR', 'ANULAR')
     AND p.ESTADO_PRM = 'ACT'
    WHERE r.rol_Nombre = 'Administrador'
       OR (
            p.prm_Modulo = SUBSTRING(r.rol_Nombre, LOCATE('_', r.rol_Nombre) + 1)
            AND (
                p.prm_Accion = 'VER'
                OR (SUBSTRING_INDEX(r.rol_Nombre, '_', 1) = 'Jefe' AND p.prm_Accion = 'ANULAR')
                OR (SUBSTRING_INDEX(r.rol_Nombre, '_', 1) = 'Auxiliar' AND p.prm_Accion = 'APROBAR')
                OR (SUBSTRING_INDEX(r.rol_Nombre, '_', 1) = 'Operativo' AND p.prm_Accion = 'CREAR')
            )
       );

    IF (SELECT COUNT(*) FROM tmp_licoreria_permisos_matriz) <> 50 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'La matriz generada no contiene las 50 asignaciones esperadas.';
    END IF;

    START TRANSACTION;

    -- Desactivar cualquier permiso adicional de los 15 roles de modulo.
    -- El Administrador conserva los permisos adicionales que ya tenga.
    UPDATE ROLESxPERMISOS rp
    JOIN ROLES r ON r.id_Rol = rp.id_Rol
    JOIN tmp_licoreria_roles_matriz t ON t.nombre = r.rol_Nombre
    LEFT JOIN tmp_licoreria_permisos_matriz e
      ON e.id_Rol = rp.id_Rol AND e.id_Permiso = rp.id_Permiso
    SET rp.ESTADO_RxP = 'INA'
    WHERE r.rol_Nombre <> 'Administrador'
      AND e.id_Rol IS NULL
      AND (rp.ESTADO_RxP IS NULL OR rp.ESTADO_RxP <> 'INA');

    UPDATE ROLESxPERMISOS rp
    JOIN tmp_licoreria_permisos_matriz e
      ON e.id_Rol = rp.id_Rol AND e.id_Permiso = rp.id_Permiso
    SET rp.ESTADO_RxP = 'ACT'
    WHERE rp.ESTADO_RxP IS NULL OR rp.ESTADO_RxP <> 'ACT';

    INSERT INTO ROLESxPERMISOS (id_Rol, id_Permiso, ESTADO_RxP)
    SELECT e.id_Rol, e.id_Permiso, 'ACT'
    FROM tmp_licoreria_permisos_matriz e
    LEFT JOIN ROLESxPERMISOS rp
      ON rp.id_Rol = e.id_Rol AND rp.id_Permiso = e.id_Permiso
    WHERE rp.id_Rol IS NULL;

    COMMIT;
    DROP TEMPORARY TABLE tmp_licoreria_permisos_matriz;
    SET v_permisos_tmp_creada = FALSE;
    DROP TEMPORARY TABLE tmp_licoreria_roles_matriz;
    SET v_roles_tmp_creada = FALSE;
END //
DELIMITER ;

-- Comprobacion de la matriz efectiva del catalogo.
SELECT r.rol_Nombre, p.prm_Modulo, p.prm_Accion
FROM ROLES r
JOIN ROLESxPERMISOS rp ON rp.id_Rol = r.id_Rol AND rp.ESTADO_RxP = 'ACT'
JOIN PERMISOS p ON p.id_Permiso = rp.id_Permiso AND p.ESTADO_PRM = 'ACT'
WHERE r.rol_Nombre IN (
    'Administrador',
    'Jefe_COMPRAS', 'Auxiliar_COMPRAS', 'Operativo_COMPRAS',
    'Jefe_INVENTARIOS', 'Auxiliar_INVENTARIOS', 'Operativo_INVENTARIOS',
    'Jefe_VENTAS', 'Auxiliar_VENTAS', 'Operativo_VENTAS',
    'Jefe_TALENTO_HUMANO', 'Auxiliar_TALENTO_HUMANO', 'Operativo_TALENTO_HUMANO',
    'Jefe_CONTABILIDAD', 'Auxiliar_CONTABILIDAD', 'Operativo_CONTABILIDAD'
)
ORDER BY r.rol_Nombre, p.prm_Modulo, p.prm_Accion;
