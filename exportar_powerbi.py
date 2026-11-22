"""
Exporta una FOTO FIJA del esquema estrella de BD 5 (`db_gye_dwh`, MariaDB :3309) a CSV en `powerbi_datos/`:
  dim_sede.csv, dim_producto.csv, dim_tiempo.csv, fact_ventas.csv (+ etl_control.csv si existe)

Es la alternativa sin API. Para datos en vivo usa `powerbi_datos/LaCava_PowerQuery.pq`
(ver `powerbi_datos/GUIA_POWER_BI.md`).

Credenciales: se leen de API/.env (BD5_GUAYAQUIL_DWH_*), con los mismos valores por defecto que la API.
"""

import csv
import os
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "powerbi_datos"
OUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(ROOT / "API" / ".env")
except ImportError:
    pass


def export_table(cur, table_name: str) -> None:
    cur.execute(f"SELECT * FROM {table_name}")
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    csv_path = OUT_DIR / f"{table_name}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)
    print(f"  [OK] {csv_path.name} ({len(rows)} filas)")


def main() -> None:
    conn = mysql.connector.connect(
        host="127.0.0.1",
        port=int(os.getenv("BD5_GUAYAQUIL_DWH_PORT", "3309")),
        user=os.getenv("BD5_GUAYAQUIL_DWH_USER", "root"),
        password=os.getenv("BD5_GUAYAQUIL_DWH_PASSWORD", os.getenv("MARIADB_PASSWORD", "1597.MyHql")),
        database=os.getenv("BD5_GUAYAQUIL_DWH_DATABASE", "db_gye_dwh"),
        use_pure=True,
    )
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    existentes = {r[0] for r in cur.fetchall()}
    for t in ("dim_sede", "dim_producto", "dim_tiempo", "fact_ventas", "etl_control"):
        if t in existentes:
            export_table(cur, t)
    cur.close()
    conn.close()
    print(f"  Listo. Abre Power BI -> Obtener datos -> Texto/CSV -> {OUT_DIR}")


if __name__ == "__main__":
    main()
