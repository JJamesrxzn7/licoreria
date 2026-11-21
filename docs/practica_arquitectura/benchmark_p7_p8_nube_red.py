"""
DEMOSTRACIÓN EN VIVO — PREGUNTAS 7 y 8 (ARQUITECTURA DE BASES DE DATOS)
Proyecto: Licorería La Cava
- Pregunta 7: Paradigmas Cloud (DBaaS vs. IaaS/PaaS/SaaS), Control del Sistema y Vendor Lock-in
- Pregunta 8: Topologías de Red (Bus, Malla, Hipercubo, Árbol), Interconexión Física
              (Infiniband / SAN) e impacto de Latencia (RTT) y Ancho de Banda en la UX.

Ejecución:
  C:\\Users\\Jeremy\\AppData\\Local\\Python\\bin\\python3.14.exe docs/practica_arquitectura/benchmark_p7_p8_nube_red.py
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import socket
import sys
import time
import mysql.connector

# Forzar salida UTF-8 en consola Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[2]
MARIADB_CONFIG = {
    "host": "localhost",
    "port": 3307,
    "user": "root",
    "password": "1597.MyHql",
    "database": "licoreriadatabase",
}


def print_banner(title: str) -> None:
    print("\n" + "=" * 92)
    print(f"  {title}")
    print("=" * 92)


def get_connection():
    return mysql.connector.connect(**MARIADB_CONFIG)


# =========================================================================
# 1. DEMOSTRACIÓN PREGUNTA 7: INSPECCIÓN CLOUD (PaaS + DBaaS) Y VENDOR LOCK-IN
# =========================================================================
def demo_p7_cloud_and_vendor_lockin(conn) -> None:
    print_banner(
        "PREGUNTA 7: PARADIGMAS CLOUD (IaaS / DBaaS / PaaS / SaaS), CONTROL Y VENDOR LOCK-IN"
    )

    render_yaml_path = ROOT_DIR / "render.yaml"
    ca_cert_path = ROOT_DIR / "API" / "prod-ca-2021.crt"
    env_path = ROOT_DIR / "API" / ".env"
    pg_conn_path = ROOT_DIR / "API" / "postgres_connection.py"
    migrations_dir = ROOT_DIR / "API" / "migrations"

    # Extraer host de Supabase desde API/.env
    supabase_host = "aws-0-us-east-1.pooler.supabase.com"
    supabase_port = 5432
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("SUPABASE_SCHEMA_HOST="):
                supabase_host = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("SUPABASE_SCHEMA_PORT="):
                try:
                    supabase_port = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass

    # Detectar servicios PaaS en render.yaml
    paas_services = []
    if render_yaml_path.is_file():
        for line in render_yaml_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("name:"):
                svc_name = stripped.split("name:", 1)[1].strip()
                if svc_name not in paas_services:
                    paas_services.append(svc_name)

    # Contar migraciones PostgreSQL
    pg_migrations = sorted(migrations_dir.glob("*_postgresql.sql")) if migrations_dir.is_dir() else []

    # Consultar MariaDB local (IaaS / On-Premise)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT VARIABLE_NAME, VARIABLE_VALUE
        FROM information_schema.GLOBAL_VARIABLES
        WHERE VARIABLE_NAME IN ('VERSION', 'DATADIR', 'INNODB_BUFFER_POOL_SIZE', 'VERSION_COMPILE_OS')
        """
    )
    vars_local = {k.upper(): v for k, v in cur.fetchall()}

    cur.execute(
        """
        SELECT ROUTINE_TYPE, COUNT(*)
        FROM information_schema.ROUTINES
        WHERE ROUTINE_SCHEMA = DATABASE()
        GROUP BY ROUTINE_TYPE
        """
    )
    routines = dict(cur.fetchall())
    sp_count = routines.get("PROCEDURE", 0)
    fn_count = routines.get("FUNCTION", 0)

    cur.execute(
        "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()"
    )
    trg_count = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE()"
    )
    view_count = cur.fetchone()[0]

    print("[7.1] Diagnóstico en Vivo de la Arquitectura Híbrida del Proyecto:")
    print(
        f"  • Capa IaaS / On-Premise (MariaDB Local :{MARIADB_CONFIG['port']}):"
    )
    print(
        f"    - Motor y SO       : MariaDB {vars_local.get('VERSION', '?')} sobre {vars_local.get('VERSION_COMPILE_OS', '?')}"
    )
    print(
        f"    - Acceso Filesystem: datadir = {vars_local.get('DATADIR', '?')} (Control físico total del DBA)"
    )
    print(
        f"    - Buffer Pool RAM  : {int(vars_local.get('INNODB_BUFFER_POOL_SIZE', 0)) // (1024 * 1024)} MB configurables por el DBA"
    )
    print(
        f"  • Capa DBaaS (Supabase PostgreSQL Cloud):"
    )
    print(
        f"    - Endpoint Pooler  : {supabase_host}:{supabase_port} (Región AWS us-east-1 Virginia)"
    )
    print(
        f"    - Certificado TLS  : {ca_cert_path.relative_to(ROOT_DIR)} "
        f"({'EXISTE (' + str(ca_cert_path.stat().st_size) + ' bytes)' if ca_cert_path.is_file() else 'NO ENCONTRADO'})"
    )
    print(
        f"    - Guardián de Rol  : {pg_conn_path.relative_to(ROOT_DIR)} -> Bloquea rolsuper, rolbypassrls y rolcreatedb"
    )
    print(
        f"  • Capa PaaS (Render Blueprint - {render_yaml_path.name}):"
    )
    print(
        f"    - Servicios PaaS   : {', '.join(paas_services)} (healthCheckPath: /readyz)"
    )
    print(
        f"  • Capa SaaS (Aplicación Final):"
    )
    print(
        f"    - Licorería La Cava Web consumida por cajeros/gerentes desde el navegador vía HTTPS."
    )

    print("\n[7.2] Cuantificación Real de VENDOR LOCK-IN en Nuestra Capa de Datos:")
    print(
        f"  ┌──────────────────────────────────────────────┬───────────────┬───────────────────────────────────────────────────┐"
    )
    print(
        f"  │ Objeto Programado en el Motor                │ En MariaDB    │ Impacto de Vendor Lock-in al migrar a Supabase PG │"
    )
    print(
        f"  ├──────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────┤"
    )
    print(
        f"  │ Procedimientos Almacenados (SQL/PSM)         │ {sp_count:>13} │ Reescritura a PL/pgSQL + transacciones explícitas │"
    )
    print(
        f"  │ Funciones Almacenadas (SQL/PSM)              │ {fn_count:>13} │ Reescritura de sintaxis y tipos de retorno        │"
    )
    print(
        f"  │ Triggers (TRG_AUD_* y lógica de negocio)     │ {trg_count:>13} │ PG exige FUNCTION RETURNS trigger + CREATE TRIGGER│"
    )
    print(
        f"  │ Vistas del Esquema (VW_*)                    │ {view_count:>13} │ Adaptación de tipos, collations y RLS subyacente  │"
    )
    print(
        f"  └──────────────────────────────────────────────┴───────────────┴───────────────────────────────────────────────────┘"
    )
    print(
        f"  -> Total objetos acoplados al motor local: {sp_count + fn_count + trg_count + view_count} objetos."
    )
    print(
        f"  -> Migraciones PostgreSQL reescritas en API/migrations/: {len(pg_migrations)} archivos SQL:"
    )
    for m in pg_migrations:
        print(f"     * {m.name}")
    cur.close()
    return supabase_host, supabase_port


# =========================================================================
# 2. DEMOSTRACIÓN PREGUNTA 8 (EXP 1): LATENCIA FÍSICA (RTT) Y PROBLEMA N+1
# =========================================================================
def measure_supabase_tcp_rtt(host: str, port: int) -> tuple[float, bool]:
    """Mide en vivo el RTT TCP hacia aws-0-us-east-1.pooler.supabase.com:5432."""
    samples = []
    for _ in range(2):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=1.5):
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                samples.append(rtt_ms)
        except OSError:
            break
    if samples:
        return sum(samples) / len(samples), True
    # Fallback realista Ecuador <-> us-east-1 Virginia si no hay internet en el aula
    return 85.0, False


def demo_p8_latency_n_plus_1(conn, supabase_host: str, supabase_port: int) -> None:
    print_banner(
        "PREGUNTA 8 (EXPERIMENTO 1): LATENCIA DE RED (RTT) Y EL PROBLEMA N+1 EN LA NUBE"
    )

    cur = conn.cursor()

    # Warm-up
    cur.execute("SELECT COUNT(*) FROM facturas")
    cur.fetchall()

    # A) Medición en vivo del Patrón N+1 (1 query de facturas + 40 queries de proxfac = 41 viajes)
    t0 = time.perf_counter()
    cur.execute(
        "SELECT id_Factura, id_Cliente, fac_Fecha, fac_Total, ESTADO_FAC FROM facturas ORDER BY id_Factura"
    )
    facturas = cur.fetchall()
    total_detalles_n1 = 0
    for fac in facturas:
        id_fac = fac[0]
        cur.execute(
            "SELECT id_Producto, pxf_Cantidad, pxf_Precio, pxf_Subtotal FROM proxfac WHERE id_Factura = %s",
            (id_fac,),
        )
        detalles = cur.fetchall()
        total_detalles_n1 += len(detalles)
    elapsed_n1_local_ms = (time.perf_counter() - t0) * 1000.0
    round_trips_n1 = 1 + len(facturas)

    # B) Medición en vivo del Patrón Conjunto (1 solo viaje con JOIN)
    t1 = time.perf_counter()
    cur.execute(
        """
        SELECT f.id_Factura, f.id_Cliente, f.fac_Fecha, f.fac_Total, f.ESTADO_FAC,
               pf.id_Producto, pf.pxf_Cantidad, pf.pxf_Precio, pf.pxf_Subtotal
        FROM facturas f
        JOIN proxfac pf ON pf.id_Factura = f.id_Factura
        ORDER BY f.id_Factura
        """
    )
    rows_join = cur.fetchall()
    elapsed_join_local_ms = (time.perf_counter() - t1) * 1000.0
    round_trips_join = 1

    # Medir RTT real hacia Supabase en Virginia (us-east-1)
    wan_rtt_ms, is_live_wan = measure_supabase_tcp_rtt(supabase_host, supabase_port)
    wan_status = (
        f"MEDIDO EN VIVO vía socket TCP a {supabase_host}:{supabase_port}"
        if is_live_wan
        else f"SIMULADO (Fallback sin internet hacia {supabase_host}:{supabase_port})"
    )

    print(
        f"  Operación de Negocio: Cargar listado de {len(facturas)} Facturas con sus {len(rows_join)} líneas de detalle (PROXFAC)."
    )
    print(
        f"  • Medición Localhost (:3307) — Patrón N+1 ({round_trips_n1} Round-Trips) : {elapsed_n1_local_ms:6.2f} ms"
    )
    print(
        f"  • Medición Localhost (:3307) — 1 Solo JOIN ({round_trips_join} Round-Trip)  : {elapsed_join_local_ms:6.2f} ms"
    )
    print(f"  • Latencia WAN (RTT) Ecuador <-> AWS us-east-1 : {wan_rtt_ms:6.2f} ms ({wan_status})")

    # Tabla comparativa en distintos medios físicos de interconexión
    # Tiempo total = Tiempo de motor base + (RoundTrips * RTT_medio)
    engine_base_join_ms = max(0.4, elapsed_join_local_ms * 0.5)
    engine_base_n1_ms = max(1.5, elapsed_n1_local_ms * 0.4)

    interconexiones = [
        ("1. Infiniband HDR / RDMA (Clúster Paralelo)", 0.002, "200 Gbps"),
        ("2. SAN Fibre Channel / NVMe-oF (Shared-Disk)", 0.050, "32-64 Gbps"),
        ("3. LAN Ethernet 1/10 Gbps (Servidor Local)", 0.400, "1-10 Gbps"),
        (f"4. WAN Cloud Ecuador <-> Supabase us-east-1", wan_rtt_ms, "50-100 Mbps"),
    ]

    print("\n  Proyección Física del Tiempo de Respuesta según la Interconexión de Red:")
    print(
        "  ┌──────────────────────────────────────────────┬───────────┬─────────────┬────────────────┬────────────────┬──────────────────────┐"
    )
    print(
        "  │ Medio Físico / Interconexión de BD           │ RTT (ms)  │ Ancho Banda │ 1 JOIN (1 RTT) │ N+1 (41 RTTs)  │ Impacto en UX React  │"
    )
    print(
        "  ├──────────────────────────────────────────────┼───────────┼─────────────┼────────────────┼────────────────┼──────────────────────┤"
    )
    for nombre, rtt, bw in interconexiones:
        t_join = engine_base_join_ms + (round_trips_join * rtt)
        t_n1 = engine_base_n1_ms + (round_trips_n1 * rtt)
        if t_n1 < 50:
            ux = "Instantáneo (<50ms)"
        elif t_n1 < 250:
            ux = "Fluido (<250ms)"
        elif t_n1 < 1000:
            ux = "Lento (Perceptible)"
        else:
            ux = f"CRÍTICO ({t_n1/1000:.2f} seg!)"
        print(
            f"  │ {nombre:<44} │ {rtt:>9.3f} │ {bw:<11} │ {t_join:>11.2f} ms │ {t_n1:>11.2f} ms │ {ux:<20} │"
        )
    print(
        "  └──────────────────────────────────────────────┴───────────┴─────────────┴────────────────┴────────────────┴──────────────────────┘"
    )
    print(
        f"  -> CONCLUSIÓN P8.1: En desarrollo local el problema N+1 se esconde ({elapsed_n1_local_ms:.1f} ms), pero al desplegar"
    )
    print(
        f"     en DBaaS Cloud (RTT={wan_rtt_ms:.1f} ms), 41 viajes de red suman {41 * wan_rtt_ms:.0f} ms ({41 * wan_rtt_ms / 1000:.2f} s) bloqueando al usuario."
    )
    cur.close()


# =========================================================================
# 3. DEMOSTRACIÓN PREGUNTA 8 (EXP 2): IMPACTO DEL ANCHO DE BANDA (10,000 FILAS)
# =========================================================================
def demo_p8_bandwidth_payload(conn) -> None:
    print_banner(
        "PREGUNTA 8 (EXPERIMENTO 2): IMPACTO DEL ANCHO DE BANDA (10,000 FILAS vs. AGREGACIÓN EN MOTOR)"
    )

    cur = conn.cursor()

    def get_bytes_sent() -> int:
        cur.execute(
            "SELECT VARIABLE_VALUE FROM information_schema.SESSION_STATUS WHERE VARIABLE_NAME = 'BYTES_SENT'"
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_STATUS WHERE VARIABLE_NAME = 'BYTES_SENT'"
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    # A) Anti-patrón: Traer las 10,000 filas completas de demo_ventas_rango por el socket TCP y sumar en Python
    b0 = get_bytes_sent()
    t0 = time.perf_counter()
    cur.execute(
        """
        SELECT id_transaccion, fecha_venta, id_sucursal_num, ciudad,
               id_cliente, id_producto, cantidad, precio_unitario, total_venta
        FROM demo_ventas_rango
        """
    )
    all_rows = cur.fetchall()
    totales_py = {}
    for r in all_rows:
        ciudad = r[3]
        monto = float(r[8])
        totales_py[ciudad] = totales_py.get(ciudad, 0.0) + monto
    elapsed_raw_ms = (time.perf_counter() - t0) * 1000.0
    bytes_raw = max(1, get_bytes_sent() - b0)

    # B) Patrón Optimizado: Agregar con GROUP BY dentro de MariaDB y transferir solo 3 filas por la red
    b1 = get_bytes_sent()
    t1 = time.perf_counter()
    cur.execute(
        """
        SELECT ciudad,
               COUNT(*) AS transacciones,
               SUM(cantidad) AS unidades,
               ROUND(SUM(total_venta), 2) AS total_usd
        FROM demo_ventas_rango
        GROUP BY ciudad
        ORDER BY total_usd DESC
        """
    )
    agg_rows = cur.fetchall()
    elapsed_agg_ms = (time.perf_counter() - t1) * 1000.0
    bytes_agg = max(1, get_bytes_sent() - b1)

    reduction_pct = (1.0 - (bytes_agg / bytes_raw)) * 100.0
    speedup = elapsed_raw_ms / max(0.01, elapsed_agg_ms)

    print(
        f"  Tabla analizada: `demo_ventas_rango` ({len(all_rows):,} filas históricas de ventas por ciudad)."
    )
    print(
        "  ┌────────────────────────────────────────────────────┬──────────────┬──────────────────┬────────────────┐"
    )
    print(
        "  │ Estrategia de Uso del Canal de Red (BD -> API)     │ Filas en Red │ Tráfico TCP Real │ Tiempo Total   │"
    )
    print(
        "  ├────────────────────────────────────────────────────┼──────────────┼──────────────────┼────────────────┤"
    )
    print(
        f"  │ 1. Anti-Patrón: SELECT * + Suma en Python          │ {len(all_rows):>12,} │ {bytes_raw:>10,} Bytes │ {elapsed_raw_ms:>11.2f} ms │"
    )
    print(
        f"  │ 2. Optimizado : SELECT GROUP BY en Motor MariaDB   │ {len(agg_rows):>12,} │ {bytes_agg:>10,} Bytes │ {elapsed_agg_ms:>11.2f} ms │"
    )
    print(
        "  └────────────────────────────────────────────────────┴──────────────┴──────────────────┴────────────────┘"
    )
    print(
        f"  -> Ahorro de Ancho de Banda en el canal físico : {reduction_pct:.2f}% menos bytes transmitidos ({bytes_raw / bytes_agg:.0f}x más liviano)."
    )
    print(
        f"  -> Aceleración medida en vivo                  : {speedup:.1f}x más rápido."
    )
    cur.close()


# =========================================================================
# 4. DEMOSTRACIÓN PREGUNTA 8 (EXP 3): TOPOLOGÍAS DE INTERCONEXIÓN FÍSICA
# =========================================================================
def demo_p8_topologies_table(n_nodes: int = 16) -> None:
    print_banner(
        f"PREGUNTA 8 (EXPERIMENTO 3): COMPARATIVA MATEMÁTICA DE TOPOLOGÍAS DE RED (Clúster N = {n_nodes} Nodos)"
    )

    d_hypercube = int(math.log2(n_nodes))
    d_tree = 2 * int(math.log2(n_nodes))

    topologias = [
        {
            "nombre": "1. Bus Común (Shared Bus)",
            "enlaces": "1 bus compartido",
            "grado": "1",
            "diametro": "1 (acceso directo)",
            "biseccion": "1 (Cuello de botella)",
            "fallos": "Crítica (Fallo único tumba todo)",
            "uso_bd": "Redes locales antiguas / Bus interno PCI",
        },
        {
            "nombre": "2. Árbol / Fat-Tree (Jerárquica)",
            "enlaces": f"N - 1 = {n_nodes - 1}",
            "grado": "3 (1 padre, 2 hijos)",
            "diametro": f"2·log2(N) = {d_tree} saltos",
            "biseccion": "1 (Árbol simple) / N/2 (Fat-Tree)",
            "fallos": "Media (Fallo en raíz particiona clúster)",
            "uso_bd": "Clos / Leaf-Spine en Datacenters Cloud (AWS/Render)",
        },
        {
            "nombre": f"3. Hipercubo (d = log2(N) = {d_hypercube}D)",
            "enlaces": f"(N·log2(N))/2 = {(n_nodes * d_hypercube) // 2}",
            "grado": f"log2(N) = {d_hypercube}",
            "diametro": f"log2(N) = {d_hypercube} saltos",
            "biseccion": f"N / 2 = {n_nodes // 2} enlaces",
            "fallos": f"Alta ({d_hypercube} rutas disjuntas entre nodos)",
            "uso_bd": "Clústeres de BD Paralelas / Infiniband HPC",
        },
        {
            "nombre": "4. Malla Completa (Full Mesh)",
            "enlaces": f"N(N-1)/2 = {(n_nodes * (n_nodes - 1)) // 2}",
            "grado": f"N - 1 = {n_nodes - 1}",
            "diametro": "1 salto directo (0 hops intermedios)",
            "biseccion": f"N² / 4 = {(n_nodes ** 2) // 4} enlaces",
            "fallos": "Máxima (Redundancia total punto a punto)",
            "uso_bd": "Clústeres HA pequeños (2-4 nodos Oracle RAC / Galera)",
        },
    ]

    print(
        "  ┌──────────────────────────────────┬──────────────────────┬────────────────────────────────────────┬───────────────────────────────────┬─────────────────────────────────────────┐"
    )
    print(
        "  │ Topología de Interconexión       │ Nº Enlaces Físicos   │ Diámetro (Saltos / Latencia)           │ Ancho de Banda de Bisección       │ Tolerancia a Fallos / Uso               │"
    )
    print(
        "  ├──────────────────────────────────┼──────────────────────┼────────────────────────────────────────┼───────────────────────────────────┼─────────────────────────────────────────┤"
    )
    for t in topologias:
        print(
            f"  │ {t['nombre']:<32} │ {t['enlaces']:<20} │ {t['diametro']:<38} │ {t['biseccion']:<33} │ {t['fallos']:<39} │"
        )
    print(
        "  └──────────────────────────────────┴──────────────────────┴────────────────────────────────────────┴───────────────────────────────────┴─────────────────────────────────────────┘"
    )
    print(
        "  -> Rol de INFINIBAND (RDMA) y SAN: En arquitecturas Shared-Disk o BD Paralelas, Infiniband permite acceso directo"
    )
    print(
        "     a memoria remota (RDMA) con latencia de ~2 µs sin pasar por el stack TCP/IP del kernel, mientras que la SAN"
    )
    print(
        "     (Fibre Channel / NVMe-oF) desacopla los discos físicos permitiendo que cualquier nodo monte los datafiles."
    )


def main() -> None:
    t_start = time.perf_counter()
    conn = get_connection()
    try:
        supabase_host, supabase_port = demo_p7_cloud_and_vendor_lockin(conn)
        demo_p8_latency_n_plus_1(conn, supabase_host, supabase_port)
        demo_p8_bandwidth_payload(conn)
        demo_p8_topologies_table(n_nodes=16)
    finally:
        conn.close()
    total_s = time.perf_counter() - t_start
    print("\n" + "=" * 92)
    print(f"  DEMOSTRACIÓN P7 y P8 COMPLETADA CON ÉXITO EN {total_s:.2f} SEGUNDOS.")
    print("=" * 92)


if __name__ == "__main__":
    main()
