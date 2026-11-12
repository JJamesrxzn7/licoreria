from psycopg.rows import dict_row

from postgres_connection import connect_postgres


QUERIES = {
    "productos": """
        SELECT TRIM(P.id_Producto) AS id, TRIM(P.pro_Descripcion) AS name,
               TRIM(P.id_Producto) AS sku,
               CONCAT('786', LPAD(ASCII(SUBSTRING(P.id_Producto, 1, 1))::text, 6, '0')) AS barcode,
               COALESCE(TRIM(M.mar_Nombre), 'Sin Marca') AS brand,
               COALESCE(TRIM(C.cat_Nombre), 'Licores') AS category,
               750 AS ml, 40 AS abv, P.pro_Valor_Compra AS cost,
               P.pro_Precio_Venta AS price, P.pro_Saldo_Final AS stock,
               P.pro_Saldo_Inicial AS "minStock", TRIM(P.pro_UM_Compra) AS "buyUnitId",
               COALESCE(TRIM(UC.um_Descripcion), TRIM(P.pro_UM_Compra)) AS "buyUnit",
               TRIM(P.pro_UM_Venta) AS "sellUnitId",
               COALESCE(TRIM(UV.um_Descripcion), TRIM(P.pro_UM_Venta)) AS "sellUnit",
               COALESCE(UC.um_FactorConversion, 1.00) AS "purchaseFactor",
               COALESCE(UV.um_FactorConversion, 1.00) AS "sellFactor",
               ROUND(COALESCE(UC.um_FactorConversion, 1.00) /
                     NULLIF(COALESCE(UV.um_FactorConversion, 1.00), 0), 2) AS "factorConversion",
               COALESCE(
                   TRIM(H.pch_Descripcion),
                   CASE WHEN H.pch_Letra IS NOT NULL AND H.pch_Nivel IS NOT NULL
                        THEN CONCAT('Percha ', TRIM(H.pch_Letra), H.pch_Nivel) END,
                   'A1'
               ) AS shelf,
               TRIM(P.id_Percha) AS "shelfId",
               CASE WHEN P.ESTADO_PROD = 'ACT' THEN 'ACTIVE' ELSE 'INACTIVE' END AS status
        FROM PRODUCTOS P
        LEFT JOIN MARCAS M ON P.id_Marca = M.id_Marca
        LEFT JOIN CATEGORIAS C ON P.id_Categoria = C.id_Categoria
        LEFT JOIN UNIDADES_MEDIDAS UC ON P.pro_UM_Compra = UC.id_Unidad_Medida
        LEFT JOIN UNIDADES_MEDIDAS UV ON P.pro_UM_Venta = UV.id_Unidad_Medida
        LEFT JOIN PERCHAS H ON P.id_Percha = H.id_Percha
        ORDER BY P.pro_Descripcion
    """,
    "clientes": """
        SELECT TRIM(C.id_Cliente) AS id, TRIM(C.cli_RUC_CED) AS "ciRuc",
               TRIM(C.cli_Nombre) AS name, TRIM(C.cli_Telefono) AS contact,
               TRIM(C.cli_Mail) AS email, COALESCE(TRIM(CI.ciu_Descripcion), 'Quito') AS city,
               TRIM(C.cli_Direccion) AS address,
               CASE WHEN LENGTH(TRIM(C.cli_RUC_CED)) = 13 THEN 'JUR' ELSE 'NAT' END AS type,
               C.cli_MontoMaxCredito AS "creditLimit", 0.00 AS "creditUsed",
               C.cli_Descuento AS "discountRate",
               CASE WHEN C.ESTADO_CLI = 'ACT' THEN 'ACTIVE' ELSE 'INACTIVE' END AS status
        FROM CLIENTES C LEFT JOIN CIUDADES CI ON C.id_Ciudad = CI.id_Ciudad
        ORDER BY C.cli_Nombre
    """,
    "proveedores": """
        SELECT TRIM(P.id_Proveedor) AS id, TRIM(P.prv_RUC_CED) AS ruc,
               TRIM(P.prv_Nombre) AS name, TRIM(P.prv_Telefono) AS contact,
               TRIM(P.prv_Celular) AS mobile, TRIM(P.prv_Mail) AS email,
               COALESCE(TRIM(CI.ciu_Descripcion), 'Quito') AS city,
               TRIM(P.id_Ciudad) AS "cityId", TRIM(P.prv_Direccion) AS address,
               CASE WHEN P.ESTADO_PRV = 'ACT' THEN 'ACTIVE' ELSE 'INACTIVE' END AS status
        FROM PROVEEDORES P LEFT JOIN CIUDADES CI ON P.id_Ciudad = CI.id_Ciudad
        ORDER BY P.id_Proveedor DESC
    """,
}


def listar(tipo: str, include_cost: bool = True) -> list[dict]:
    with connect_postgres() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(QUERIES[tipo])
            rows = cursor.fetchall()
            if tipo == "productos":
                for row in rows:
                    if not include_cost:
                        row.pop("cost", None)
                    for field in ("purchaseFactor", "sellFactor", "factorConversion"):
                        row[field] = float(row[field]) if row[field] is not None else 1.0
            return rows
