-- MariaDB. Ejecutar por separado con un cliente que admita DELIMITER, sin --force.
-- Este rol permite leer, insertar, actualizar y borrar datos en esta base,
-- y consultar definiciones de vistas. NO concede DROP, ALTER, CREATE,
-- TRIGGER, EVENT, EXECUTE, GRANT OPTION ni administracion de cuentas.
-- DELETE y UPDATE pueden eliminar o alterar todos los registros, incluso las
-- tablas de usuarios y permisos de la aplicacion. No protege contra ello.
-- CREATE ROLE falla si el nombre ya existe: no se reutiliza un rol que podria
-- tener privilegios adicionales. No ejecutar el GRANT por separado tras un error.
-- CREATE ROLE y GRANT hacen commit implicito: no son reversibles con ROLLBACK.
DELIMITER //
BEGIN NOT ATOMIC
    CREATE ROLE licoreria_dba_limitado;
    GRANT SELECT, INSERT, UPDATE, DELETE, SHOW VIEW
        ON licoreriadatabase.* TO licoreria_dba_limitado;
END //
DELIMITER ;

SHOW GRANTS FOR licoreria_dba_limitado;

-- Asignacion opcional posterior, realizada por un administrador, sustituyendo
-- los marcadores por una cuenta ya existente y verificando sus privilegios:
-- SHOW GRANTS FOR 'usuario_dba'@'localhost';
-- GRANT licoreria_dba_limitado TO 'usuario_dba'@'localhost';
-- SET DEFAULT ROLE licoreria_dba_limitado FOR 'usuario_dba'@'localhost';
-- SHOW GRANTS FOR 'usuario_dba'@'localhost';
--
-- Los privilegios se suman: el rol NO revoca privilegios directos, globales ni
-- otros roles. Verifique SHOW GRANTS de la cuenta y de todos sus roles antes
-- de asignarlo. Tampoco use una cuenta root o con EXECUTE sobre rutinas
-- privilegiadas. La cuenta de la API es independiente de este rol.
