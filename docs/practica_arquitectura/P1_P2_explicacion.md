# Práctica Arquitecturas — Preguntas 1 y 2
**Proyecto:** Licorería La Cava · **Stack:** React + Vite (`frontend/`) → FastAPI (`api/main.py`) → MariaDB `licoreriadatabase` (puerto 3307)
**Script de demostración:** `docs/practica_arquitectura/demo_p1_p2.sql` (abrir en HeidiSQL)

---

## Pregunta 1 — DBA vs. Arquitecto de Sistemas de Información

### Nuestro proyecto dividido en capas

```
 [ Navegador: React/Vite :5173 ]      <- ARQUITECTO DE SI
             | HTTP/JSON (REST, CORS)
 [ API FastAPI / uvicorn :8000 ]      <- ARQUITECTO DE SI
             | Protocolo MySQL (mysql-connector) :3307
 [ MariaDB - licoreriadatabase ]      <- DBA
   InnoDB, buffer pool, índices, FK, triggers, usuarios, backups
```

### Comparación

| Aspecto | DBA (arquitectura de BD) | Arquitecto de SI |
|---|---|---|
| **Objetivo de diseño** | Integridad, consistencia (ACID), disponibilidad y rendimiento del dato | Cumplir procesos de negocio, integrar componentes, usabilidad, mantenibilidad |
| **Qué diseña** | Modelo lógico/físico: tablas, tipos, PK/FK, índices, particiones, motor (InnoDB), vistas, triggers, procedimientos | Capas: UI, API, servicios, autenticación, integración (REST), despliegue |
| **Métricas clave** | QPS/TPS, *buffer pool hit ratio* (>99 %), consultas lentas, bloqueos/deadlocks, RPO/RTO de backups, uso de disco | Tiempo de respuesta HTTP (latencia p95), throughput de peticiones, disponibilidad del servicio (SLA), errores 4xx/5xx, usuarios concurrentes |
| **Infraestructura** | RAM del servidor (`innodb_buffer_pool_size`), disco/IOPS, logs de transacción, replicación, `max_connections`, nivel de aislamiento | Servidores de app, contenedores, balanceadores, CORS, red, nube, CI/CD |
| **Seguridad** | Usuarios y `GRANT` en el motor, mínimo privilegio, cifrado en reposo | Autenticación de usuarios finales (tokens Bearer), roles de la app, HTTPS |
| **Herramienta en nuestro proyecto** | HeidiSQL | VS Code, Vite, uvicorn, Swagger (`/docs`) |

### Evidencia en nuestro proyecto
**Lado del DBA (correr en HeidiSQL, bloques 1.1 a 1.8 del script):**
1. **1.1** Motor, filas y tamaño de cada tabla → decisiones de *diseño físico*.
2. **1.2 / 1.3** Llaves foráneas e índices → *diseño lógico* y rendimiento.
3. **1.4** Triggers/procedimientos/vistas → lógica que vive dentro del motor.
4. **1.5** Variables de infraestructura (buffer pool, logs, `max_connections`, aislamiento).
5. **1.6** **Métricas del DBA**: QPS, consultas lentas, deadlocks, *hit ratio*.
6. **1.7** Usuario `app_licoreria` con solo DML → si intenta `DROP TABLE` sale **ERROR 1142**. El DBA protege el esquema aunque la aplicación falle.

**Lado del Arquitecto de SI (mostrar en el código):**
- `api/main.py`: `FastAPI(...)`, `CORSMiddleware` (qué frontends pueden llamar), endpoints `/healthz` y `/readyz` (métricas de disponibilidad del *servicio*, no del motor), autenticación `HTTPBearer`.
- `api/.env`: la app solo conoce *host/puerto/usuario* de la BD → la BD es una “caja negra” para el arquitecto.
- La API soporta **MariaDB y PostgreSQL** (`mysql.connector` y `psycopg`): el arquitecto puede cambiar de motor sin tocar el frontend. Eso es decisión de arquitectura de SI; cómo se indexa/almacena en cada motor es decisión del DBA.
- `frontend/vite.config.ts` → despliegue de la UI en `/licoreria/`.

**Conclusión:** el DBA optimiza *cómo se guarda y se accede al dato* (métricas del motor); el arquitecto optimiza *cómo fluye la información entre componentes hasta el usuario* (métricas del servicio). Un endpoint lento puede deberse a la red/API (arquitecto) o a una consulta sin índice (DBA): cada uno mide en su capa.

---

## Pregunta 2 — Cliente-Servidor NO es arquitectura interna de la BD

### Por qué es un error conceptual
- **Cliente-Servidor es un modelo de despliegue de software**: dice *qué proceso pide* y *qué proceso atiende* a través de la red. No dice nada de cómo el DBMS guarda páginas, usa memoria o reparte datos entre discos/CPUs.
- El **mismo** MariaDB puede atender clientes en 2 capas (HeidiSQL → MariaDB) o en 3 capas (React → FastAPI → MariaDB) **sin cambiar nada de su almacenamiento interno**. Si C/S fuera arquitectura interna, cambiar de 2 a 3 capas cambiaría el motor; no lo hace.
- La arquitectura interna (física) del DBMS se describe con **Shared Memory, Shared Disk, Shared Nothing** (cómo los procesadores comparten memoria y disco).

### Nuestro proyecto en ambas visiones

| | Nuestro caso |
|---|---|
| **2 capas** | HeidiSQL (cliente) ↔ MariaDB (servidor) |
| **3 capas** | React (presentación) ↔ FastAPI (lógica de negocio) ↔ MariaDB (datos) |
| **Arquitectura física del DBMS** | Un solo proceso `mariadbd` en un equipo, varios hilos que comparten el **mismo buffer pool (RAM)** y el **mismo datadir (disco)** → **Shared Memory / shared-everything (SMP)** |

### Contraste con arquitecturas paralelas

| Arquitectura | Qué se comparte | Escala | Ejemplo real |
|---|---|---|---|
| **Shared Memory** | CPUs comparten RAM y disco | Limitada (cuello de botella en bus de memoria) | MariaDB/PostgreSQL en un servidor multinúcleo (**nuestro caso**) |
| **Shared Disk** | Cada nodo tiene su RAM, todos acceden al mismo disco (SAN) | Media; requiere coordinar bloqueos de páginas | Oracle RAC, IBM Db2 pureScale |
| **Shared Nothing** | Cada nodo tiene su CPU, RAM y disco; los datos se particionan | Alta (lineal) | MariaDB Xpand/Spider, Galera (replicado), Cassandra, Teradata |
| **Cliente-Servidor** | *No aplica*: es separación de funciones entre programas | Se escala clonando clientes/APIs | Navegador → API → BD |

Clave: **Cliente-Servidor puede montarse sobre cualquiera de las tres**. Nuestra React+FastAPI seguiría igual si MariaDB pasara a un clúster shared-nothing; solo cambiaría el host en `api/.env`.

### Demostración en vivo (bloques 2.1 a 2.3 del script)
1. Levantar la API y el frontend:
   ```powershell
   cd api;      uvicorn main:app --reload --port 8000
   cd frontend; npm run dev
   ```
2. Abrir la app en el navegador y navegar (ej. productos/ventas).
3. En HeidiSQL ejecutar **2.1** (`PROCESSLIST`): aparecen la sesión de **HeidiSQL** y la(s) de la **API**. **El navegador no aparece** → el cliente web nunca toca la BD (3 capas).
4. Ejecutar **2.2**: un solo `datadir`, un solo `innodb_buffer_pool_size`, varios hilos → memoria y disco compartidos = **Shared Memory**.
5. Ejecutar **2.3** antes y después de repetir una consulta desde la app y desde HeidiSQL: las lecturas físicas a disco casi no suben → ambos clientes usan la **misma memoria compartida** del servidor.

**Conclusión:** Cliente-Servidor responde *“¿quién hace qué en el sistema de información?”*; Shared Memory/Disk/Nothing responde *“¿cómo está construido físicamente el motor de BD para procesar en paralelo?”*. Son niveles distintos.
