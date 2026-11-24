"""
Construye el ERP completo en una sede MariaDB nueva copiando el modelo de Guayaquil (tu ERP original):

  1. Estructura: tablas y vistas (sin las tablas demo_/dwh_ que solo existen en la central).
  2. Catálogos con datos (productos, clientes, proveedores, empleados, usuarios, roles, plan de cuentas…).
  3. Lógica: triggers, procedimientos y funciones (después de los datos, para que copiar catálogos no ensucie el log).
  4. Auditoría total (erp_sedes.aplicar_auditoria) con log_Sede = la sede.

No borra nada existente: crea la base nueva (por defecto `lacava_quito`). Si ya existe, se detiene.

Uso:  python API/erp_construir_sede_mariadb.py QUITO [--reemplazar]
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import erp_sedes

BIN = Path(r"C:\Program Files\MariaDB 12.3\bin")
ORIGEN = erp_sedes.SEDES_MARIADB["GUAYAQUIL"]


def _dump(args: list[str], tablas: list[str] | None = None) -> str:
    env = {**os.environ, "MYSQL_PWD": erp_sedes.MARIADB_PASS}
    r = subprocess.run([str(BIN / "mariadb-dump.exe"), "-h", ORIGEN["host"], "-P", str(ORIGEN["port"]), "-u", "root",
                        "--skip-comments", "--default-character-set=utf8mb4", *args, ORIGEN["database"], *(tablas or [])],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode != 0:
        raise SystemExit(f"mariadb-dump falló: {r.stderr[:400]}")
    # Sin DEFINER: los objetos quedan a nombre del usuario que los crea en la sede
    return re.sub(r"/\*!50017 DEFINER=`[^`]+`@`[^`]+`\*/\s*|DEFINER=`[^`]+`@`[^`]+`\s*", "", r.stdout)


def _aplicar(sede: str, sql: str, etiqueta: str) -> None:
    cfg = erp_sedes.SEDES_MARIADB[sede]
    env = {**os.environ, "MYSQL_PWD": erp_sedes.MARIADB_PASS}
    r = subprocess.run([str(BIN / "mariadb.exe"), "-h", cfg["host"], "-P", str(cfg["port"]), "-u", "root",
                        "--default-character-set=utf8mb4", cfg["database"]],
                       input=sql, capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode != 0:
        raise SystemExit(f"[{etiqueta}] falló en {sede}: {r.stderr[:600]}")
    print(f"  [OK] {etiqueta}")


def construir(sede: str, reemplazar: bool) -> None:
    cfg = erp_sedes.SEDES_MARIADB[sede]
    conn = erp_sedes.conectar_mariadb(sede, database="mysql")
    cur = conn.cursor()
    cur.execute("SHOW DATABASES LIKE %s", (cfg["database"],))
    if cur.fetchone():
        if not reemplazar:
            raise SystemExit(f"La base {cfg['database']} ya existe en {sede}. Usa --reemplazar para recrearla.")
        cur.execute(f"DROP DATABASE `{cfg['database']}`")
    cur.execute(f"CREATE DATABASE `{cfg['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_uca1400_ai_ci")
    cur.close()
    conn.close()
    print(f"Base {cfg['database']} creada en {sede} ({cfg['host']}:{cfg['port']})")

    ignorar = [f"--ignore-table={ORIGEN['database']}.{t}" for t in erp_sedes.SOLO_CENTRAL]
    estructura = _dump(["--no-data", "--skip-triggers", *ignorar])
    # Las vistas que dependen de tablas solo-central no aplican en la sede
    _aplicar(sede, "SET FOREIGN_KEY_CHECKS=0;\n" + estructura, "estructura: tablas y vistas")

    catalogos = _dump(["--no-create-info", "--skip-triggers", "--complete-insert"], erp_sedes.CATALOGOS)
    _aplicar(sede, "SET FOREIGN_KEY_CHECKS=0;\n" + catalogos, f"catálogos ({len(erp_sedes.CATALOGOS)} tablas)")

    logica = _dump(["--no-data", "--no-create-info", "--routines", "--triggers", "--skip-opt", *ignorar])
    _aplicar(sede, logica, "triggers, procedimientos y funciones")

    hechas = erp_sedes.aplicar_auditoria(sede)
    print(f"  [OK] auditoría total ({len(hechas)} sentencias, log_Sede = {sede})")


if __name__ == "__main__":
    construir(sys.argv[1].upper(), "--reemplazar" in sys.argv)
