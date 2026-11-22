// ============================================================================
// POWER QUERY (M) — CLÚSTER HÍBRIDO "LA CAVA"  ·  7 consultas para Power BI
// ============================================================================
// Power BI Desktop lee los datos a través de la API (no necesita drivers ODBC).
// La API debe estar corriendo en la Laptop (balanceador en el puerto 8000).
//
// CÓMO USARLO (ver GUIA_POWER_BI.md para el paso a paso con capturas mentales):
//   Inicio -> Transformar datos -> (Editor de Power Query)
//   Inicio -> Nuevo origen -> Consulta en blanco
//   Clic derecho en la consulta -> Cambiar nombre  (usa EXACTAMENTE el nombre indicado)
//   Vista -> Editor avanzado -> borra todo -> pega el bloque -> Listo
//   Repite para cada una de las 7 consultas de abajo.
// ============================================================================


// ---------------------------------------------------------------------------
// CONSULTA 1 — Nombre: ApiLaCava   (parámetro de texto con la URL de la API)
// Si abres Power BI en OTRA máquina de la VPN, cámbialo a "http://100.123.81.4:8000"
// ---------------------------------------------------------------------------
"http://127.0.0.1:8000" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]


// ---------------------------------------------------------------------------
// CONSULTA 2 — Nombre: fact_ventas   (tabla de HECHOS del esquema estrella, BD 5 :3309)
// ---------------------------------------------------------------------------
let
    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/fact_ventas"])),
    Tabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(Tabla, {
        {"id_fact", Int64.Type}, {"id_sede", type text}, {"id_producto", type text}, {"id_tiempo", type text},
        {"usuario_rbac", type text}, {"rol_rbac", type text}, {"cantidad_botellas", Int64.Type},
        {"subtotal_usd", type number}, {"iva_usd", type number}, {"total_venta_usd", type number},
        {"etl_lote", type text}, {"fecha_carga_etl", type datetime}
    })
in
    Tipos


// ---------------------------------------------------------------------------
// CONSULTA 3 — Nombre: dim_sede
// ---------------------------------------------------------------------------
let
    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/dim/dim_sede"])),
    Tabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(Tabla, {
        {"id_sede", type text}, {"nombre_sede", type text}, {"ciudad", type text}, {"region", type text},
        {"maquina_fisica", type text}, {"motor_bd", type text}, {"puerto_tcp", Int64.Type}
    })
in
    Tipos


// ---------------------------------------------------------------------------
// CONSULTA 4 — Nombre: dim_producto
// ---------------------------------------------------------------------------
let
    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/dim/dim_producto"])),
    Tabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(Tabla, {
        {"id_producto", type text}, {"nombre_producto", type text}, {"categoria", type text},
        {"marca", type text}, {"precio_unitario", type number}
    })
in
    Tipos


// ---------------------------------------------------------------------------
// CONSULTA 5 — Nombre: dim_tiempo
// ---------------------------------------------------------------------------
let
    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/dim/dim_tiempo"])),
    Tabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(Tabla, {
        {"id_tiempo", type text}, {"fecha", type date}, {"anio", Int64.Type}, {"mes", Int64.Type},
        {"nombre_mes", type text}, {"trimestre", type text}
    })
in
    Tipos


// ---------------------------------------------------------------------------
// CONSULTA 6 — Nombre: operaciones_6bds   (lo que insertan los 6 agentes en las 6 BDs)
// SQL (BD 1, 3, 4, 5) + NoSQL (BD 2) + Cloud (BD 6) unificados con la columna origen_nodo
// ---------------------------------------------------------------------------
let
    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/operaciones_6bds", Query = [limit = "500"]])),
    Tabla = Table.FromRecords(Origen, {"id", "origen_nodo", "sede", "motor", "puerto", "modulo", "usuario_rbac", "rol_rbac", "detalle", "monto_usd", "fecha_hora"}, MissingField.UseNull),
    Tipos = Table.TransformColumnTypes(Tabla, {
        {"id", type text}, {"origen_nodo", type text}, {"sede", type text}, {"motor", type text},
        {"puerto", Int64.Type}, {"modulo", type text}, {"usuario_rbac", type text}, {"rol_rbac", type text},
        {"detalle", type text}, {"monto_usd", type number}, {"fecha_hora", type text}
    }),
    FechaHora = Table.TransformColumns(Tipos, {{"fecha_hora", each try DateTime.From(Text.Start(_, 19)) otherwise null, type datetime}})
in
    FechaHora


// ---------------------------------------------------------------------------
// CONSULTA 7 — Nombre: salud_nodos   (estado ONLINE/OFFLINE y latencia ms de las 6 BDs)
// ---------------------------------------------------------------------------
let
    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/salud_nodos"])),
    Tabla = Table.FromRecords(Origen),
    Tipos = Table.TransformColumnTypes(Tabla, {
        {"bd", type text}, {"sede", type text}, {"maquina", type text}, {"motor", type text},
        {"puerto", Int64.Type}, {"estado", type text}, {"latencia_ms", type number},
        {"tablas", Int64.Type}, {"tamano_kb", type number}, {"medido_en", type datetime}
    })
in
    Tipos
