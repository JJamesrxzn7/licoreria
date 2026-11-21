# MATRIZ OFICIAL DE CREDENCIALES Y ROLES RBAC — CLÚSTER HÍBRIDO "LA CAVA"

Este documento contiene todas las credenciales oficiales provisionadas en las bases de datos relacionales (**BD 1 Quito `:3307`**, **BD 4 Guayaquil `:3306`** y **BD 6 Cuenca Cloud `:5432`**), tanto para:
1. **Iniciar sesión en la Interfaz Web "La Cava"** (`https://jjamesrxzn7.github.io/licoreria` o `http://127.0.0.1:8000/licoreria/`).
2. **Conectarse directamente al motor de Base de Datos** desde HeidiSQL / pgAdmin / DBeaver (`CREATE USER` + `GRANT`).
3. **Autenticar a los 6 Agentes IA Transaccionales** (`agentes_quito.py` en la PC de Escritorio y `agentes_gye_cuenca.py` en la Laptop).

---

## 1. USUARIOS DE GOBERNANZA: ADMINISTRADOR GENERAL Y DBA

| # | Usuario (`username`) | Contraseña | Rol en Aplicación | Rol en Motor BD | Colaborador Asignado | Alcance y Pantallas Disponibles |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **`admin`** | **`LaCavaAdmin2026*`** | `SuperAdministrador` (`ROL-ADM`) | `rol_admin` / `rol_jefe` | Sebastián Mendoza (*Administrador General del ERP*) | **Acceso Total (100%):** Ve todos los 5 módulos de negocio (Ventas, Bodega, Abastecimiento, Talento Humano, Contabilidad), Gestión de Usuarios, Auditoría y la sección **Arquitectura BD & SI (DBA)**. |
| **2** | **`dba`** | **`LaCavaDba2026*`** | `DBA_Arquitecto` (`ROL-DBA`) | `rol_dba` / `rol_jefe` | Alejandro Viteri (*Administrador de Bases de Datos - DBA*) | **Sección Exclusiva de Arquitectura & DBA:** Al iniciar sesión entra directamente a **`Arquitectura BD & SI (DBA)`** (Diagrama Maestro BD vs. SI, Consola Global de las 6 BDs, Prompt SQL/MongoDB, Simulador 2PC), además de **Auditoría**, **Usuarios** y **Resumen**. |

---

## 2. MATRIZ DE 15 USUARIOS OPERATIVOS POR MÓDULO (3 ROLES × 5 MÓDULOS)

En cada uno de los **5 Módulos del Negocio (`C`, `I`, `V`, `TH`, `Ctbl`)** existen exactamente **3 niveles jerárquicos**:
- **Jefe (`rol_jefe`):** Permisos `VER`, `CREAR`, `APROBAR` y `ANULAR` en su módulo (`GRANT ALL PRIVILEGES` en el esquema).
- **Supervisor (`rol_supervisor`):** Permisos `VER`, `CREAR` y `APROBAR` en su módulo (`GRANT SELECT, INSERT, UPDATE`).
- **Operativo (`rol_operador`):** Permisos `VER` y `CREAR` en su módulo (`GRANT SELECT, INSERT`).

### A. Módulo 1: Compras (`C` — Abastecimiento, Órdenes de Compra, Proveedores, Productos)

| # | Nivel / Rol | Usuario (`username`) | Contraseña | Rol Motor BD | Colaborador | Cédula | Pantallas Habilitadas en la Web |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **3** | **Jefe** | **`c_jefe`** | **`ComprasJefe2026*`** | `rol_jefe` | Roberto Gavilanes | `1714223318` | Resumen, Compras, Proveedores, Productos, Unidades de medida |
| **4** | **Supervisor** | **`c_supervisor`** | **`ComprasSup2026*`** | `rol_supervisor` | Valeria Salazar | `1715334429` | Resumen, Compras, Proveedores, Productos, Unidades de medida |
| **5** | **Operativo** | **`c_operador`** | **`ComprasOpe2026*`** | `rol_operador` | Mateo Cevallos | `1716445530` | Resumen, Compras, Proveedores, Productos, Unidades de medida |

### B. Módulo 2: Inventarios (`I` — Bodega, Ajustes Físicos, Recepciones, Entregas)

| # | Nivel / Rol | Usuario (`username`) | Contraseña | Rol Motor BD | Colaborador | Cédula | Pantallas Habilitadas en la Web |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **6** | **Jefe** | **`i_jefe`** | **`InveJefe2026*`** | `rol_jefe` | Fernando Baquerizo | `0912345672` | Resumen, Ajustes físicos, Recepciones, Entregas |
| **7** | **Supervisor** | **`i_supervisor`** | **`InveSup2026*`** | `rol_supervisor` | Gabriela Pincay | `0913456783` | Resumen, Ajustes físicos, Recepciones, Entregas |
| **8** | **Operativo** | **`i_operador`** | **`InveOpe2026*`** | `rol_operador` | Diego Zambrano | `0914567894` | Resumen, Ajustes físicos, Recepciones, Entregas |

### C. Módulo 3: Ventas (`V` — Punto de Venta POS, Facturas, Clientes)

| # | Nivel / Rol | Usuario (`username`) | Contraseña | Rol Motor BD | Colaborador | Cédula | Pantallas Habilitadas en la Web |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **9** | **Jefe** | **`v_jefe`** | **`VentasJefe2026*`** | `rol_jefe` | Carolina Andrade | `1717556641` | Resumen, Punto de venta, Facturas, Clientes |
| **10** | **Supervisor** | **`v_supervisor`** | **`VentasSup2026*`** | `rol_supervisor` | Andrés Villacís | `0915678905` | Resumen, Punto de venta, Facturas, Clientes |
| **11** | **Operativo** | **`v_operador`** | **`VentasOpe2026*`** | `rol_operador` | Camila Ordóñez | `0102345675` | Resumen, Punto de venta, Facturas, Clientes |

### D. Módulo 4: Talento Humano (`TH` — Ficha del Personal, Dependientes, Roles de Pago)

| # | Nivel / Rol | Usuario (`username`) | Contraseña | Rol Motor BD | Colaborador | Cédula | Pantallas Habilitadas en la Web |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **12** | **Jefe** | **`th_jefe`** | **`ThJefe2026*`** | `rol_jefe` | Patricia Espinosa | `1718667752` | Resumen, Ficha del personal, Roles de pago, Usuarios |
| **13** | **Supervisor** | **`th_supervisor`** | **`ThSup2026*`** | `rol_supervisor` | Santiago Mosquera | `1719778863` | Resumen, Ficha del personal, Roles de pago |
| **14** | **Operativo** | **`th_operador`** | **`ThOpe2026*`** | `rol_operador` | Daniela Cordero | `0103456786` | Resumen, Ficha del personal, Roles de pago |

### E. Módulo 5: Contabilidad (`Ctbl` — Libro Diario, Bancos, Centros de Costos, Reportes)

| # | Nivel / Rol | Usuario (`username`) | Contraseña | Rol Motor BD | Colaborador | Cédula | Pantallas Habilitadas en la Web |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **15** | **Jefe** | **`ctbl_jefe`** | **`CtblJefe2026*`** | `rol_jefe` | Ricardo Peñaherrera | `1720889974` | Resumen, Contabilidad, Bancos, Centros de costos, Reportes |
| **16** | **Supervisor** | **`ctbl_supervisor`** | **`CtblSup2026*`** | `rol_supervisor` | Mónica Arosemena | `0916789016` | Resumen, Contabilidad, Bancos, Centros de costos, Reportes |
| **17** | **Operativo** | **`ctbl_operador`** | **`CtblOpe2026*`** | `rol_operador` | Esteban Crespo | `0104567897` | Resumen, Contabilidad, Bancos, Centros de costos, Reportes |

---

## 3. ASIGNACIÓN DE CREDENCIALES A LOS 6 AGENTES IA Y BASES DE DATOS

| Agente IA | Máquina Física | Header `X-Sede` | Base de Datos Destino | Puerto | Usuarios y Contraseñas que Utiliza |
| :--- | :--- | :--- | :--- | :-: | :--- |
| **Agente 1** (`agentes_quito.py`) | PC Escritorio (`100.77.220.102`) | `QUITO` | **BD 1:** MariaDB `licoreriadatabase` | `3307` | Rota entre los 15 usuarios (`c_jefe` / `ComprasJefe2026*`, ..., `ctbl_operador` / `CtblOpe2026*`) |
| **Agente 2** (`agentes_quito.py`) | PC Escritorio (`100.77.220.102`) | `QUITO_NOSQL` | **BD 2:** MongoDB `quito_nosql_mongo` | `27017` | Rota entre los 15 usuarios RBAC enviando telemetría JSON y alertas de stock |
| **Agente 3** (`agentes_quito.py`) | PC Escritorio (`100.77.220.102`) | `QUITO_PARALELA` | **BD 3:** MariaDB `quito_paralela_db` (`PARTITION BY HASH 4`) | `3308` | Rota entre los 15 usuarios RBAC insertando lotes en las 4 particiones hash |
| **Agente 4** (`agentes_gye_cuenca.py`) | Laptop (`100.123.81.4`) | `GUAYAQUIL` | **BD 4:** MariaDB Local `licoreriadatabase` | `3306` | Rota entre los 15 usuarios (`c_jefe` / `ComprasJefe2026*`, ..., `ctbl_operador` / `CtblOpe2026*`) |
| **Agente 5** (`agentes_gye_cuenca.py`) | Laptop (`100.123.81.4`) | `GUAYAQUIL_DWH` | **BD 5:** MariaDB DWH `db_gye_dwh` (Esquema Estrella Power BI) | `3309` | Usuarios de Ventas y Contabilidad (`v_jefe`, `v_supervisor`, `ctbl_jefe`, `ctbl_supervisor`) |
| **Agente 6** (`agentes_gye_cuenca.py`) | Laptop (`100.123.81.4`) | `CUENCA` | **BD 6:** PostgreSQL / Supabase `cloud_cuenca_loja` | `5432` | Rota entre los 15 usuarios RBAC registrando transacciones australes y latencia WAN |

---

## 4. CREDENCIALES ADMINISTRATIVAS DE LOS MOTORES FÍSICOS (PARA HEIDISQL / PGADMIN / COMPASS / POWER BI)

- **MariaDB (BD 1 `:3307`, BD 3 `:3308`, BD 4 `:3306`, BD 5 `:3309`):**
  - Usuario Root del Motor: `root` | Contraseña: `1597.MyHql`
  - También puedes entrar a HeidiSQL con cualquiera de los 17 usuarios de la tabla superior y su respectiva contraseña (ej. `v_jefe` / `VentasJefe2026*` o `dba` / `LaCavaDba2026*`).
- **MongoDB (BD 2 `:27017`):**
  - URI: `mongodb://100.77.220.102:27017/quito_nosql_mongo` (o `mongodb://127.0.0.1:27017/quito_nosql_mongo`)
- **PostgreSQL 18 / Supabase (BD 6 `:5432`):**
  - Local Mirror: Host `127.0.0.1` | Puerto `5432` | Base `cloud_cuenca_loja` | Usuario `postgres` | Contraseña `147852369.MyPost`
  - Supabase Pooler: Host `aws-0-us-east-1.pooler.supabase.com` | Puerto `5432` | Usuario `postgres.izyglalrpkhidyhkgknz` | Contraseña `1471581269.Kjs`
