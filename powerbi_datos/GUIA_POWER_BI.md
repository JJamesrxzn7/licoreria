# Power BI — "La Cava" (BD 5 DWH + 6 BDs del clúster)

Power BI Desktop lee todo **a través de la API** (`http://127.0.0.1:8000`), así que no hace falta
instalar drivers de MariaDB ni de PostgreSQL. Tiempo estimado: 10–15 minutos.

## 0. Antes de empezar

- La API debe estar corriendo en la Laptop (balanceador `:8000` + 3 réplicas).
  Prueba en el navegador: <http://127.0.0.1:8000/api/powerbi/dim/dim_sede> → debe salir un JSON.
- El Agente 5 (Mini-ETL) llena `fact_ventas` cada 60 s con las ventas nuevas de BD 1, BD 4 y BD 6.
  Si `fact_ventas` está vacía, en la GUI → Arquitectura → clic en **AG 5** → **Ejecutar 1 operación ahora**.

| Consulta en Power BI | Endpoint de la API | Origen real |
|---|---|---|
| `fact_ventas` | `/api/powerbi/fact_ventas` | BD 5 `db_gye_dwh.fact_ventas` (:3309) |
| `dim_sede` | `/api/powerbi/dim/dim_sede` | BD 5 |
| `dim_producto` | `/api/powerbi/dim/dim_producto` | BD 5 |
| `dim_tiempo` | `/api/powerbi/dim/dim_tiempo` | BD 5 |
| `operaciones_6bds` | `/api/powerbi/operaciones_6bds?limit=500` | Las 6 BDs (SQL + Mongo + Supabase) |
| `salud_nodos` | `/api/powerbi/salud_nodos` | Ping en vivo a las 6 BDs |

## 1. Cargar las 7 consultas

1. Abre **Power BI Desktop** → **Inicio → Transformar datos** (se abre el Editor de Power Query).
2. **Inicio → Nuevo origen → Consulta en blanco**.
3. En el panel de la izquierda, clic derecho sobre la consulta nueva → **Cambiar nombre** → `ApiLaCava`.
4. **Vista → Editor avanzado**, borra todo y pega el bloque **CONSULTA 1** de `LaCava_PowerQuery.pq`. **Listo**.
5. Repite los pasos 2–4 para las consultas 2 a 7, usando **exactamente** el nombre indicado en cada bloque
   (`fact_ventas`, `dim_sede`, `dim_producto`, `dim_tiempo`, `operaciones_6bds`, `salud_nodos`).
6. Si aparece *"Especifique cómo conectarse"* → **Editar credenciales** → **Anónimo** → **Conectar**.
   Si pregunta por **niveles de privacidad**, marca *Omitir* / *Público* para `127.0.0.1`.
7. **Inicio → Cerrar y aplicar**.

## 2. Relaciones del esquema estrella (vista Modelo)

Power BI suele detectarlas solo. Si no, arrastra en la vista **Modelo** (icono de 3 cajitas, a la izquierda):

| Desde (muchos) | Hacia (uno) |
|---|---|
| `fact_ventas[id_sede]` | `dim_sede[id_sede]` |
| `fact_ventas[id_producto]` | `dim_producto[id_producto]` |
| `fact_ventas[id_tiempo]` | `dim_tiempo[id_tiempo]` |

Las tres: cardinalidad **Varios a uno (*:1)**, dirección de filtro **Única**.
`operaciones_6bds` y `salud_nodos` quedan sueltas (son tablas de monitoreo, no del estrella).

## 3. Medidas

Abre `MEDIDAS_DAX.dax`. Selecciona la tabla `fact_ventas` → **Inicio → Nueva medida** → pega UNA línea
(por ejemplo `Ventas Totales USD = SUM ( fact_ventas[total_venta_usd] )`) → Enter. Repite para cada medida.

## 4. Dashboard sugerido (3 páginas)

**Página 1 — Ventas (OLAP / pregunta 6 del examen)**
- 4 tarjetas: `Ventas Totales USD`, `Botellas Vendidas`, `Ticket Promedio USD`, `Última Carga ETL`.
- Gráfico de columnas: eje `dim_sede[nombre_sede]`, valor `Ventas Totales USD`.
- Gráfico de anillo: leyenda `dim_producto[categoria]`, valor `Ventas Totales USD`.
- Gráfico de líneas: eje `dim_tiempo[nombre_mes]` (ordénalo por `dim_tiempo[mes]`: selecciona la columna
  `nombre_mes` → *Herramientas de columnas → Ordenar por columna → mes*), valor `Ventas Totales USD`.
- Segmentador (slicer): `dim_sede[ciudad]` y `fact_ventas[rol_rbac]`.

**Página 2 — Actividad de los 6 agentes (transparencia SGBDD / pregunta 4)**
- Matriz: filas `operaciones_6bds[origen_nodo]`, columnas `operaciones_6bds[modulo]`, valor `Operaciones Agentes`.
- Tabla: `fecha_hora`, `sede`, `usuario_rbac`, `detalle`, `monto_usd`.

**Página 3 — Salud del clúster (red y latencia / pregunta 8)**
- Tarjeta: `Estado Clúster`. Tarjeta: `Latencia Promedio ms`.
- Gráfico de barras: eje `salud_nodos[bd]`, valor `latencia_ms` (verás Supabase/WAN y Quito/Tailscale más lentos que la Laptop).
- Formato condicional del color de barra por `salud_nodos[estado]`.

## 5. Actualizar en vivo durante la defensa

- **Inicio → Actualizar** vuelve a llamar a la API: verás crecer `fact_ventas` (Agente 5) y cambiar la latencia.
- Guarda el archivo como `powerbi_datos/LaCava_Dashboard.pbix`.

## Alternativa sin API: CSV

`python exportar_powerbi.py` (en la raíz del proyecto) vuelca las 4 tablas del estrella a CSV en esta carpeta.
En Power BI: **Obtener datos → Texto/CSV** → carga los 4 archivos y crea las mismas relaciones del paso 2.
Los CSV son una foto fija: no se actualizan solos.
