from psycopg.rows import dict_row

from postgres_connection import connect_postgres


PURCHASE_CATALOG_QUERIES = {
    "proveedores": """
        SELECT TRIM(id_Proveedor) AS id, TRIM(prv_Nombre) AS nombre,
               TRIM(prv_RUC_CED) AS identificacion, ESTADO_PRV AS estado
        FROM PROVEEDORES ORDER BY prv_Nombre
    """,
    "productos": """
        SELECT TRIM(id_Producto) AS id, TRIM(pro_Descripcion) AS nombre,
               pro_Valor_Compra AS costo, pro_Precio_Venta AS precio,
               pro_Saldo_Final AS stock, ESTADO_PROD AS estado
        FROM PRODUCTOS ORDER BY pro_Descripcion
    """,
}

DOCUMENT_QUERIES = {
    "compras": (
        """
        SELECT TRIM(C.id_Compra) AS id, TRIM(C.id_Proveedor) AS "proveedorId",
               TRIM(P.prv_Nombre) AS proveedor, C.oc_Fecha AS fecha,
               C.oc_FechaEntrega AS "fechaEntrega", C.oc_Subtotal AS subtotal,
               C.oc_IVA AS iva, C.oc_Total AS total, C.ESTADO_OC AS estado,
               C.oc_tasaiva AS "tasaIVA"
        FROM COMPRAS C INNER JOIN PROVEEDORES P ON P.id_Proveedor = C.id_Proveedor
        ORDER BY C.oc_Fecha DESC, C.id_Compra DESC
        """,
        """
        SELECT TRIM(D.id_Compra) AS "compraId", TRIM(D.id_Producto) AS "productoId",
               TRIM(P.pro_Descripcion) AS producto, D.pxo_Cantidad AS cantidad,
               D.pxo_Valor AS "costoUnitario", D.pxo_Subtotal AS subtotal,
               D.ESTADO_PxOC AS estado
        FROM PROxOC D INNER JOIN PRODUCTOS P ON P.id_Producto = D.id_Producto
        ORDER BY D.id_Compra, P.pro_Descripcion
        """,
        "compraId",
    ),
    "ventas": (
        """
        SELECT TRIM(F.id_Factura) AS id, F.fac_Fecha AS date,
               TRIM(F.id_Cliente) AS "customerId", TRIM(C.cli_Nombre) AS "customerName",
               F.fac_Subtotal AS subtotal, F.fac_Descuento AS discount, 15.00 AS "taxRate",
               F.fac_IVA AS tax, F.fac_Total AS total, F.fac_FormaPago AS "paymentMethod",
               1 AS installments, F.ESTADO_FAC AS status
        FROM FACTURAS F INNER JOIN CLIENTES C ON F.id_Cliente = C.id_Cliente
        ORDER BY F.fac_Fecha DESC, F.id_Factura DESC
        """,
        """
        SELECT TRIM(D.id_Factura) AS "facturaId", TRIM(D.id_Producto) AS "productId",
               TRIM(P.pro_Descripcion) AS "productName", D.pxf_Cantidad AS qty,
               D.pxf_Precio AS price, D.pxf_Subtotal AS subtotal
        FROM PROxFAC D INNER JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
        ORDER BY D.id_Factura
        """,
        "facturaId",
    ),
    "recepciones": (
        """
        SELECT TRIM(R.id_Recibo) AS id, TRIM(R.id_Compra) AS "poId",
               R.rec_FechaHora AS date, R.ESTADO_REC AS status,
               R.rec_Descripcion AS description
        FROM RECEPCIONES R ORDER BY R.rec_FechaHora DESC
        """,
        """
        SELECT TRIM(D.id_Recibo) AS "reciboId", TRIM(D.id_Producto) AS "productId",
               TRIM(P.pro_Descripcion) AS "productName", D.pxr_Cantidad AS "expectedQty",
               D.pxr_Qty_Recibida AS "receivedQty",
               (D.pxr_Qty_Recibida - D.pxr_Cantidad) AS diff,
               COALESCE(TRIM(D.pxr_Motivo), '') AS reason
        FROM PROxREC D INNER JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
        ORDER BY D.id_Recibo
        """,
        "reciboId",
    ),
    "entregas": (
        """
        SELECT TRIM(E.id_Entrega) AS id, TRIM(E.id_Factura) AS "invoiceId",
               E.ent_FechaHora AS date, E.ESTADO_ENT AS status,
               E.ent_Descripcion AS description
        FROM ENTREGAS E ORDER BY E.ent_FechaHora DESC
        """,
        """
        SELECT TRIM(D.id_Entrega) AS "entregaId", TRIM(D.id_Producto) AS "productId",
               TRIM(P.pro_Descripcion) AS "productName", D.pxe_Cantidad AS "expectedQty",
               D.pxe_Qty_Entregada AS "deliveredQty",
               (D.pxe_Qty_Entregada - D.pxe_Cantidad) AS diff,
               COALESCE(TRIM(D.pxe_Motivo), '') AS reason
        FROM PROxENT D INNER JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
        ORDER BY D.id_Entrega
        """,
        "entregaId",
    ),
}


def listar_catalogos_compras() -> dict:
    with connect_postgres() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            result = {}
            for name, query in PURCHASE_CATALOG_QUERIES.items():
                cursor.execute(query)
                result[name] = cursor.fetchall()
            return result


def listar_documentos(tipo: str) -> list[dict]:
    header_query, detail_query, group_key = DOCUMENT_QUERIES[tipo]
    with connect_postgres() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(header_query)
            documents = cursor.fetchall()
            cursor.execute(detail_query)
            details_by_id = {}
            for item in cursor.fetchall():
                document_id = item.pop(group_key)
                details_by_id.setdefault(document_id, []).append(item)
            for document in documents:
                document["items"] = details_by_id.get(document["id"], [])
            return documents
