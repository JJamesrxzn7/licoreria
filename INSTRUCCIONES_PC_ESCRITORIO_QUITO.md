# INSTRUCCIONES ACTUALIZADAS PARA LA PC DE ESCRITORIO — NODO QUITO (`jerxmy-01` · `100.77.220.102`)

## 0. ESTADO DE LA RED TAILSCALE Y TOPOLOGÍA
- **`IP_TS_QUITO` (Esta PC de Escritorio `jerxmy-01`):** `100.77.220.102`
- **`IP_TS_GUAYAQUIL` (La Laptop `desktop-6jdt8q0`):** `100.123.81.4`
- **URL del Balanceador de las 3 Réplicas API en la Laptop:** `http://100.123.81.4:8000/api`
- **Interfaz Web "La Cava":** Desplegada en **GitHub Pages** (`https://jjamesrxzn7.github.io/licoreria/`) y también servida localmente por el balanceador en `http://100.123.81.4:8000/licoreria/`.

---

## 1. SINCRONIZAR EL REPOSITORIO EN LA PC DE ESCRITORIO
En la PC de Escritorio abre una terminal en la carpeta del proyecto y haz `git pull` para traer los scripts de aprovisionamiento de los **17 usuarios oficiales (`15 por módulo + dba + admin`)** y los agentes actualizados:

```powershell
git pull origin main
```

---

## 2. ABRIR PUERTOS `3307`, `3308` Y `27017` EN EL FIREWALL DE WINDOWS (OBLIGATORIO)
Ejecuta en **PowerShell como Administrador** en la PC de Escritorio:

```powershell
New-NetFirewallRule -DisplayName "LaCava Quito Cluster (Tailscale 3307, 3308, 27017)" `
  -Direction Inbound -Protocol TCP -LocalPort 3307,3308,27017 -Action Allow
```

---

## 3. LEVANTAR LAS 3 BASES DE DATOS DE QUITO Y CARGAR LOS 17 USUARIOS RBAC

### Opción A: Con el script automático de Python (si tienes MariaDB y MongoDB instalados en la PC de Escritorio)
Ejecuta directamente los dos scripts que ya están en la carpeta `API/`:

```powershell
python API/provision_hybrid_cluster_6dbs.py
python API/provision_17_users_rbac.py
```

Esto creará automáticamente en tu PC de Escritorio:
1. **`BD 1` (`:3307` — MariaDB `licoreriadatabase`):**
   - Los 5 módulos (`compras`, `productos`, `facturas`, `empleados`, `asientos`) y la tabla `operaciones_agentes_ia`.
   - Los **17 usuarios oficiales** con sus contraseñas reales tanto para el login web (`USUARIOS` con hash PBKDF2-SHA256) como a nivel de motor MariaDB (`CREATE USER` + `GRANT` a `rol_jefe`, `rol_supervisor`, `rol_operador`, `rol_dba`, `rol_admin`) y en la tabla `rbac_matriz_15_usuarios`.
2. **`BD 2` (`:27017` — MongoDB `quito_nosql_mongo`):**
   - Colecciones `logs_auditoria` y `eventos_agentes`.
3. **`BD 3` (`:3308` — MariaDB `quito_paralela_db`):**
   - Tabla masiva `historico_transacciones` particionada con **`PARTITION BY HASH(id) PARTITIONS 4`** (*Speed-up*).

### Opción B: Con Docker (`docker-compose.quito.yml`)
Si usas Docker en la PC de Escritorio, levanta los 3 contenedores en `0.0.0.0:3307`, `0.0.0.0:27017` y `0.0.0.0:3308`, y luego corre `python API/provision_hybrid_cluster_6dbs.py` y `python API/provision_17_users_rbac.py` para poblarlos con los 17 usuarios y las tablas particionadas.

---

## 4. TABLA DE LOS 17 USUARIOS Y CONTRASEÑAS QUE USA LA PC DE ESCRITORIO

Todos los detalles están en `USUARIOS_Y_CONTRASENAS_RBAC.md`. Resumen rápido para los agentes de Quito:

| Rol / Módulo | Usuario (`username`) | Contraseña | Rol Motor BD |
| :--- | :--- | :--- | :--- |
| **Administrador General (Todo el ERP)** | `admin` | `LaCavaAdmin2026*` | `rol_admin` / `rol_jefe` |
| **DBA (Sección Arquitectura BD & SI)** | `dba` | `LaCavaDba2026*` | `rol_dba` / `rol_jefe` |
| **Compras (`C`)** | `c_jefe` / `c_supervisor` / `c_operador` | `ComprasJefe2026*` / `ComprasSup2026*` / `ComprasOpe2026*` | `rol_jefe` / `rol_supervisor` / `rol_operador` |
| **Inventarios (`I`)** | `i_jefe` / `i_supervisor` / `i_operador` | `InveJefe2026*` / `InveSup2026*` / `InveOpe2026*` | `rol_jefe` / `rol_supervisor` / `rol_operador` |
| **Ventas (`V`)** | `v_jefe` / `v_supervisor` / `v_operador` | `VentasJefe2026*` / `VentasSup2026*` / `VentasOpe2026*` | `rol_jefe` / `rol_supervisor` / `rol_operador` |
| **Talento Humano (`TH`)** | `th_jefe` / `th_supervisor` / `th_operador` | `ThJefe2026*` / `ThSup2026*` / `ThOpe2026*` | `rol_jefe` / `rol_supervisor` / `rol_operador` |
| **Contabilidad (`Ctbl`)** | `ctbl_jefe` / `ctbl_supervisor` / `ctbl_operador` | `CtblJefe2026*` / `CtblSup2026*` / `CtblOpe2026*` | `rol_jefe` / `rol_supervisor` / `rol_operador` |

---

## 5. ENCENDER LOS 3 AGENTES IA DE QUITO (`agentes_quito.py`)
En la PC de Escritorio ejecuta:

```powershell
python agentes_quito.py
```

El script `agentes_quito.py` ya viene configurado con las 15 credenciales reales de arriba y apunta automáticamente a la IP Tailscale de la Laptop (`http://100.123.81.4:8000/api/agentes/operacion`) enviando los headers `X-Sede: QUITO`, `X-Sede: QUITO_NOSQL` y `X-Sede: QUITO_PARALELA` cada 60 segundos.
