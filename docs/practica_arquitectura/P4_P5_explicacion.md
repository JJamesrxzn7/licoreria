# Desarrollo Técnico de las Preguntas 4 y 5 — Arquitectura Distribuida Licorería "La Cava"

Este documento responde en profundidad las **Preguntas 4 y 5** de la práctica de **Arquitectura de Bases de Datos vs. Arquitectura de Sistemas de Información**, aterrizadas directamente sobre el clúster físico de **6 Bases de Datos Reales** levantado en el proyecto:

* **Sede Matriz Quito (`UIO` — 3 Bases de Datos + 5 Módulos `C, I, V, TH, Ctbl`):**
  1. `QUITO-SQL` (**MariaDB 12.3 Puerto `:3307`** — `licoreriadatabase` + vistas de los 5 cilindros `mod_c_compras`, `mod_i_inventarios`, `mod_v_ventas`, `mod_th_talento_humano`, `mod_ctbl_contabilidad`).
  2. `QUITO-NOSQL` (**Motor Documental JSON Puerto `:3307`** — `quito_nosql_db` + `API/data/quito_nosql.db` con fichas de cata JSON, sesiones POS y telemetría).
  3. `QUITO-OTRAS-DWH` (**PostgreSQL 18.3 Puerto `:5432`** — `quito_otras_dwh` con el Cubo Estrella Nacional y la bitácora del Coordinador 2PC).
* **Sede Regional Guayaquil (`GYE` — 2 Bases de Datos en Puertos TCP Independientes):**
  4. `GUAYAQUIL-SQL-1` (**MariaDB 12.3 Puerto `:3308`** — `licoreria_guayaquil`, instancia física aislada en `cluster_nodes/gye_3308` con el fragmento horizontal de la Costa `GYE, MNT, MCH`).
  5. `GUAYAQUIL-BD-2` (**MariaDB 12.3 Puerto `:3309`** — `licoreria_guayaquil_bodega`, instancia física aislada en `cluster_nodes/gye_3309` con contenedores del Puerto Marítimo de Guayaquil y réplica de stock).
* **Sede Nube Cuenca y Loja (`CUE / LJA` — Cloud DB):**
  6. `CUENCA-LOJA-CLOUD` (**PostgreSQL 18.3 Cloud DBaaS Puerto `:5432`** — `cloud_cuenca_loja` / Pooler TLS de Supabase `aws-0-us-east-1.pooler.supabase.com:5432` con el fragmento austral de Cuenca y Loja).

---

## Pregunta 4: Transparencia de Localización y Fragmentación en un SGBD Distribuido vs. APIs Web Heterogéneas

### 4.1. Cómo se logra la Transparencia de Localización y de Fragmentación en nuestra Arquitectura
Según las reglas de C. J. Date para Sistemas de Gestión de Bases de Datos Distribuidas (SGBDD):

1. **Transparencia de Fragmentación:**
   * Nuestra relación global de clientes (`CLIENTES`) y de facturación (`FACTURAS`) está dividida mediante **Fragmentación Horizontal Primaria** según el predicado geográfico `id_Ciudad`:
     $$\text{CLIENTES}_{\text{QUITO (:3307)}} = \sigma_{\text{id\_Ciudad} \in \{\text{'UIO','IBR','AMB','LTX','RIO'}\}}(\text{CLIENTES})$$
     $$\text{CLIENTES}_{\text{GUAYAQUIL (:3308)}} = \sigma_{\text{id\_Ciudad} \in \{\text{'GYE','MNT','MCH'}\}}(\text{CLIENTES})$$
     $$\text{CLIENTES}_{\text{CUENCA\_CLOUD (:5432)}} = \sigma_{\text{id\_Ciudad} \in \{\text{'CUE','LJA'}\}}(\text{CLIENTES})$$
   * Además, en Quito (`:3307`) los datos operacionales están organizados en los **5 módulos funcionales de la pizarra (`C` Compras, `I` Inventarios, `V` Ventas, `TH` Talento Humano, `Ctbl` Contabilidad)**.
   * **¿Cómo se oculta esto al usuario final?** Cuando el usuario o el DBA solicita la vista nacional en la aplicación web (`Vista Global Federada P4` en la Consola DBA), el **Enrutador de Consultas Distribuidas del Middleware FastAPI (`:8000`)** descompone la consulta global en 3 subconsultas paralelas hacia `:3307`, `:3308` y `:5432` y reconstruye la relación global mediante la operación de unión (`UNION ALL`), sin que la capa de presentación React (`:5173`) conozca que la tabla estaba particionada en tres ciudades distintas.

2. **Transparencia de Localización:**
   * Los usuarios y los componentes de React nunca codifican direcciones IP (`127.0.0.1:3307`, `127.0.0.1:3308`, `127.0.0.1:3309`, `aws-0-us-east-1.pooler.supabase.com:5432`) ni nombres de esquemas físicos (`licoreriadatabase`, `licoreria_guayaquil`, `cloud_cuenca_loja`).
   * El catálogo global de localización reside en el diccionario de topología (`NODES_CONFIG` en `API/arquitectura_cluster.py`). Si mañana migramos la base de datos de Guayaquil del puerto `:3308` a un servidor en AWS RDS o cambiamos Cuenca Cloud de región, únicamente se actualiza el descriptor en el Middleware y ninguna pantalla ni consulta de negocio sufre cambios.

### 4.2. Diferencia Técnica frente a Integrar Datos mediante APIs Web (REST / GraphQL) entre Sistemas Heterogéneos

| Criterio Técnico | SGBD Distribuido (Transparencia de BD) | Integración vía APIs Web (Sistemas Heterogéneos) |
| :--- | :--- | :--- |
| **Nivel de Abstracción** | Opera en la **Capa de Datos / Motor SQL** (optimizador de consultas distribuidas, vistas federadas, protocolo binario TCP `:3307/:3308/:5432`). | Opera en la **Capa de Aplicación / Lógica de Negocio** (serialización HTTP/JSON sobre REST o GraphQL en `:8000`). |
| **Optimización de Consultas (`JOIN` y `WHERE`)** | El optimizador distribuido aplica *predicate pushdown* y *semi-joins* a nivel de álgebra relacional, transfiriendo solo las tuplas filtradas por sockets binarios. | La aplicación debe invocar múltiples endpoints HTTP (`GET /quito/clientes`, `GET /guayaquil/clientes`), deserializar JSON en memoria RAM y hacer el `merge`/`filter` por código imperativo. |
| **Atomicidad Transaccional y Bloqueos** | Soporta transacciones globales nativas (`XA START / XA PREPARE / XA COMMIT`) y detección de *deadlocks* distribuidos a nivel de páginas/filas (`InnoDB` / `MVCC`). | Las APIs REST son *stateless* (sin estado); no mantienen cursores ni bloqueos de fila entre llamadas HTTP, por lo que requieren patrones compensatorios como **Sagas** en lugar de bloqueos ACID directos. |
| **Acoplamiento de Esquema** | Exige un **Esquema Conceptual Global (GCS)** unificado y mapeado hacia los esquemas locales (LCS) de cada nodo. | Permite **autonomía total de esquema**: Quito puede usar SQL relacional, Guayaquil otro ERP y un catálogo externo usar NoSQL JSON sin compartir un esquema relacional único. |

---

## Pregunta 5: Gestión de Concurrencia Distribuida, Rol del Middleware y Protocolo Two-Phase Commit (2PC)

### 5.1. ¿Cómo se gestiona la concurrencia cuando múltiples sitios actualizan datos compartidos?
Cuando un cliente corporativo realiza un pedido nacional o se ejecuta una transferencia de inventario de *Aguardiente Zhumir (`PRO-004`)* entre la **Bodega de Guayaquil (`:3308`)**, la **Sede Matriz Quito (`:3307`)** y la **Nube de Cuenca/Loja (`:5432`)**:
1. **Control de Concurrencia Local en cada Nodo (MVCC + 2PL):**
   * Cada motor (**MariaDB InnoDB** en `:3307/:3308/:3309` y **PostgreSQL 18** en `:5432`) aplica **Control de Concurrencia Multiversión (MVCC)** junto con **Bloqueo de Dos Fases Estricto (Strict 2PL — Two-Phase Locking)** sobre las filas afectadas (`SELECT ... FOR UPDATE` o `UPDATE` dentro de una transacción con `autocommit=False`).
   * Mientras la transacción global está en curso, la fila del producto `PRO-004` queda bloqueada exclusivamente (`X-Lock`) en Guayaquil (`:3308`) y en Quito (`:3307`), impidiendo que otro cajero concurrente venda el mismo stock antes de que concluya la decisión global (**Aislamiento ACID**).

### 5.2. Rol del Middleware (`FastAPI :8000`) y del Coordinador de Transacciones
Como nuestro clúster es **Multi-Motor y Multi-Puerto** (combina instancias de **MariaDB 12.3** en `:3307, :3308, :3309` con **PostgreSQL 18** en `:5432`), los motores no hablan directamente entre sí por un protocolo propietario único. Aquí el **Middleware FastAPI (`API/arquitectura_cluster.py`)** cumple tres funciones críticas:
1. **Administrador de Conexiones Heterogéneas:** Abre y mantiene canales transaccionales (`autocommit=False`) simultáneos con los drivers `mysql.connector` (`:3307`, `:3308`, `:3309`) y `psycopg` (`:5432`).
2. **Coordinador 2PC (Transaction Manager):** Asigna un identificador global único (`tx_id`, ej. `2PC-8F91A2B4`), dirige la **Fase 1 (Votación/PREPARE)** y la **Fase 2 (Decisión/COMMIT o ROLLBACK)**, y recolecta los votos de todos los nodos participantes.
3. **Bitácora Persistente del Coordinador (Write-Ahead Log 2PC):** Registra el estado de cada fase y la decisión final en la tabla `auditoria_transacciones_2pc` del nodo `quito_otras_dwh` (`PostgreSQL :5432`) para recuperación ante desastres.

### 5.3. Funcionamiento del Protocolo Two-Phase Commit (2PC) y Análisis de Fallo en la Fase de Preparación (`PREPARE`)

El protocolo **Two-Phase Commit (2PC)** garantiza la **Atomicidad Distribuida** (*"todos los sitios confirman o ninguno confirma"*) en dos fases:

#### Fase 1: Fase de Preparación o Votación (`PREPARE`)
1. El **Coordinador (`FastAPI :8000`)** envía el comando `PREPARE` (con las sentencias `UPDATE`/`INSERT` sin confirmar) a los nodos participantes:
   * **Participante 1:** `QUITO-SQL (:3307)` — Incrementa recepción de stock (`+15` botellas).
   * **Participante 2:** `GUAYAQUIL-SQL (:3308)` — Descuenta stock de bodega Costa (`-15` botellas).
   * **Participante 3:** `CUENCA-LOJA-CLOUD (:5432)` — Registra guía de despacho interregional.
2. Cada participante ejecuta la operación localmente en su *buffer/redo log*, verifica restricciones de integridad (ej. que el stock no quede negativo) y adquiere los bloqueos de fila:
   * Si todo es válido y el nodo puede garantizar que podrá hacer commit, responde **`VOTE_COMMIT` (`PREPARED`)**.
   * Si ocurre cualquier error o restricción violada, responde **`VOTE_ABORT`**.

#### Fase 2: Fase de Decisión (`COMMIT` o `ABORT / ROLLBACK`)
* **Caso Exitoso (Unanimidad):** Si **todos** los nodos (`3/3`) respondieron `VOTE_COMMIT`, el Coordinador registra `GLOBAL_COMMIT` y envía `COMMIT` a `:3307`, `:3308` y `:5432`. Los cambios se vuelven permanentes y se liberan los bloqueos.

#### ¿Qué ocurre si un sitio falla durante la Fase de Preparación (`PREPARE`)? (Demostración en vivo en la Consola DBA)
Supongamos que **`QUITO-SQL (:3307)`** ya ejecutó su `UPDATE` y respondió **`VOTE_COMMIT`**, pero en ese instante **`GUAYAQUIL-SQL (:3308)`** sufre un fallo durante su fase `PREPARE` (caída del enlace de red WAN, *timeout*, caída del proceso `:3308` o falta de stock que produce **`VOTE_ABORT`**):

1. **Ruptura de Unanimidad:** En 2PC basta con que **un solo participante** vote `VOTE_ABORT` o no responda dentro del *timeout* de la Fase 1 para que la transacción global **no pueda confirmarse jamás**.
2. **Transición Inmediata a `GLOBAL_ROLLBACK`:** El Coordinador (`:8000`) escribe `PHASE_1_PREPARE_ABORT -> GLOBAL_ROLLBACK` en la bitácora `auditoria_transacciones_2pc` (`:5432`).
3. **Reversión en los Sitios que ya habían preparado (`ROLLBACK`):** El Coordinador envía explícitamente `ROLLBACK` (o `XA ROLLBACK`) a **`QUITO-SQL (:3307)`** y a **`CUENCA-LOJA-CLOUD (:5432)`**.
4. **Liberación de Bloqueos y Cero Inconsistencia:** Quito (`:3307`) deshace mediante su *Undo Log* el incremento de `+15` botellas que tenía preparado en memoria y libera el bloqueo exclusivo sobre `PRO-004`. Así se evita el clásico problema de **"inventario fantasma"** (que Quito sume botellas que Guayaquil nunca llegó a descontar).
