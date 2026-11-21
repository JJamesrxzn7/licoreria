# Práctica Arquitecturas — Preguntas 3 y 6
**Proyecto:** Licorería La Cava · **Stack:** React + Vite (`frontend/`) → FastAPI (`api/main.py`) → MariaDB `licoreriadatabase` (puerto 3307)
**Scripts de demostración en vivo:**
- SQL en HeidiSQL: `docs/practica_arquitectura/demo_p3_p6.sql`
- Benchmark de Escalabilidad en Python: `docs/practica_arquitectura/benchmark_p3_escalabilidad.py`

---

## Pregunta 3 — Mecanismos de Escalabilidad en BD (Speed-up, Scale-up y Particionamiento) vs. Scale-out en el SI

### 1. Conceptos Fundamentales y Fórmulas de Escalabilidad en Bases de Datos

En arquitecturas de bases de datos paralelas y distribuidas (DeWitt & Gray), la escalabilidad mide la capacidad del motor para aprovechar mayores recursos físicos (CPUs, discos, nodos):

| Métrica / Concepto | Definición Técnica | Fórmula Matemática | Comportamiento Ideal vs. Real |
|---|---|---|---|
| **Speed-up (Aceleración)** | Mantener **fijo el tamaño del problema/carga** y **aumentar los recursos ($N$)** para reducir el tiempo de ejecución. | $$\text{Speed-up}(N) = \frac{T(1)}{T(N)}$$ | **Ideal (Lineal):** $\text{Speed-up}(N) = N$.<br>**Real (Sub-lineal):** $< N$ por costos de arranque, interferencia en memoria/disco (Shared-Memory) y sesgo (*skew*). |
| **Scale-up (Ampliación)** | **Aumentar proporcionalmente la carga ($N\times$) y los recursos ($N\times$)**, buscando que el tiempo de respuesta se mantenga constante o que los TPS crezcan linealmente. | $$\text{Scale-up}_{\text{tiempo}}(N) = \frac{T(1, \text{Carga } 1\times)}{T(N, \text{Carga } N\times)}$$<br>$$\text{Scale-up}_{\text{TPS}}(N) = \frac{\text{TPS}(N)}{\text{TPS}(1)}$$ | **Ideal:** $\text{Scale-up}_{\text{tiempo}} = 1.00$ (y $\text{TPS}(N) = N \cdot \text{TPS}(1)$).<br>**Tipos:** *Scale-up Transaccional* ($N$ veces más transacciones pequeñas concurrentes) y *Scale-up Batch* (una consulta analítica sobre una tabla $N$ veces más grande). |

---

### 2. Los 3 Mecanismos de Particionamiento Horizontal en el Motor de Base de Datos

Para lograr *Speed-up* y *Scale-up* evitando que un solo disco o estructura de índice sea el cuello de botella, el DBA divide horizontalmente las tuplas de una tabla grande en **particiones físicas independientes**. En `licoreriadatabase` hemos creado y poblado 3 tablas con **10,000 transacciones reales cada una**:

| Estrategia de Particionamiento | Tabla Real en `licoreriadatabase` | Definición DDL en MariaDB | Cómo reparte las 10,000 filas | Ventaja Principal (Partition Pruning) | Desventaja / Riesgo de Sesgo (*Skew*) |
|---|---|---|---|---|---|
| **1. Por Rango (*Range Partitioning*)** | `demo_ventas_rango` | `PARTITION BY RANGE (YEAR(fecha_venta))` (`p_2024`, `p_2025`, `p_2026`, `p_futuro`) | `p_2024`: **2,500** filas<br>`p_2025`: **4,000** filas<br>`p_2026`: **3,500** filas<br>`p_futuro`: **0** filas | Ideal para **consultas por intervalos históricos** (`WHERE fecha_venta BETWEEN ...`): el motor poda (*pruning*) los demás años y lee solo `[p_2025]`. | **Sesgo temporal (*Hot-spot*)**: todas las inserciones del año actual golpean únicamente la partición `p_2026`. |
| **2. Por Asociación / Función Hash (*Hash Partitioning*)** | `demo_ventas_hash` | `PARTITION BY HASH (id_sucursal_num) PARTITIONS 4` | `p0`: **1,500** filas<br>`p1`: **3,500** filas<br>`p2`: **2,500** filas<br>`p3`: **2,500** filas | Ideal para **búsquedas exactas y joins por clave asociada** (`WHERE id_sucursal_num = 2` → lee solo `[p2]`). Agrupa datos relacionados en la misma partición. | Si una sucursal vende mucho más que otra, su partición tendrá más datos (*data skew* por dominio). No sirve para rangos. |
| **3. En Turno Rotativo (*Round-Robin*)** | `demo_ventas_rotativo` | `PARTITION BY HASH (id_transaccion) PARTITIONS 4` (con ID secuencial $1..10,000 \Rightarrow i \bmod 4$) | `p0`: **2,500** filas<br>`p1`: **2,500** filas<br>`p2`: **2,500** filas<br>`p3`: **2,500** filas | **Equilibrio matemático perfecto (0% skew)**: garantiza que todas las particiones tengan exactamente la misma cantidad de tuplas. Ideal para escaneos completos paralelos. | **No permite *Partition Pruning* en consultas de rango o negocio** (`WHERE fecha_venta ...` obliga a escanear las 4 particiones `[p0,p1,p2,p3]`). |

---

### 3. Contraste Crítico: Particionamiento en BD vs. Scale-out en la Capa de Aplicaciones del SI

```
 [ Balanceador / Cliente HTTP ]
        /               \
       v                 v
 [ FastAPI :8000 ]  [ FastAPI :8001 ]   <-- SCALE-OUT EN CAPA DE APP (Stateless: clonar procesos es trivial)
        \               /
         v             v
 [ MariaDB :3307 (Buffer Pool + Disco) ] <-- CAPA DE BD (Stateful + ACID: requiere Particionamiento físico)
   |-- demo_ventas_rango    (p_2024 | p_2025 | p_2026)
   |-- demo_ventas_hash     (p0 | p1 | p2 | p3)
   |-- demo_ventas_rotativo (p0 | p1 | p2 | p3)
```

| Criterio | Scale-out en la Capa de Aplicaciones del SI (`api/main.py`) | Escalabilidad y Particionamiento en la Capa de BD (`MariaDB`) |
|---|---|---|
| **Estado (*State*)** | **Stateless (Sin estado):** La API FastAPI valida tokens JWT y ejecuta lógica de negocio sin guardar datos persistentes en su RAM local. | **Stateful (Con estado persistente y ACID):** Mantiene la única fuente de verdad, bloqueos de filas (*row locks*), *Buffer Pool* y *Redo Logs*. |
| **Cómo se escala horizontalmente** | **Clonación directa:** Se levantan $N$ instancias idénticas (`uvicorn main:app --port 8000` y `--port 8001`) detrás de un balanceador. | **No basta con clonar procesos:** Si clonamos 10 APIs contra 1 BD sin particionar, las 10 compiten por el mismo disco e índices. Exige **particionamiento físico** (Rango, Hash o Rotativo) o arquitectura *Shared-Nothing*. |
| **Responsable** | Arquitecto de Sistemas de Información / DevOps. | Administrador de Base de Datos (DBA). |

---

### 4. Resultados Reales del Benchmark en Vivo (`benchmark_p3_escalabilidad.py`)

Para ejecutar el benchmark en vivo frente al profesor:
```powershell
C:\Users\Jeremy\AppData\Local\Python\bin\python3.14.exe docs/practica_arquitectura/benchmark_p3_escalabilidad.py
```

Resultados medidos sobre `licoreriadatabase`:
- **Speed-up (Carga fija = 1,000 consultas reales):**
  - $N=1$ hilo: $T(1) = 1.14\text{ s}$ ($\text{Speed-up} = 1.00\times$, Eficiencia $= 100\%$)
  - $N=4$ hilos: $T(4) = 0.31\text{ s}$ ($\text{Speed-up} = 3.67\times$ vs ideal $4.00\times$, Eficiencia $= 91.9\%$)
  - $N=8$ hilos: $T(8) = 0.21\text{ s}$ ($\text{Speed-up} = 5.42\times$ vs ideal $8.00\times$, Eficiencia $= 67.7\%$)
- **Scale-up Transaccional (Carga y trabajadores crecen $1\times \to 4\times \to 8\times$: 200, 800 y 1,600 consultas):**
  - $1\times$ ($1$ worker, $200$ tx): $\sim 909\text{ TPS}$ ($T = 0.22\text{ s}$, Índice Scale-up $= 1.00$)
  - $4\times$ ($4$ workers, $800$ tx): $\sim 3,345\text{ TPS}$ ($T = 0.24\text{ s}$, Índice Scale-up $= 0.92$, Throughput $3.68\times$)
  - $8\times$ ($8$ workers, $1,600$ tx): $\sim 4,335\text{ TPS}$ ($T = 0.37\text{ s}$, Throughput $4.77\times$)

---

## Pregunta 6 — Base de Datos Operacional (OLTP) vs. Data Warehouse (OLAP / Esquema en Estrella + Proceso ETL)

### 1. Diferencias Arquitectónicas entre OLTP y Data Warehouse (OLAP) en Nuestro Proyecto

| Característica | Base Operacional OLTP (`licoreriadatabase` 3FN) | Data Warehouse OLAP (`dwh_*` Esquema en Estrella) |
|---|---|---|
| **Propósito Principal** | Operación diaria en tiempo real: facturar en caja, descontar stock con triggers, registrar auditoría y asientos contables. | Análisis estratégico e histórico para toma de decisiones gerenciales (rentabilidad por región, trimestre, categoría, marca y segmento B2B/B2C). |
| **Modelado de Datos** | **3ra Forma Normal (3FN)**: Entidades altamente divididas (`FACTURAS`, `PROXFAC`, `PRODUCTOS`, `CATEGORIAS`, `MARCAS`, `CLIENTES`, `CIUDADES`) para evitar redundancia y anomalías de actualización. | **Modelo Dimensional en Estrella (*Star Schema*)**: 1 Tabla de Hechos central (`dwh_fact_ventas`) rodeada de 3 Dimensiones **desnormalizadas** (`dwh_dim_tiempo`, `dwh_dim_producto`, `dwh_dim_cliente`). |
| **Operaciones Típicas** | Lecturas/escrituras puntuales muy cortas (`INSERT`, `UPDATE`, `SELECT WHERE id_Factura = 'FAC-000001'`) con alta concurrencia y garantías ACID. | Consultas de lectura masiva (*read-only* / carga por lotes ETL) con agregaciones multidimensionales (`SUM`, `COUNT`, `GROUP BY` por Región, Trimestre, Categoría). |
| **Cantidad de JOINs** | **Alta (6 a 7 tablas en JOIN)** para reconstruir una venta con su ciudad, categoría y marca (ver Bloque `6.1`). | **Mínima (1 nivel de JOIN en estrella)**: la tabla de hechos se une directamente a las dimensiones desnormalizadas (ver Bloques `6.4` y `6.5`). |
| **Horizonte Temporal** | Estado actual (*fotografía operativa del momento*, ej. `pro_Saldo_Final` actual). | Histórico consolidado multianual (series 2024–2026 clasificadas en `dwh_dim_tiempo`). |

---

### 2. Arquitectura del Esquema en Estrella Implementado en `licoreriadatabase`

```
        +--------------------------+
        |     dwh_dim_tiempo       |
        |--------------------------|
        | PK sk_tiempo (YYYYMMDD)  |
        |    fecha, anio, trimestre|
        |    mes, nombre_mes       |
        |    dia_semana, fin_sem   |
        +------------+-------------+
                     | 1
                     |
                     | N
        +------------+-------------+
        |     dwh_fact_ventas      | (TABLA DE HECHOS CENTRAL - 660 filas)
        |--------------------------|
        | PK id_hecho              |
        | FK sk_tiempo             |
        | FK sk_producto           |
        | FK sk_cliente            |
        |    id_factura_oltp       |
        |    cantidad_vendida      | <-- Métricas Cuantitativas Aditivas
        |    precio_unitario       |
        |    costo_unitario        |
        |    ingreso_bruto         |
        |    costo_total           |
        |    margen_ganancia       |
        +-----+--------------+-----+
            N |              | N
              |              |
            1 |              | 1
+-------------+------------+ +-------------+--------------+
|     dwh_dim_producto     | |      dwh_dim_cliente       |
|--------------------------| |----------------------------|
| PK sk_producto           | | PK sk_cliente              |
|    id_producto_oltp      | |    id_cliente_oltp         |
|    descripcion           | |    nombre_cliente          |
|    categoria (Desnorm.)  | |    tipo_cliente (JUR/NAT)  |
|    marca     (Desnorm.)  | |    ruc_ced                 |
|    um_venta              | |    ciudad, provincia       |
|    costo_actual, precio  | |    region (Desnorm.)       |
+--------------------------+ +----------------------------+
```

---

### 3. El Proceso ETL (`CALL SP_ETL_CARGAR_DWH_VENTAS()`)

El procedimiento almacenado `SP_ETL_CARGAR_DWH_VENTAS()` automatiza las 3 etapas del pipeline de datos:

1. **Fase E (*Extract* — Extracción):**
   - Extrae los catálogos maestros y transacciones aprobadas/abiertas desde las 7 tablas operacionales en 3FN: `FACTURAS` (40 facturas reales), `PROXFAC` (160 líneas de detalle), `PRODUCTOS` (30 licores/cervezas/vinos), `CATEGORIAS`, `MARCAS`, `CLIENTES` (20 clientes de Ecuador) y `CIUDADES`, además del lote histórico transaccional.
2. **Fase T (*Transform* — Transformación, Limpieza y Desnormalización):**
   - **Limpieza y estandarización:** Aplica `TRIM()` y `COALESCE()` sobre cadenas `CHAR` para eliminar espacios de relleno del modelo operacional.
   - **Desnormalización de Producto:** Colapsa 3 tablas (`PRODUCTOS` $\bowtie$ `CATEGORIAS` $\bowtie$ `MARCAS`) en una sola tabla plana `dwh_dim_producto`.
   - **Desnormalización de Cliente y Regla de Negocio:** Colapsa `CLIENTES` $\bowtie$ `CIUDADES` en `dwh_dim_cliente` y deriva la columna analítica `tipo_cliente`: `'JUR'` (Persona Jurídica / B2B si `CHAR_LENGTH(cli_RUC_CED) = 13`) vs. `'NAT'` (Persona Natural / B2C si tiene 10 dígitos).
   - **Enriquecimiento Temporal:** Convierte `DATE` en clave subrogada entera `sk_tiempo` (`YYYYMMDD`), extrae año, trimestre (`QUARTER`), nombre del mes en español, día de la semana e indicador booleano `es_fin_semana`.
   - **Cálculo de Indicadores Financieros (KPIs):** Calcula en línea `ingreso_bruto`, `costo_total = cantidad * costo_unitario` y la utilidad neta `margen_ganancia = ingreso_bruto - costo_total`.
3. **Fase L (*Load* — Carga):**
   - Carga las dimensiones mediante `INSERT ... ON DUPLICATE KEY UPDATE` (manteniendo claves subrogadas `sk_producto`, `sk_cliente`, `sk_tiempo`) e inserta los 660 registros de hechos consolidados en `dwh_fact_ventas`.

---

### 4. Guía Paso a Paso para la Demostración en Vivo (HeidiSQL + Terminal)

1. **Demostrar Pregunta 3 en HeidiSQL (`docs/practica_arquitectura/demo_p3_p6.sql`):**
   - Ejecutar **Bloque 3.1**: Mostrar las 12 particiones físicas de `demo_ventas_rango`, `demo_ventas_hash` y `demo_ventas_rotativo` en `information_schema.PARTITIONS` (ver cómo Turno Rotativo tiene exactamente `2,500` filas en cada partición `p0..p3`).
   - Ejecutar **Bloques 3.2, 3.3 y 3.4**: Mostrar el resultado de `EXPLAIN PARTITIONS` y señalar la columna `partitions` para demostrar cómo MariaDB hace *Partition Pruning* leyendo solo `p_2025` (Rango) o `p2` (Hash).
2. **Demostrar el Benchmark de Speed-up y Scale-up en Terminal:**
   - Correr `C:\Users\Jeremy\AppData\Local\Python\bin\python3.14.exe docs/practica_arquitectura/benchmark_p3_escalabilidad.py` y mostrar las tablas de *Speed-up* ($1 \to 4 \to 8$ hilos con 1,000 consultas fijas) y *Scale-up* ($200 \to 800 \to 1,600$ consultas).
3. **Demostrar Pregunta 6 en HeidiSQL (`docs/practica_arquitectura/demo_p3_p6.sql`):**
   - Ejecutar **Bloque 6.1**: Mostrar una consulta operacional OLTP que requiere unir 7 tablas normalizadas en 3FN.
   - Ejecutar **Bloque 6.2 y 6.3**: Ejecutar en vivo `CALL SP_ETL_CARGAR_DWH_VENTAS();` y mostrar las dimensiones desnormalizadas (`dwh_dim_producto` y `dwh_dim_cliente`).
   - Ejecutar **Bloques 6.4 y 6.5**: Mostrar los reportes gerenciales OLAP (*Roll-up* por Año/Trimestre/Región y *Slice & Dice* por Categoría/Marca/Segmento Jurídico vs. Natural) obteniendo ingresos, costos, utilidad neta y porcentaje de rentabilidad en milisegundos.
