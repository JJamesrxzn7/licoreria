#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
PRÁCTICA DE ARQUITECTURA DE BASES DE DATOS - PREGUNTA 3
Benchmark en Vivo: Speed-up, Scale-up, Particionamiento en BD vs. Scale-out en SI
Proyecto: Licorería La Cava | Motor: MariaDB 11.x (localhost:3307/licoreriadatabase)
Ejecutar:
    C:\\Users\\Jeremy\\AppData\\Local\\Python\\bin\\python3.14.exe docs/practica_arquitectura/benchmark_p3_escalabilidad.py
=============================================================================
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
import mysql.connector

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_CONFIG = {
    "host": "localhost",
    "port": 3307,
    "user": "root",
    "password": "1597.MyHql",
    "database": "licoreriadatabase",
}

# Conjunto de consultas mixtas (Transaccionales OLTP + Particionadas con Pruning)
QUERIES_BENCHMARK = [
    # 1. Consulta con Partition Pruning por Rango (lee únicamente la partición p_2025)
    """
    SELECT ciudad, COUNT(*) AS ventas, SUM(total_venta) AS ingresos
    FROM demo_ventas_rango
    WHERE fecha_venta BETWEEN '2025-01-01' AND '2025-12-31'
    GROUP BY ciudad
    """,
    # 2. Consulta con Partition Pruning por Asociación Hash (lee únicamente la partición de sucursal 2)
    """
    SELECT id_producto, SUM(cantidad) AS unidades, SUM(total_venta) AS total
    FROM demo_ventas_hash
    WHERE id_sucursal_num = 2
    GROUP BY id_producto
    ORDER BY total DESC
    LIMIT 5
    """,
    # 3. Consulta Transaccional OLTP puntual sobre FACTURAS + PROXFAC + CLIENTES
    """
    SELECT f.id_Factura, c.cli_Nombre, f.fac_Fecha, f.fac_Total, COUNT(pf.id_Producto) AS items
    FROM facturas f
    INNER JOIN clientes c ON f.id_Cliente = c.id_Cliente
    INNER JOIN proxfac pf ON f.id_Factura = pf.id_Factura
    WHERE f.ESTADO_FAC = 'APR'
    GROUP BY f.id_Factura, c.cli_Nombre, f.fac_Fecha, f.fac_Total
    LIMIT 10
    """,
    # 4. Consulta sobre particionamiento Turno Rotativo (Round-Robin)
    """
    SELECT id_transaccion, fecha_venta, ciudad, total_venta
    FROM demo_ventas_rotativo
    WHERE id_transaccion IN (101, 502, 1003, 2504, 5001, 7502, 9999)
    """,
]


def worker_task(num_queries: int, worker_id: int) -> int:
    """Ejecuta un lote de consultas reales abriendo su propia sesión/hilo contra MariaDB."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    executed = 0
    try:
        for i in range(num_queries):
            q = QUERIES_BENCHMARK[(i + worker_id) % len(QUERIES_BENCHMARK)]
            cur.execute(q)
            cur.fetchall()
            executed += 1
    finally:
        cur.close()
        conn.close()
    return executed


def run_workload(total_queries: int, num_workers: int) -> float:
    """Reparte `total_queries` entre `num_workers` hilos concurrentes y mide el tiempo total (segundos)."""
    base = total_queries // num_workers
    rem = total_queries % num_workers
    chunks = [base + (1 if i < rem else 0) for i in range(num_workers)]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker_task, chunks[i], i) for i in range(num_workers)]
        for f in futures:
            f.result()
    t1 = time.perf_counter()
    return t1 - t0


def mostrar_particiones_y_pruning():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    print("\n" + "=" * 88)
    print(" 1. VERIFICACIÓN DE MECANISMOS DE PARTICIONAMIENTO FÍSICO EN MARIADB (10,000 FILAS C/U)")
    print("=" * 88)
    cur.execute("""
        SELECT TABLE_NAME, PARTITION_NAME, PARTITION_METHOD, PARTITION_EXPRESSION, TABLE_ROWS
        FROM information_schema.PARTITIONS
        WHERE TABLE_SCHEMA = 'licoreriadatabase' AND TABLE_NAME LIKE 'demo_ventas_%'
        ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION
    """)
    print(f"{'TABLA':<24} | {'PARTICIÓN':<10} | {'MÉTODO':<8} | {'EXPRESIÓN':<22} | {'FILAS':>8}")
    print("-" * 88)
    for r in cur.fetchall():
        print(f"{r[0]:<24} | {r[1]:<10} | {r[2]:<8} | {str(r[3]):<22} | {r[4]:>8}")

    print("\n" + "-" * 88)
    print(" Demostración de PARTITION PRUNING (Poda de Particiones con EXPLAIN PARTITIONS):")
    print("-" * 88)
    pruning_demos = [
        (
            "Rango (Año 2025 -> solo lee p_2025)",
            "EXPLAIN PARTITIONS SELECT COUNT(*), SUM(total_venta) FROM demo_ventas_rango WHERE fecha_venta BETWEEN '2025-01-01' AND '2025-12-31'"
        ),
        (
            "Asociación/Hash (Sucursal 2 -> solo lee p2)",
            "EXPLAIN PARTITIONS SELECT COUNT(*), SUM(total_venta) FROM demo_ventas_hash WHERE id_sucursal_num = 2"
        ),
        (
            "Turno Rotativo (Transacción #2501 -> 2501 mod 4 = 1 -> solo lee p1)",
            "EXPLAIN PARTITIONS SELECT * FROM demo_ventas_rotativo WHERE id_transaccion = 2501"
        ),
    ]
    for titulo, sql in pruning_demos:
        cur.execute(sql)
        row = cur.fetchone()
        # En MariaDB EXPLAIN PARTITIONS devuelve: id, select_type, table, partitions, type, possible_keys, key, ...
        part_leida = row[3]
        tipo_acceso = row[4]
        rows_est = row[9]
        print(f"  * {titulo:<64} -> Partición física leída: [{part_leida}] (filas escaneadas: ~{rows_est})")

    cur.close()
    conn.close()


def benchmark_speedup():
    print("\n" + "=" * 88)
    print(" 2. BENCHMARK DE SPEED-UP (ACELERACIÓN): CARGA FIJA = 1,000 CONSULTAS, RECURSOS 1 -> 4 -> 8")
    print("    Fórmula: Speed-up(N) = T(1) / T(N)  |  Eficiencia(N) = Speed-up(N) / N")
    print("=" * 88)
    fixed_load = 1000
    workers_list = [1, 4, 8]
    results = {}

    # Warm-up del pool/buffer
    run_workload(20, 2)

    for n in workers_list:
        elapsed = run_workload(fixed_load, n)
        results[n] = elapsed

    t1 = results[1]
    print(f"{'HILOS (N)':<12} | {'CARGA FIJA':<14} | {'TIEMPO T(N)':<14} | {'SPEED-UP REAL':<15} | {'SPEED-UP IDEAL':<15} | {'EFICIENCIA':<10}")
    print("-" * 88)
    for n in workers_list:
        tn = results[n]
        speedup = t1 / tn if tn > 0 else 0.0
        eficiencia = (speedup / n) * 100.0
        print(f"{n:<12} | {fixed_load:<14} | {tn:>10.4f} seg | {speedup:>12.2f}x   | {float(n):>12.2f}x   | {eficiencia:>8.1f} %")

    print("\n  [Interpretación Técnica]:")
    print("  El Speed-up es sub-lineal (< N) debido a la Ley de Amdahl y a que MariaDB opera en una")
    print("  arquitectura Shared-Memory (SMP): los N hilos comparten el mismo Buffer Pool, mutexes")
    print("  internos e I/O local, generando sobrecarga de coordinación al competir por los mismos núcleos.")


def benchmark_scaleup():
    print("\n" + "=" * 88)
    print(" 3. BENCHMARK DE SCALE-UP (AMPLIACIÓN): CARGA Y RECURSOS CRECEN PROPORCIONALMENTE (1x, 4x, 8x)")
    print("    Fórmula: Scale-up(N) = TPS(N) / TPS(1)  |  Tiempo por lote T(1, 1x) / T(N, Nx)")
    print("=" * 88)
    base_load = 200
    configs = [
        (1, base_load * 1),   # 1x: 200 tx con 1 worker
        (4, base_load * 4),   # 4x: 800 tx con 4 workers
        (8, base_load * 8),   # 8x: 1,600 tx con 8 workers
    ]
    results = []
    for n, load in configs:
        elapsed = run_workload(load, n)
        tps = load / elapsed if elapsed > 0 else 0.0
        results.append((n, load, elapsed, tps))

    t_base = results[0][2]
    tps_base = results[0][3]

    print(f"{'ESCALA':<8} | {'WORKERS':<9} | {'CARGA (TX)':<12} | {'TIEMPO TOTAL':<14} | {'THROUGHPUT (TPS)':<18} | {'ÍNDICE SCALE-UP (TIEMPO)'}")
    print("-" * 88)
    for n, load, elapsed, tps in results:
        scaleup_tiempo = t_base / elapsed if elapsed > 0 else 0.0
        factor_tps = tps / tps_base if tps_base > 0 else 0.0
        print(f"{f'{n}x':<8} | {n:<9} | {load:<12} | {elapsed:>10.4f} seg | {tps:>12.1f} tx/s | {scaleup_tiempo:>8.2f} (TPS: {factor_tps:.2f}x)")

    print("\n  [Interpretación Técnica]:")
    print("  - Scale-up Transaccional: Al cuadruplicar/octuplicar las peticiones concurrentes junto con")
    print("    los hilos de conexión, el Throughput total (TPS) se multiplica drásticamente y el tiempo")
    print("    de respuesta por lote se mantiene casi constante (cercano a 1.00 = escalabilidad saludable).")


def contraste_scaleout_si():
    print("\n" + "=" * 88)
    print(" 4. CONTRASTE: SCALE-OUT EN LA CAPA DE APLICACIONES (SI) vs. CAPA DE BASE DE DATOS (DBMS)")
    print("=" * 88)
    print("  * Capa de Aplicaciones del SI (Backend FastAPI Stateless):")
    print("    - Es 100% STATELESS (sin estado en RAM local: autentica con JWT y delega estado a la BD).")
    print("    - Hacer SCALE-OUT horizontal es trivial: basta con levantar N procesos/contenedores clones:")
    print("        Instancia 1 -> uvicorn backend.main:app --port 8000")
    print("        Instancia 2 -> uvicorn backend.main:app --port 8001")
    print("  * Capa de Base de Datos (MariaDB InnoDB con estado compartido y garantías ACID):")
    print("    - Aunque clonemos 10 instancias de FastAPI, TODAS golpean el MISMO Buffer Pool, el MISMO")
    print("      Redo Log (ib_logfile0) y los MISMOS archivos .ibd en disco.")
    print("    - Por ello, escalar la BD horizontalmente (Scale-out) exige PARTICIONAMIENTO FÍSICO")
    print("      (Rango, Hash/Asociación o Turno Rotativo) para dividir los datos y evitar cuellos de botella.")
    print("=" * 88 + "\n")


if __name__ == "__main__":
    print("\n*** INICIANDO DEMOSTRACIÓN EN VIVO - PREGUNTA 3 (ESCALABILIDAD Y PARTICIONAMIENTO) ***")
    t_start = time.perf_counter()
    mostrar_particiones_y_pruning()
    benchmark_speedup()
    benchmark_scaleup()
    contraste_scaleout_si()
    print(f"*** DEMOSTRACIÓN FINALIZADA EN {time.perf_counter() - t_start:.2f} SEGUNDOS ***\n")
