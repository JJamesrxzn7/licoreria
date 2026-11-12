from getpass import getpass

import mysql.connector

from main import database_backend, get_db_config, hash_password


def main() -> int:
    if database_backend() == "postgresql":
        print("El restablecimiento para PostgreSQL aún no está disponible. No se modificó ninguna base de datos.")
        return 1
    username = input("Nombre de usuario a recuperar: ").strip()
    if not username:
        print("Debes indicar el nombre de usuario.")
        return 1

    password = getpass("Nueva contraseña (8 a 100 caracteres): ")
    if not 8 <= len(password) <= 100:
        print("La contraseña debe tener entre 8 y 100 caracteres.")
        return 1
    if password != getpass("Confirma la nueva contraseña: "):
        print("Las contraseñas no coinciden.")
        return 1
    if input(f"¿Restablecer la contraseña de '{username}'? [s/N]: ").strip().lower() != "s":
        print("Operación cancelada.")
        return 1

    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(**get_db_config())
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id_Usuario FROM USUARIOS WHERE usr_Username = %s LIMIT 2",
            (username,),
        )
        matches = cursor.fetchall()
        if len(matches) != 1:
            print("No se encontró exactamente una cuenta con ese nombre. No se hicieron cambios.")
            return 1

        cursor.execute(
            """
            UPDATE USUARIOS
            SET usr_PasswordHash = %s, usr_IntentosFallidos = 0
            WHERE usr_Username = %s
            """,
            (hash_password(password), username),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            print("No se pudo actualizar la cuenta. No se hicieron cambios.")
            return 1

        connection.commit()
        print("Contraseña restablecida. Ya puedes iniciar sesión con la nueva contraseña.")
        return 0
    except mysql.connector.Error as error:
        if connection and connection.is_connected():
            connection.rollback()
        print(f"No se pudo conectar o actualizar la cuenta (error {error.errno}). Revisa la configuración local de la API.")
        return 1
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
