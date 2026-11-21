# Guía Teórica-Práctica — Preguntas 7 y 8 (Arquitectura de Bases de Datos)

**Proyecto:** Sistema de Gestión Integral **Licorería La Cava**  
**Motores y Entornos Reales del Repositorio:**
- **Entorno IaaS / Local Bare-Metal:** MariaDB `12.3.2` en `localhost:3307` (`licoreriadatabase`: 41 tablas base + tablas DWH/particionamiento, 25 vistas, 28 procedimientos almacenados, 5 funciones y 130 triggers).
- **Entorno DBaaS Cloud:** **Supabase PostgreSQL** (`aws-0-us-east-1.pooler.supabase.com:5432`) con verificación TLS estricta (`API/prod-ca-2021.crt`), validación de mínimo privilegio (`API/postgres_connection.py`) y migraciones PL/pgSQL + RLS (`API/migrations/*_postgresql.sql`).
- **Entorno PaaS Cloud:** **Render Blueprint** (`render.yaml`) con dos servicios gestionados (`licoreria-api` en Python/Uvicorn y `licoreria-frontend` en React/Vite estático).

---

## 1. Pregunta 7: Paradigmas de Servicio en la Nube (DBaaS vs. IaaS / PaaS / SaaS), Control del Sistema y *Vendor Lock-in*

### 1.1. Frontera Técnica entre IaaS, DBaaS, PaaS y SaaS en Nuestro Proyecto

En la ingeniería de datos moderna, la diferencia entre los modelos de servicio en la nube radica en **dónde se traza la frontera de responsabilidad y control técnico** entre el Administrador de Base de Datos (DBA) / Arquitecto y el proveedor Cloud:

```
+-----------------------------------------------------------------------------------+
| CAPA DE LA PILA TECNOLÓGICA    | On-Prem / IaaS |   DBaaS    |   PaaS     | SaaS  |
|                                | (MariaDB :3307)| (Supabase) | (Render)   |(Web)  |
+--------------------------------+----------------+------------+------------+-------+
| 8. Uso del Sistema / Datos     |    Cliente     |  Cliente   |  Cliente   |Cliente|
| 7. Aplicación (React / FastAPI)|    Cliente     |  Cliente   |  Cliente   | Prov. |
| 6. Esquema SQL, Índices y RLS  |    Cliente     |  Cliente   |    N/A     | Prov. |
| 5. Runtime / Pooler / Backups  |    Cliente     | Proveedor  | Proveedor  | Prov. |
| 4. Motor DBMS Binario / Parches|    Cliente     | Proveedor  | Proveedor  | Prov. |
| 3. Sistema Operativo (Linux/W) |    Cliente     | Proveedor  | Proveedor  | Prov. |
| 2. Virtualización / Contenedor |  Cliente/Prov  | Proveedor  | Proveedor  | Prov. |
| 1. Hardware, SAN, Red Física   |  Cliente/Prov  | Proveedor  | Proveedor  | Prov. |
+-----------------------------------------------------------------------------------+
```

#### Tabla Comparativa Aterrizada a los Archivos Reales de `licoreria`

| Modelo Cloud | Definición Arquitectónica | Implementación Real en `licoreria` | Archivos de Evidencia en el Repositorio | Qué Controla el Equipo / DBA | Qué Abstrae el Proveedor |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **IaaS** (*Infrastructure as a Service* / On-Premise) | El proveedor entrega cómputo virtualizado (EC2/VPS), red y bloques de disco crudos; el DBA instala y administra el SO y el binario del DBMS (`mariadbd`). | Nuestro servidor **MariaDB 12.3.2** en `:3307` (o desplegado en una VM Linux/Windows dedicada). | `API/.env` (`MARIADB_HOST=localhost`, `MARIADB_PORT=3307`), `datadir` físico en disco. | Acceso `root` al SO, archivos `.ibd`, `my.ini`, `innodb_buffer_pool_size` (4 GB), `innodb_flush_log_at_trx_commit`, binlogs y respaldos manuales. | Solo la electricidad, enfriamiento y el hipervisor físico (si es VPS/EC2). |
| **DBaaS** (*Database as a Service*) | Servicio gestionado de base de datos donde el proveedor opera el motor, los parches, la alta disponibilidad (HA), los backups automáticos, el TLS y el pooler de conexiones. | **Supabase PostgreSQL** en la región AWS Virginia (`us-east-1`) accedido mediante el pooler gestionado en el puerto `5432`. | `API/.env` (`aws-0-us-east-1.pooler.supabase.com:5432`), `API/.env.supabase.local`, `API/prod-ca-2021.crt`, `API/postgres_connection.py`, `API/GUIA_NUBE.md`. | Diseño lógico (43 tablas), índices, vistas, funciones PL/pgSQL y políticas **RLS (Row-Level Security)**. | Prohibido el acceso SSH al SO, prohibido `SUPERUSER`, prohibido `BYPASSRLS` y ocultamiento del filesystem físico (`PGDATA`). |
| **PaaS** (*Platform as a Service*) | Plataforma que ejecuta el código de la aplicación gestionando automáticamente el *build*, contenedor, runtime, certificados SSL y *health checks*. | **Render Blueprint** que construye y despliega el backend FastAPI/Uvicorn (`licoreria-api`) y el frontend estático React/Vite (`licoreria-frontend`). | `render.yaml` (`runtime: python`, `healthCheckPath: /readyz`, `POSTGRES_SSL_ROOT_CERT: /etc/secrets/supabase-ca.crt`). | Código fuente Python/React, variables de entorno (`DATABASE_URL`, `CORS_ORIGINS`) y lógica del endpoint `/readyz`. | Orquestación de contenedores, balanceo de carga HTTPS, red interna y reinicio automático ante fallos. |
| **SaaS** (*Software as a Service*) | Software final listo para usar a través de Internet (navegador) sin que el usuario instale ni configure servidores, motores ni código. | **Sistema Web Licorería La Cava** (módulos de Ventas, Compras, Inventario, Nómina, Contabilidad y Auditoría). | `frontend/src/App.jsx` servido por HTTPS al navegador del usuario final. | El usuario final (cajero, bodeguero, contador, gerente) solo opera transacciones de negocio desde su navegador. | **Todo** el stack técnico (Frontend, API PaaS, Base de Datos DBaaS, red y almacenamiento). |

---

### 1.2. Análisis Profundo: Control del Sistema vs. Abstracción Operativa

1. **En IaaS / Bare-Metal (`MariaDB :3307`):**
   - Cuando ejecutamos el **Bloque 7.1** de `demo_p7_p8.sql` (`SHOW VARIABLES`), comprobamos que el DBA tiene acceso a `datadir = C:\Program Files\MariaDB 12.3\data\`, puede dimensionar el `innodb_buffer_pool_size` a nivel de bytes en RAM y conectarse como `root@localhost` con privilegio `SUPER`.
   - **Costo oculto:** El DBA es responsable de configurar replicación primaria-secundaria, monitorear que el disco no se llene con los *Binary Logs* (`log_bin`) y aplicar parches de seguridad sin tiempo de inactividad.

2. **En DBaaS (`Supabase PostgreSQL`):**
   - El proveedor (Supabase sobre AWS `us-east-1`) entrega cifrado en tránsito (`sslmode="verify-full"` contra `API/prod-ca-2021.crt`), *connection pooling* (Supavisor/PgBouncer en `aws-0-us-east-1.pooler.supabase.com:5432`) y respaldos *Point-in-Time Recovery (PITR)*.
   - **Pérdida de Control del Sistema:** El proveedor **jamás** entrega `rolsuper` real ni acceso al sistema operativo. De hecho, nuestro propio módulo [`API/postgres_connection.py`](file:///c:/Users/Jeremy/Desktop/PUCE/5toS/BasesDeDatosII/licoreria/API/postgres_connection.py#L7-L59) refuerza esta frontera arquitectónica mediante `_validate_database_role()`, que **aborta en frío la conexión** si detecta que el rol tiene `rolsuper`, `rolbypassrls`, `rolcreatedb`, `rolcreaterole`, `rolreplication` o privilegio `CREATE` sobre el esquema `public`.

---

### 1.3. Análisis Profundo del *Vendor Lock-in* (Acoplamiento al Proveedor y al Motor)

El *Vendor Lock-in* en la capa de datos es la barrera técnica y económica que impide trasladar una base de datos de un motor o proveedor cloud a otro sin reescribir gran parte del sistema. Nuestro proyecto demuestra empíricamente por qué **"migrar una base de datos empresarial no es solo copiar tablas"**:

1. **Acoplamiento por Dialecto Procedural (`SQL/PSM` de MariaDB vs. `PL/pgSQL` de PostgreSQL):**
   - Como documenta [`API/GUIA_NUBE.md`](file:///c:/Users/Jeremy/Desktop/PUCE/5toS/BasesDeDatosII/licoreria/API/GUIA_NUBE.md#L231-L234) y verifica en vivo nuestro script `benchmark_p7_p8_nube_red.py`, la base local MariaDB contiene **188 objetos programados**:
     - **28 Procedimientos Almacenados** (`sp_compra_crear`, `sp_registrar_log`, etc.)
     - **5 Funciones Almacenadas**
     - **130 Disparadores (Triggers)** (`TRG_AUD_*`, triggers de recálculo de IVA y kardex)
     - **25 Vistas** (`vw_*`)
   - En MariaDB, los triggers contienen bloques procedurales directos usando `SIGNAL SQLSTATE '45000'` y variables de sesión con arroba (`@auditoria_usuario`).
   - En PostgreSQL/Supabase, ese código **no compila**: PostgreSQL exige separar cada trigger en una función `CREATE FUNCTION ... RETURNS trigger LANGUAGE plpgsql AS $$` + `CREATE TRIGGER ... EXECUTE FUNCTION`, cambiar `@auditoria_usuario` por `current_setting('app.auditoria_usuario', true)` y cambiar `SIGNAL SQLSTATE` por `RAISE EXCEPTION ... USING ERRCODE = 'P0001'`.
   - **Evidencia real en el repositorio:** Tuvimos que construir **7 migraciones específicas para PostgreSQL** en `API/migrations/*_postgresql.sql` (como `20261108_compras_postgresql.sql`, `20261108_ventas_postgresql.sql` y `20261111_nomina_aprobacion_postgresql.sql`).

2. **Acoplamiento a Mecanismos de Seguridad y Ecosistema DBaaS:**
   - **Row-Level Security (RLS):** Supabase basa su arquitectura de seguridad en políticas RLS a nivel de fila en PostgreSQL. En `API/migrations/20261108_api_role_rls_postgresql.sql` tuvimos que activar `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` y crear políticas explícitas (`CREATE POLICY ... FOR SELECT/INSERT/UPDATE TO licoreria_api_access`) sobre las **43 tablas**. MariaDB no utiliza este modelo nativo de políticas RLS por rol de la misma forma.
   - **Infraestructura Propietaria del DBaaS:** El uso del *connection pooler* gestionado (`aws-0-us-east-1.pooler.supabase.com`), la autoridad certificadora propia del proveedor (`API/prod-ca-2021.crt`) y la especificación declarativa `render.yaml` en PaaS introducen *lock-in* operativo que debe gestionarse mediante capas de abstracción en el backend (`DATABASE_BACKEND=postgresql` vs `mariadb`).

---

## 2. Pregunta 8: Topologías de Red (Bus, Malla, Hipercubo, Árbol), Interconexión Física (Infiniband / SAN), Latencia y Ancho de Banda

### 2.1. Topologías de Red en Arquitecturas de Bases de Datos Paralelas y Distribuidas

Cuando un sistema de base de datos escala más allá de un solo servidor hacia un clúster de $N$ nodos (para procesamiento paralelo de consultas, *sharding* o alta disponibilidad), la **topología de la red de interconexión** determina cuántos saltos (*hops*) debe recorrer un paquete de datos, cuál es el ancho de banda agregado y qué ocurre si falla un cable o conmutador.

Para un clúster de **$N = 16$ nodos de base de datos** (calculado en vivo por `benchmark_p7_p8_nube_red.py`):

| Topología de Red | Fórmulas Matemáticas ($N$ nodos) | Valores para $N=16$ Nodos | Diámetro (Saltos Máximos / Latencia) | Ancho de Banda de Bisección | Tolerancia a Fallos y Caso de Uso en Bases de Datos |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Bus Común** (*Shared Bus*) | Enlaces $= 1$ medio compartido<br>Grado $= 1$ | **1 bus** compartido | **$1$** (acceso directo cuando el bus está libre) | **$1$** (Cuello de botella severo: solo 1 par transmite a la vez) | **Crítica (Muy Baja):** Si el bus físico se corta, todo el clúster cae. Usado solo en buses internos de placa/PCIe o LAN coaxiales históricas. |
| **2. Árbol / Fat-Tree** (*Jerárquica*) | Enlaces $= N - 1$<br>Grado $\le 3$ | **15 enlaces** | **$2 \log_2(N) = 8$ saltos** | **$1$** en árbol binario simple; **$N/2 = 8$** en **Fat-Tree / Clos** | **Media a Alta (con Fat-Tree):** En un árbol simple, si cae el nodo raíz el clúster se divide en dos (*Split-Brain*). En topología **Fat-Tree (Leaf-Spine)** es el estándar de los datacenters Cloud donde corren **Render** y **Supabase (AWS)**. |
| **3. Hipercubo** (*$d$-Cube*, $N = 2^d$) | Dimensión $d = \log_2(N)$<br>Enlaces $= \frac{N \log_2(N)}{2}$<br>Grado $= \log_2(N)$ | Dimensión **$4\text{D}$**<br>**32 enlaces**<br>Grado $= 4$ | **$\log_2(N) = 4$ saltos** | **$N / 2 = 8$ enlaces** simultáneos | **Alta:** Existen $d = 4$ caminos físicamente independientes entre nodos. Excelente equilibrio entre costo de cableado y baja latencia para **motores de BD paralelos (MPP) y clústeres HPC**. |
| **4. Malla Completa** (*Full Mesh*) | Enlaces $= \frac{N(N-1)}{2}$<br>Grado $= N - 1$ | **120 enlaces**<br>Grado $= 15$ | **$1$ salto directo** ($0$ nodos intermedios) | **$N^2 / 4 = 64$ enlaces** | **Máxima:** Ningún fallo de enlace aísla un nodo y la latencia es mínima ($1$ hop), pero su costo cuadrático $\mathcal{O}(N^2)$ la limita a clústeres pequeños de alta disponibilidad ($2$ a $4$ nodos, ej. **MariaDB Galera Cluster** u **Oracle RAC**). |

---

### 2.2. Rol de **Infiniband (RDMA)** y **SAN (Fibre Channel / NVMe-oF)** en Arquitecturas de BD

En bases de datos de misión crítica (especialmente arquitecturas **Shared-Disk** y motores transaccionales/analíticos en clúster), el stack Ethernet TCP/IP convencional introduce demasiada sobrecarga de CPU y latencia ($\sim 200\text{ a }500\ \mu\text{s}$). Allí entran dos tecnologías físicas especializadas:

1. **Infiniband con RDMA (*Remote Direct Memory Access*):**
   - **Qué hace:** Es una red de interconexión de ultra-baja latencia ($\sim 1\text{ a }2\ \mu\text{s}$, es decir **$0.002\text{ ms}$**) y altísimo ancho de banda ($100\text{ Gbps}$ HDR a $400\text{ Gbps}$ NDR) que suele organizarse en topologías **Fat-Tree** o **Hipercubo/Toro**.
   - **Por qué es vital para el DBMS:** Gracias a **RDMA**, un nodo de base de datos puede leer o escribir una página de $16\text{ KB}$ directamente en el **`innodb_buffer_pool`** (memoria RAM) de otro nodo del clúster **sin involucrar al sistema operativo ni a la CPU remota (*Kernel Bypass* y *Zero-Copy*)**. Esto permite fusionar cachés de memoria entre nodos (Cache Fusion) y sincronizar *commits* distribuidos casi a velocidad de memoria local.

2. **SAN (*Storage Area Network* — Fibre Channel / iSCSI / NVMe-oF):**
   - **Qué hace:** Es una red dedicada exclusivamente a bloques de almacenamiento que conecta los servidores de base de datos con cabinas de discos NVMe redundantes (RAID) mediante protocolos Fibre Channel ($32\text{–}64\text{ Gbps}$) o NVMe over Fabrics (NVMe-oF).
   - **Por qué es vital para el DBMS:** Permite las arquitecturas **Shared-Disk** y de **Compute-Storage Disaggregation** (como AWS Aurora o el almacenamiento subyacente de Supabase): todos los nodos de cómputo ven los mismos volúmenes lógicos (LUNs / Datafiles). Si el nodo primario de BD muere, un nodo secundario monta instantáneamente los mismos bloques de la SAN sin tener que copiar terabytes de datos por la red.

---

### 2.3. Cómo la Latencia ($\text{RTT}$) y el Ancho de Banda Condicionan el Rendimiento de la App y la Experiencia del Usuario (UX)

El tiempo total que espera un usuario en el frontend React (`licoreria-frontend`) cuando solicita datos a la base de datos a través de un canal físico responde a la ecuación fundamental de transporte de red:

$$T_{\text{total}} = T_{\text{motor\_CPU\_I/O}} + \left( N_{\text{viajes}} \times \text{RTT} \right) + \frac{\text{Tamaño\_Payload (Bits)}}{\text{Ancho\_de\_Banda (bps)}}$$

Donde:
- **$\text{RTT}$ (*Round-Trip Time* / Latencia):** Tiempo que tarda un paquete en viajar desde el cliente (FastAPI) hasta el servidor de BD y regresar.
- **$N_{\text{viajes}}$ (*Round-Trips*):** Cantidad de consultas secuenciales que hace el backend para responder una petición HTTP.
- **$\text{Ancho de Banda}$ (*Bandwidth*):** Capacidad del canal físico ($\text{Mbps}$ o $\text{Gbps}$) para evacuar el volumen de bytes (`Bytes_sent`) devuelto por la consulta.

#### A. Demostración Práctica 1: La Latencia ($\text{RTT}$) y el Problema $N+1$ (Bloque 8.4)
En nuestro proyecto tenemos **40 facturas** (`facturas`) y **160 líneas de detalle** (`proxfac`). Si el cajero abre la pantalla de facturación y el backend ejecuta el anti-patrón **$N+1$** ($1$ consulta para listar las $40$ facturas $+ 40$ consultas individuales para traer los detalles de cada factura $= 41\text{ Round-Trips}$):

- **En Infiniband / RDMA ($\text{RTT} \approx 0.002\text{ ms}$):** $41 \times 0.002\text{ ms} = 0.08\text{ ms}$ de red.
- **En Localhost `:3307` (Medido en vivo con `benchmark_p7_p8_nube_red.py`):**
  - Patrón $N+1$ ($41$ viajes): **`~4.16 ms`**
  - Patrón `1 JOIN` ($1$ viaje): **`~0.76 ms`**
  - *Trampa para el desarrollador:* En su laptop local, ambos parecen instantáneos ($<5\text{ ms}$), por lo que el desarrollador no nota el defecto arquitectónico.
- **En Producción WAN hacia nuestro DBaaS Supabase (`aws-0-us-east-1.pooler.supabase.com:5432` en Virginia, $\text{RTT} \approx 85\text{ ms}$ desde Ecuador):**
  - Patrón `1 JOIN` ($1$ viaje): $1 \times 85\text{ ms} + 0.8\text{ ms} \approx \mathbf{85.8\text{ ms}}$ $\rightarrow$ **UX instantánea y fluida en React.**
  - Patrón $N+1$ ($41$ viajes): $41 \times 85\text{ ms} + 1.6\text{ ms} \approx \mathbf{3,486.6\text{ ms}}$ (**$3.5\text{ segundos}$**) $\rightarrow$ **UX destruida:** el cajero ve un *spinner* congelado durante tres segundos y medio por cada clic, aunque el motor PostgreSQL procesó las consultas en menos de $2\text{ ms}$ de CPU.

#### B. Demostración Práctica 2: El Ancho de Banda y el Tamaño del Payload (Bloques 8.2 y 8.3)
Medido en vivo sobre las **10,000 filas** de `demo_ventas_rango` usando los contadores internos del motor (`SESSION_STATUS -> Bytes_sent`):
- **Anti-Patrón (Saturación del Ancho de Banda):** Ejecutar `SELECT * FROM demo_ventas_rango` para traer las $10,000$ filas a Python y sumarlas en la aplicación transmite **`620,264 Bytes` ($\sim 606\text{ KB}$)** por el socket TCP y tarda **`~35 ms`** en local (y bajo concurrencia en una red WAN de $50\text{ Mbps}$ saturaría el canal con decenas de megabytes por segundo).
- **Patrón Optimizado (Proyección y Agregación `GROUP BY` en el Motor):** Hacer que MariaDB agrupe por ciudad junto al Buffer Pool/SAN y devuelva solo las **8 filas** resumidas transmite apenas **`558 Bytes`** y tarda **`~5.7 ms`**.
- **Resultado:** Una reducción real del **$99.91\%$ del ancho de banda consumido** ($1,112\times$ menos tráfico en la red) y una respuesta **$6.1\times$ más rápida**.

---

## 3. Guía Rápida para la Demostración en Vivo frente al Profesor

### Paso A: En HeidiSQL (`docs/practica_arquitectura/demo_p7_p8.sql`)
1. Abrir `docs/practica_arquitectura/demo_p7_p8.sql` en HeidiSQL conectado a `localhost:3307` (`licoreriadatabase`).
2. Presionar **`Ctrl+F9`** (o seleccionar por bloques con `F9`):
   - **Bloques `7.1` a `7.4`:** Muestran las variables físicas de control del DBA en IaaS (`datadir`, `innodb_buffer_pool_size`), el conteo en vivo de los **188 objetos con *Vendor Lock-in*** (28 SPs, 5 funciones, 130 triggers, 25 vistas) frente a nuestras migraciones PostgreSQL/RLS, y la tabla completa de capas `IaaS -> DBaaS -> PaaS -> SaaS`.
   - **Bloques `8.1` a `8.4`:** Muestran los buffers de red del motor (`max_allowed_packet`, `net_buffer_length`), el tráfico real acumulado `Bytes_received` vs `Bytes_sent`, la reducción de $>99\%$ de payload en el Data Warehouse (`dwh_fact_ventas`) y la matriz comparativa de tiempos $N+1$ vs `1 JOIN` desde Infiniband ($0.002\text{ ms}$) hasta WAN Cloud Virginia ($85\text{ ms}$).

### Paso B: En Terminal (`docs/practica_arquitectura/benchmark_p7_p8_nube_red.py`)
Ejecutar el benchmark automatizado:
```powershell
C:\Users\Jeremy\AppData\Local\Python\bin\python3.14.exe docs/practica_arquitectura/benchmark_p7_p8_nube_red.py
```
El script inspecciona en vivo `render.yaml`, `API/.env`, `API/prod-ca-2021.crt` y `API/postgres_connection.py`, mide la latencia TCP hacia Supabase (`aws-0-us-east-1.pooler.supabase.com:5432`), ejecuta el experimento $N+1$ vs `JOIN` sobre las 40 facturas reales, mide los bytes TCP exactos sobre las 10,000 filas de `demo_ventas_rango` e imprime la matriz matemática de topologías (`Bus`, `Árbol/Fat-Tree`, `Hipercubo 4D` y `Malla Completa`).
