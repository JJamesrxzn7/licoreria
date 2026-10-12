import logging
import os
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

import mysql.connector  # type: ignore
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Cargar variables de entorno desde .env (con fallback si python-dotenv no estuviera instalado)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, val = stripped.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

logger = logging.getLogger(__name__)
app = FastAPI(title="Licorería La Cava - API de Bases de Datos II")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CENT = Decimal("0.01")


def get_db_config() -> dict[str, str | int | bool]:
    password = os.getenv("MARIADB_PASSWORD", "")
    try:
        port = int(os.getenv("MARIADB_PORT", "3307"))
    except ValueError as error:
        raise HTTPException(
            status_code=500, detail="La variable MARIADB_PORT no es válida."
        ) from error
    return {
        "host": os.getenv("MARIADB_HOST", "localhost"),
        "port": port,
        "user": os.getenv("MARIADB_USER", "root"),
        "password": password,
        "database": os.getenv("MARIADB_DATABASE", "licoreriadatabase"),
        "use_pure": True,
    }


def get_user_id(cursor=None) -> str:
    """
    Obtiene un id_Usuario de la tabla USUARIOS de la aplicación si existe.
    El usuario de conexión MariaDB (ej. 'root') no pertenece a las tablas de la app,
    por lo que aquí solo consultamos la tabla USUARIOS de la base de datos si existe algún registro.
    """
    if cursor is not None:
        try:
            env_user = os.getenv("MARIADB_USER_ID", "").strip()
            if env_user:
                cursor.execute("SELECT id_Usuario FROM USUARIOS WHERE id_Usuario = %s LIMIT 1", (env_user,))
                row = cursor.fetchone()
                if row:
                    return str(row[0] if isinstance(row, tuple) else row["id_Usuario"]).strip()

            cursor.execute("SELECT id_Usuario FROM USUARIOS ORDER BY id_Usuario ASC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return str(row[0] if isinstance(row, tuple) else row["id_Usuario"]).strip()
        except Exception as e:
            logger.debug("No se pudo obtener usuario de USUARIOS: %s", e)

    return os.getenv("MARIADB_USER_ID", "USR-000001").strip()[:16]


def raise_database_error(error: mysql.connector.Error) -> None:
    if error.errno == 1305:
        raise HTTPException(
            status_code=503,
            detail=f"Falta instalar el procedimiento o vista requerido en MariaDB: {error.msg}",
        ) from error
    if error.errno == 1644:
        raise HTTPException(status_code=409, detail=str(error.msg)) from error
    if error.errno in {1045, 2002, 2003, 2005}:
        logger.error("No fue posible conectar con MariaDB: %s", error)
        raise HTTPException(
            status_code=503,
            detail=f"No fue posible conectar con MariaDB en el puerto configurado. Detalle: {error.msg}",
        ) from error
    if error.errno in {1062, 1452, 3819}:
        raise HTTPException(
            status_code=409,
            detail=f"Restricción de base de datos violada: {error.msg}",
        ) from error
    logger.exception("Error de base de datos no clasificado.")
    raise HTTPException(
        status_code=500, detail=f"Error en MariaDB: {error.msg}"
    ) from error


# ==========================================
# MODELOS PYDANTIC
# ==========================================

class PurchaseItemInput(BaseModel):
    product_id: str = Field(alias="idProducto", min_length=1, max_length=10)
    quantity: int = Field(alias="cantidad", gt=0)
    unit_cost: Decimal = Field(alias="costoUnitario", ge=0, max_digits=7, decimal_places=2)


class PurchaseOrderInput(BaseModel):
    supplier_id: str = Field(alias="idProveedor", min_length=1, max_length=10)
    delivery_date: datetime | None = Field(default=None, alias="fechaEntrega")
    tax_rate: Decimal = Field(default=Decimal("0"), alias="tasaIVA", ge=0, le=100)
    items: list[PurchaseItemInput] = Field(min_length=1)


class SaleItemInput(BaseModel):
    product_id: str = Field(alias="idProducto")
    quantity: int = Field(alias="cantidad", gt=0)
    unit_price: Decimal = Field(alias="precioUnitario", ge=0)


class SaleOrderInput(BaseModel):
    customer_id: str = Field(alias="idCliente")
    employee_id: str = Field(default="EMP-000001", alias="idEmpleado")
    description: str = Field(default="Venta en Punto de Venta", alias="descripcion")
    tax_rate: Decimal = Field(default=Decimal("15"), alias="tasaIVA")
    payment_method: str = Field(default="CASH", alias="metodoPago")
    installments: int = Field(default=1, alias="cuotas")
    items: list[SaleItemInput] = Field(min_length=1)


class CustomerInput(BaseModel):
    id: str | None = None
    name: str = Field(alias="nombre", min_length=2, max_length=40)
    ci_ruc: str = Field(alias="ciRuc", min_length=10, max_length=13)
    phone: str = Field(default="", alias="telefono")
    email: str = Field(default="", alias="email")
    city_id: str = Field(default="UIO", alias="idCiudad")
    mobile: str = Field(default="", alias="celular")
    address: str = Field(default="", alias="direccion")
    credit_limit: Decimal = Field(default=Decimal("0"), alias="cupoCredito")
    discount: Decimal = Field(default=Decimal("0"), alias="descuento")
    status: str = Field(default="ACT", alias="estado")


class SupplierInput(BaseModel):
    id: str | None = None
    name: str = Field(alias="nombre", min_length=2, max_length=40)
    ruc: str = Field(alias="ruc", min_length=10, max_length=13)
    phone: str = Field(default="", alias="telefono")
    email: str = Field(default="", alias="email")
    city_id: str = Field(default="UIO", alias="idCiudad")
    mobile: str = Field(default="", alias="celular")
    address: str = Field(default="", alias="direccion")
    status: str = Field(default="ACT", alias="estado")


class ProductInput(BaseModel):
    id: str | None = None
    name: str = Field(alias="nombre", min_length=2, max_length=40)
    category_id: str = Field(default="CAT-000001", alias="idCategoria")
    brand_id: str = Field(default="MAR-000001", alias="idMarca")
    buy_unit: str = Field(default="CAJ", alias="umCompra")
    sell_unit: str = Field(default="BOT", alias="umVenta")
    buy_cost: Decimal = Field(alias="costoCompra", ge=0)
    sell_price: Decimal = Field(alias="precioVenta", ge=0)
    initial_stock: int = Field(default=0, alias="stockInicial")


class PhysicalAdjustmentInput(BaseModel):
    employee_id: str = Field(default="EMP-000001", alias="idEmpleado")
    product_id: str = Field(alias="idProducto")
    type: str = Field(alias="tipo")  # 'IN' o 'OUT'
    quantity: int = Field(alias="cantidad", gt=0)
    reason: str = Field(alias="motivo")


class JournalEntryLineInput(BaseModel):
    account_id: str = Field(alias="idCuenta")
    debit: Decimal = Field(default=Decimal("0"), alias="debe")
    credit: Decimal = Field(default=Decimal("0"), alias="haber")


class JournalEntryInput(BaseModel):
    description: str = Field(alias="descripcion", max_length=30)
    lines: list[JournalEntryLineInput] = Field(min_length=2)


class ReceptionConfirmInput(BaseModel):
    items: list[dict[str, object]]  # [{ "productId": str, "receivedQty": int, "reason": str }]


class DeliveryConfirmInput(BaseModel):
    items: list[dict[str, object]]  # [{ "productId": str, "deliveredQty": int, "reason": str }]


class PayrollInput(BaseModel):
    description: str = Field(alias="descripcion", max_length=40)
    start_date: date = Field(alias="fechaInicio")
    end_date: date = Field(alias="fechaFin")
    employee_id: str = Field(alias="idEmpleado")
    base_salary: Decimal = Field(alias="sueldoBase")
    bonus: Decimal = Field(default=Decimal("0"), alias="bonificaciones")
    deductions: Decimal = Field(default=Decimal("0"), alias="descuentos")


class AccountInput(BaseModel):
    id: str = Field(alias="idCuenta", min_length=1, max_length=15)
    name: str = Field(alias="nombre", min_length=2, max_length=60)
    type: str = Field(default="COR", alias="tipo")


# ==========================================
# 0. CATÁLOGOS AUXILIARES (Ciudades, Unidades, Categorías, Marcas, Perchas, Bancos)
# ==========================================

@app.get("/api/catalogos/generales")
def obtener_catalogos_generales():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)

        cur.execute("SELECT TRIM(id_Ciudad) AS id, TRIM(ciu_Descripcion) AS nombre, TRIM(ciu_Provincia) AS provincia, TRIM(ciu_Region) AS region FROM CIUDADES ORDER BY ciu_Descripcion")
        ciudades = cur.fetchall()

        cur.execute("SELECT TRIM(id_Unidad_Medida) AS id, TRIM(um_Descripcion) AS nombre, um_FactorConversion AS factor FROM UNIDADES_MEDIDAS ORDER BY um_Descripcion")
        unidades = cur.fetchall()

        cur.execute("SELECT TRIM(id_Categoria) AS id, TRIM(cat_Nombre) AS nombre FROM CATEGORIAS WHERE ESTADO_CAT = 'ACT' OR ESTADO_CAT IS NULL ORDER BY cat_Nombre")
        categorias = cur.fetchall()

        cur.execute("SELECT TRIM(id_Marca) AS id, TRIM(mar_Nombre) AS nombre FROM MARCAS WHERE ESTADO_MAR = 'ACT' OR ESTADO_MAR IS NULL ORDER BY mar_Nombre")
        marcas = cur.fetchall()

        cur.execute("SELECT TRIM(id_Percha) AS id, TRIM(pch_Descripcion) AS nombre, TRIM(pch_Letra) AS letra, pch_Nivel AS nivel FROM PERCHAS WHERE ESTADO_PCH = 'ACT' OR ESTADO_PCH IS NULL ORDER BY pch_Letra, pch_Nivel")
        perchas = cur.fetchall()

        cur.execute("SELECT TRIM(id_Banco) AS id, TRIM(ban_Nombre) AS nombre FROM BANCOS WHERE ESTADO_BAN = 'ACT' OR ESTADO_BAN IS NULL ORDER BY ban_Nombre")
        bancos = cur.fetchall()

        return {
            "ciudades": ciudades,
            "unidadesMedida": unidades,
            "categorias": categorias,
            "marcas": marcas,
            "perchas": perchas,
            "bancos": bancos,
        }
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/ciudades")
def listar_ciudades():
    return obtener_catalogos_generales()["ciudades"]


@app.get("/api/unidades-medida")
def listar_unidades_medida():
    return obtener_catalogos_generales()["unidadesMedida"]


@app.get("/api/categorias")
def listar_categorias():
    return obtener_catalogos_generales()["categorias"]


@app.get("/api/marcas")
def listar_marcas():
    return obtener_catalogos_generales()["marcas"]


# ==========================================
# 1. MÓDULO ABASTECIMIENTO / COMPRAS
# ==========================================

@app.get("/api/compras/catalogos")
def listar_catalogos_compras():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT TRIM(id_Proveedor) AS id, TRIM(prv_Nombre) AS nombre,
                   TRIM(prv_RUC_CED) AS identificacion, ESTADO_PRV AS estado
            FROM PROVEEDORES
            ORDER BY prv_Nombre
            """
        )
        suppliers = cur.fetchall()
        cur.execute(
            """
            SELECT TRIM(id_Producto) AS id, TRIM(pro_Descripcion) AS nombre,
                   pro_Valor_Compra AS costo, pro_Precio_Venta AS precio,
                   pro_Saldo_Final AS stock, ESTADO_PROD AS estado
            FROM PRODUCTOS
            ORDER BY pro_Descripcion
            """
        )
        products = cur.fetchall()
        return {"proveedores": suppliers, "productos": products}
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/compras")
def listar_compras():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT TRIM(C.id_Compra) AS id, TRIM(C.id_Proveedor) AS proveedorId,
                   TRIM(P.prv_Nombre) AS proveedor, C.oc_Fecha AS fecha,
                   C.oc_FechaEntrega AS fechaEntrega, C.oc_Subtotal AS subtotal,
                   C.oc_IVA AS iva, C.oc_Total AS total, C.ESTADO_OC AS estado
            FROM COMPRAS C
            INNER JOIN PROVEEDORES P ON P.id_Proveedor = C.id_Proveedor
            ORDER BY C.oc_Fecha DESC, C.id_Compra DESC
            """
        )
        orders = cur.fetchall()
        cur.execute(
            """
            SELECT TRIM(D.id_Compra) AS compraId, TRIM(D.id_Producto) AS productoId,
                   TRIM(P.pro_Descripcion) AS producto, D.pxo_Cantidad AS cantidad,
                   D.pxo_Valor AS costoUnitario, D.pxo_Subtotal AS subtotal,
                   D.ESTADO_PxOC AS estado
            FROM PROxOC D
            INNER JOIN PRODUCTOS P ON P.id_Producto = D.id_Producto
            ORDER BY D.id_Compra, P.pro_Descripcion
            """
        )
        details_by_order: dict[str, list[dict[str, object]]] = {}
        for item in cur.fetchall():
            order_id = item.pop("compraId")
            details_by_order.setdefault(order_id, []).append(item)
        for order in orders:
            order["items"] = details_by_order.get(order["id"], [])
            subtotal = Decimal(str(order["subtotal"]))
            tax = Decimal(str(order["iva"]))
            order["tasaIVA"] = (
                (tax * 100 / subtotal).quantize(CENT, rounding=ROUND_HALF_UP)
                if subtotal
                else Decimal("0.00")
            )
        return orders
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/compras")
def crear_compra(purchase: PurchaseOrderInput):
    if len({item.product_id for item in purchase.items}) != len(purchase.items):
        raise HTTPException(
            status_code=422, detail="Cada producto debe aparecer una sola vez."
        )

    items_with_subtotal = [
        (
            item,
            (Decimal(item.quantity) * item.unit_cost).quantize(
                CENT, rounding=ROUND_HALF_UP
            ),
        )
        for item in purchase.items
    ]
    subtotal = sum((line_subtotal for _, line_subtotal in items_with_subtotal), Decimal("0"))
    tax = (subtotal * purchase.tax_rate / 100).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    total = subtotal + tax
    if max(subtotal, tax, total) >= Decimal("100000"):
        raise HTTPException(
            status_code=422,
            detail="El total supera la capacidad NUMERIC(7,2) de la base de datos.",
        )

    order_id = f"OC{uuid4().hex[:8].upper()}"
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.execute(
            "SELECT 1 FROM PROVEEDORES WHERE id_Proveedor = %s AND ESTADO_PRV = 'ACT'",
            (purchase.supplier_id,),
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=422, detail="El proveedor no existe o no está activo."
            )
        product_ids = [item.product_id for item in purchase.items]
        placeholders = ", ".join(["%s"] * len(product_ids))
        cur.execute(
            f"SELECT TRIM(id_Producto) FROM PRODUCTOS WHERE ESTADO_PROD = 'ACT' AND id_Producto IN ({placeholders})",
            tuple(product_ids),
        )
        active_product_ids = {row[0] for row in cur.fetchall()}
        if active_product_ids != set(product_ids):
            raise HTTPException(
                status_code=422,
                detail="Uno o más productos no existen o no están activos.",
            )
        try:
            cur.callproc(
                "SP_COMPRA_CREAR",
                (
                    order_id,
                    purchase.supplier_id,
                    purchase.delivery_date,
                    subtotal,
                    tax,
                    total,
                    user_id,
                ),
            )
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                cur.execute(
                    """
                    INSERT INTO COMPRAS
                        (id_Compra, id_Proveedor, oc_Fecha, oc_FechaEntrega, oc_Subtotal, oc_IVA, oc_Total, ESTADO_OC)
                    VALUES (%s, %s, NOW(), %s, %s, %s, %s, 'ABI')
                    """,
                    (order_id, purchase.supplier_id, purchase.delivery_date, subtotal, tax, total),
                )
            else:
                raise
        for item, line_subtotal in items_with_subtotal:
            cur.execute(
                """
                INSERT INTO PROxOC
                    (id_Compra, id_Producto, pxo_Cantidad, pxo_Valor,
                     pxo_Subtotal, ESTADO_PxOC)
                VALUES (%s, %s, %s, %s, %s, 'ABI')
                """,
                (
                    order_id,
                    item.product_id,
                    item.quantity,
                    item.unit_cost,
                    line_subtotal,
                ),
            )
        conn.commit()
        return {
            "id": order_id,
            "estado": "ABI",
            "subtotal": str(subtotal),
            "iva": str(tax),
            "total": str(total),
            "mensaje": f"Orden {order_id} creada.",
        }
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


def cambiar_estado_compra(order_id: str, procedure: str) -> dict[str, str]:
    if len(order_id) > 10:
        raise HTTPException(status_code=422, detail="El identificador de compra no es válido.")
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        try:
            cur.callproc(procedure, (order_id, user_id))
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                new_state = "APR" if procedure == "SP_COMPRA_APROBAR" else "ANU"
                cur.execute("UPDATE COMPRAS SET ESTADO_OC = %s WHERE id_Compra = %s", (new_state, order_id))
                cur.execute("UPDATE PROxOC SET ESTADO_PxOC = %s WHERE id_Compra = %s", (new_state, order_id))
            else:
                raise
        if procedure == "SP_COMPRA_APROBAR":
            cur.execute(
                """
                SELECT id_Recibo FROM RECEPCIONES
                WHERE id_Compra = %s
                ORDER BY rec_FechaHora DESC
                LIMIT 1
                """,
                (order_id,),
            )
            receipt = cur.fetchone()
            if receipt is None:
                receipt_id = f"R{uuid4().hex[:9].upper()}"
                cur.execute(
                    """
                    INSERT INTO RECEPCIONES
                        (id_Recibo, id_Compra, rec_Descripcion, rec_FechaHora,
                         rec_Num_Produc, ESTADO_REC)
                    VALUES (%s, %s, 'Recepción de compra', NOW(), 0, 'PEN')
                    """,
                    (receipt_id, order_id),
                )
            else:
                receipt_id = receipt[0].strip()
            cur.execute(
                """
                SELECT TRIM(id_Producto), pxo_Cantidad
                FROM PROxOC
                WHERE id_Compra = %s
                """,
                (order_id,),
            )
            order_items = cur.fetchall()
            for product_id, quantity in order_items:
                cur.execute(
                    """
                    INSERT INTO PROxREC
                        (id_Recibo, id_Producto, pxr_Cantidad,
                         pxr_Qty_Recibida, pxr_Motivo, ESTADO_PxREC)
                    VALUES (%s, %s, %s, 0, NULL, 'PEN')
                    """,
                    (receipt_id, product_id, quantity),
                )
            cur.execute(
                "UPDATE RECEPCIONES SET rec_Num_Produc = %s WHERE id_Recibo = %s",
                (len(order_items), receipt_id),
            )
        conn.commit()
        return {
            "id": order_id,
            "estado": "APR" if procedure == "SP_COMPRA_APROBAR" else "ANU",
        }
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/compras/{order_id}/aprobar")
def aprobar_compra(order_id: str):
    return cambiar_estado_compra(order_id, "SP_COMPRA_APROBAR")


@app.post("/api/compras/{order_id}/anular")
def anular_compra(order_id: str):
    return cambiar_estado_compra(order_id, "SP_COMPRA_ANULAR")


# ==========================================
# 2. MÓDULO PRODUCTOS / CATÁLOGO
# ==========================================

@app.get("/api/productos")
def listar_productos():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(P.id_Producto) AS id,
                TRIM(P.pro_Descripcion) AS name,
                TRIM(P.id_Producto) AS sku,
                CONCAT('786', LPAD(ASCII(SUBSTRING(P.id_Producto, 1, 1)), 6, '0')) AS barcode,
                COALESCE(TRIM(M.mar_Nombre), 'Sin Marca') AS brand,
                COALESCE(TRIM(C.cat_Nombre), 'Licores') AS category,
                750 AS ml,
                40 AS abv,
                P.pro_Valor_Compra AS cost,
                P.pro_Precio_Venta AS price,
                P.pro_Saldo_Final AS stock,
                P.pro_Saldo_Inicial AS minStock,
                TRIM(P.pro_UM_Compra) AS buyUnit,
                TRIM(P.pro_UM_Venta) AS sellUnit,
                12 AS purchaseFactor,
                'A1' AS shelf,
                IF(P.ESTADO_PROD = 'ACT', 'ACTIVE', 'INACTIVE') AS status
            FROM PRODUCTOS P
            LEFT JOIN MARCAS M ON P.id_Marca = M.id_Marca
            LEFT JOIN CATEGORIAS C ON P.id_Categoria = C.id_Categoria
            ORDER BY P.pro_Descripcion
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/productos")
def crear_producto(prod: ProductInput):
    conn, cur = None, None
    product_id = prod.id or f"PR-{uuid4().hex[:6].upper()}"
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        try:
            cur.callproc(
                "SP_PRODUCTO_CREAR",
                (
                    product_id,
                    prod.category_id,
                    prod.brand_id,
                    prod.name[:40],
                    prod.buy_unit[:3],
                    prod.sell_unit[:3],
                    prod.buy_cost,
                    prod.sell_price,
                    prod.initial_stock,
                    user_id,
                ),
            )
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                cur.execute(
                    """
                    INSERT INTO PRODUCTOS (
                        id_Producto, id_Categoria, id_Marca, pro_Descripcion,
                        pro_UM_Compra, pro_UM_Venta, pro_Valor_Compra,
                        pro_Precio_Venta, pro_Saldo_Inicial, pro_Qty_Ingresos,
                        pro_Qty_Egresos, pro_Qty_Ajustes, pro_Saldo_Final, ESTADO_PROD
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, 'ACT')
                    """,
                    (
                        product_id,
                        prod.category_id,
                        prod.brand_id,
                        prod.name[:40],
                        prod.buy_unit[:3],
                        prod.sell_unit[:3],
                        prod.buy_cost,
                        prod.sell_price,
                        prod.initial_stock,
                        prod.initial_stock,
                    ),
                )
            else:
                raise
        conn.commit()
        return {"id": product_id, "mensaje": f"Producto {prod.name} creado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/productos/{product_id}")
def actualizar_producto(product_id: str, prod: ProductInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE PRODUCTOS
            SET pro_Descripcion = %s,
                pro_Valor_Compra = %s,
                pro_Precio_Venta = %s
            WHERE id_Producto = %s
            """,
            (prod.name[:40], prod.buy_cost, prod.sell_price, product_id),
        )
        conn.commit()
        return {"id": product_id, "mensaje": "Producto actualizado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 3. MÓDULO CLIENTES
# ==========================================

@app.get("/api/clientes")
def listar_clientes():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(C.id_Cliente) AS id,
                TRIM(C.cli_RUC_CED) AS ciRuc,
                TRIM(C.cli_Nombre) AS name,
                TRIM(C.cli_Telefono) AS contact,
                TRIM(C.cli_Mail) AS email,
                COALESCE(TRIM(CI.ciu_Descripcion), 'Quito') AS city,
                TRIM(C.cli_Direccion) AS address,
                IF(LENGTH(TRIM(C.cli_RUC_CED)) = 13, 'JUR', 'NAT') AS type,
                C.cli_MontoMaxCredito AS creditLimit,
                0.00 AS creditUsed,
                C.cli_Descuento AS discountRate,
                IF(C.ESTADO_CLI = 'ACT', 'ACTIVE', 'INACTIVE') AS status
            FROM CLIENTES C
            LEFT JOIN CIUDADES CI ON C.id_Ciudad = CI.id_Ciudad
            ORDER BY C.cli_Nombre
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/clientes")
def crear_cliente(cli: CustomerInput):
    conn, cur = None, None
    customer_id = cli.id or f"CLI-{uuid4().hex[:5].upper()}"
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO CLIENTES 
            (id_Cliente, cli_Nombre, cli_RUC_CED, cli_Telefono, cli_Mail, id_Ciudad, cli_Celular, cli_Direccion, cli_MontoMaxCredito, cli_Descuento, ESTADO_CLI)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACT')
            """,
            (
                customer_id,
                cli.name[:40],
                cli.ci_ruc[:13],
                cli.phone[:10],
                cli.email[:60],
                cli.city_id[:3],
                cli.mobile[:10],
                cli.address[:60],
                cli.credit_limit,
                cli.discount,
            ),
        )
        conn.commit()
        return {"id": customer_id, "mensaje": f"Cliente {cli.name} registrado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/clientes/{customer_id}")
def actualizar_cliente(customer_id: str, cli: CustomerInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE CLIENTES
            SET cli_Nombre = %s,
                cli_RUC_CED = %s,
                cli_Telefono = %s,
                cli_Mail = %s,
                cli_Direccion = %s,
                cli_MontoMaxCredito = %s,
                cli_Descuento = %s
            WHERE id_Cliente = %s
            """,
            (
                cli.name[:40],
                cli.ci_ruc[:13],
                cli.phone[:10],
                cli.email[:60],
                cli.address[:60],
                cli.credit_limit,
                cli.discount,
                customer_id,
            ),
        )
        conn.commit()
        return {"id": customer_id, "mensaje": "Cliente actualizado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 4. MÓDULO PROVEEDORES
# ==========================================

@app.get("/api/proveedores")
def listar_proveedores():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(P.id_Proveedor) AS id,
                TRIM(P.prv_RUC_CED) AS ruc,
                TRIM(P.prv_Nombre) AS name,
                TRIM(P.prv_Telefono) AS contact,
                TRIM(P.prv_Celular) AS mobile,
                TRIM(P.prv_Mail) AS email,
                COALESCE(TRIM(CI.ciu_Descripcion), 'Quito') AS city,
                TRIM(P.id_Ciudad) AS cityId,
                TRIM(P.prv_Direccion) AS address,
                IF(P.ESTADO_PRV = 'ACT', 'ACTIVE', 'INACTIVE') AS status
            FROM PROVEEDORES P
            LEFT JOIN CIUDADES CI ON P.id_Ciudad = CI.id_Ciudad
            ORDER BY P.prv_Nombre
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/proveedores")
def crear_proveedor(prv: SupplierInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        if prv.id and prv.id.strip():
            supplier_id = prv.id.strip()[:10]
        else:
            import re
            cur.execute("SELECT id_Proveedor FROM PROVEEDORES")
            existing_rows = cur.fetchall()
            max_id = 0
            for row in existing_rows:
                id_val = str(row[0] if isinstance(row, (list, tuple)) else row.get("id_Proveedor", ""))
                m = re.search(r"(\d+)", id_val)
                if m:
                    num = int(m.group(1))
                    if num > max_id:
                        max_id = num
            supplier_id = f"prv_{max_id + 1:06d}"

        cur.execute(
            """
            INSERT INTO PROVEEDORES 
            (id_Proveedor, prv_Nombre, prv_RUC_CED, prv_Telefono, prv_Mail, id_Ciudad, prv_Celular, prv_Direccion, ESTADO_PRV)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACT')
            """,
            (
                supplier_id,
                prv.name[:40],
                prv.ruc[:13],
                prv.phone[:10],
                prv.email[:60],
                prv.city_id[:3],
                prv.mobile[:10],
                prv.address[:60],
            ),
        )
        conn.commit()
        return {"id": supplier_id, "mensaje": f"Proveedor {prv.name} registrado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/proveedores/{supplier_id}")
def actualizar_proveedor(supplier_id: str, prv: SupplierInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE PROVEEDORES
            SET prv_Nombre = %s,
                prv_RUC_CED = %s,
                prv_Telefono = %s,
                prv_Celular = %s,
                prv_Mail = %s,
                id_Ciudad = %s,
                prv_Direccion = %s
            WHERE id_Proveedor = %s
            """,
            (
                prv.name[:40],
                prv.ruc[:13],
                prv.phone[:10],
                prv.mobile[:10],
                prv.email[:60],
                prv.city_id[:3],
                prv.address[:60],
                supplier_id,
            ),
        )
        conn.commit()
        return {"id": supplier_id, "mensaje": "Proveedor actualizado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.patch("/api/proveedores/{supplier_id}/estado")
def cambiar_estado_proveedor(supplier_id: str, payload: dict):
    nuevo_estado = payload.get("estado", "INA")
    if nuevo_estado in ["ACTIVE", "ACT"]:
        db_estado = "ACT"
    else:
        db_estado = "INA"

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            "UPDATE PROVEEDORES SET ESTADO_PRV = %s WHERE id_Proveedor = %s",
            (db_estado, supplier_id),
        )
        conn.commit()
        return {
            "id": supplier_id,
            "estado": "ACTIVE" if db_estado == "ACT" else "INACTIVE",
            "mensaje": f"Estado del proveedor actualizado a {'Activo' if db_estado == 'ACT' else 'Inactivo'}.",
        }
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()



# ==========================================
# 5. MÓDULO VENTAS Y FACTURACIÓN
# ==========================================

@app.get("/api/ventas")
def listar_ventas():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(F.id_Factura) AS id,
                F.fac_Fecha AS date,
                TRIM(F.id_Cliente) AS customerId,
                TRIM(C.cli_Nombre) AS customerName,
                F.fac_Subtotal AS subtotal,
                0.00 AS discount,
                15.00 AS taxRate,
                F.fac_IVA AS tax,
                F.fac_Total AS total,
                'CASH' AS paymentMethod,
                1 AS installments,
                F.ESTADO_FAC AS status
            FROM FACTURAS F
            INNER JOIN CLIENTES C ON F.id_Cliente = C.id_Cliente
            ORDER BY F.fac_Fecha DESC, F.id_Factura DESC
            """
        )
        invoices = cur.fetchall()

        cur.execute(
            """
            SELECT 
                TRIM(D.id_Factura) AS facturaId,
                TRIM(D.id_Producto) AS productId,
                TRIM(P.pro_Descripcion) AS productName,
                D.pxf_Cantidad AS qty,
                D.pxf_Precio AS price,
                D.pxf_Subtotal AS subtotal
            FROM PROxFAC D
            INNER JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
            ORDER BY D.id_Factura
            """
        )
        items_by_invoice: dict[str, list[dict[str, object]]] = {}
        for row in cur.fetchall():
            fac_id = row.pop("facturaId")
            items_by_invoice.setdefault(fac_id, []).append(row)

        for inv in invoices:
            inv["items"] = items_by_invoice.get(inv["id"], [])
        return invoices
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ventas")
def registrar_venta(sale: SaleOrderInput):
    invoice_id = f"FAC{uuid4().hex[:10].upper()}"
    delivery_id = f"ENT{uuid4().hex[:10].upper()}"
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        user_id = get_user_id(cur)

        # 1. Obtener empleado por defecto si no existe
        cur.execute("SELECT id_Empleado FROM EMPLEADOS LIMIT 1")
        emp_row = cur.fetchone()
        employee_id = emp_row["id_Empleado"] if emp_row else "EMP-000001"

        # 2. Calcular subtotales
        subtotal = Decimal("0")
        sale_items = []
        for item in sale.items:
            line_subtotal = (Decimal(item.quantity) * item.unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
            subtotal += line_subtotal
            sale_items.append((item.product_id, item.quantity, item.unit_price, line_subtotal))

        tax = (subtotal * Decimal("0.15")).quantize(CENT, rounding=ROUND_HALF_UP)
        total = subtotal + tax

        # 3. Invocar SP_FACTURA_CREAR
        cur.callproc(
            "SP_FACTURA_CREAR",
            (
                invoice_id,
                sale.customer_id,
                employee_id,
                sale.description[:60],
                subtotal,
                tax,
                total,
                user_id,
            ),
        )

        # 4. Insertar líneas en PROxFAC
        # El trigger TRG_BEFORE_INSERT_PROxFAC verificará stock
        # El trigger TRG_AFTER_INSERT_PROxFAC descontará stock y recalculará cabecera
        for pid, qty, price, line_sub in sale_items:
            cur.execute(
                """
                INSERT INTO PROxFAC (id_Factura, id_Producto, pxf_Cantidad, pxf_Precio, pxf_Subtotal, ESTADO_PxFAC)
                VALUES (%s, %s, %s, %s, %s, 'ABI')
                """,
                (invoice_id, pid, qty, price, line_sub),
            )

        # 5. Registrar orden de entrega en ENTREGAS y PROxENT
        cur.execute(
            """
            INSERT INTO ENTREGAS (id_Entrega, id_Factura, ent_Descripcion, ent_FechaHora, ent_Num_Produc, ESTADO_ENT)
            VALUES (%s, %s, 'Entrega venta POS', NOW(), %s, 'PEN')
            """,
            (delivery_id, invoice_id, len(sale_items)),
        )
        for pid, qty, _, _ in sale_items:
            cur.execute(
                """
                INSERT INTO PROxENT (id_Entrega, id_Producto, pxe_Cantidad, pxe_Qty_Entregada, pxe_Motivo, ESTADO_PxENT)
                VALUES (%s, %s, %s, 0, NULL, 'PEN')
                """,
                (delivery_id, pid, qty),
            )

        conn.commit()
        return {
            "id": invoice_id,
            "deliveryId": delivery_id,
            "estado": "ABI",
            "total": str(total),
            "mensaje": f"Venta {invoice_id} registrada exitosamente.",
        }
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ventas/{invoice_id}/aprobar")
def aprobar_factura(invoice_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_FACTURA_APROBAR", (invoice_id, user_id))
        conn.commit()
        return {"id": invoice_id, "estado": "APR", "mensaje": "Factura aprobada."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ventas/{invoice_id}/anular")
def anular_factura(invoice_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_FACTURA_ANULAR", (invoice_id, user_id))
        conn.commit()
        return {"id": invoice_id, "estado": "ANU", "mensaje": "Factura anulada."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 6. MÓDULO BODEGA: RECEPCIONES Y ENTREGAS
# ==========================================

@app.get("/api/recepciones")
def listar_recepciones():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(R.id_Recibo) AS id,
                TRIM(R.id_Compra) AS poId,
                R.rec_FechaHora AS date,
                R.ESTADO_REC AS status,
                R.rec_Descripcion AS description
            FROM RECEPCIONES R
            ORDER BY R.rec_FechaHora DESC
            """
        )
        receipts = cur.fetchall()

        cur.execute(
            """
            SELECT 
                TRIM(D.id_Recibo) AS reciboId,
                TRIM(D.id_Producto) AS productId,
                TRIM(P.pro_Descripcion) AS productName,
                D.pxr_Cantidad AS expectedQty,
                D.pxr_Qty_Recibida AS receivedQty,
                (D.pxr_Qty_Recibida - D.pxr_Cantidad) AS diff,
                COALESCE(TRIM(D.pxr_Motivo), '') AS reason
            FROM PROxREC D
            INNER JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
            ORDER BY D.id_Recibo
            """
        )
        items_by_receipt: dict[str, list[dict[str, object]]] = {}
        for row in cur.fetchall():
            rec_id = row.pop("reciboId")
            items_by_receipt.setdefault(rec_id, []).append(row)

        for rec in receipts:
            rec["items"] = items_by_receipt.get(rec["id"], [])
        return receipts
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/recepciones/{receipt_id}/confirmar")
def confirmar_recepcion(receipt_id: str, payload: ReceptionConfirmInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        for item in payload.items:
            prod_id = str(item.get("productId", ""))
            received_qty = int(item.get("receivedQty", 0))
            reason = str(item.get("reason", ""))
            
            # Obtener cantidad previa recibida para no duplicar sumas de stock
            cur.execute(
                "SELECT pxr_Qty_Recibida FROM PROxREC WHERE id_Recibo = %s AND id_Producto = %s",
                (receipt_id, prod_id),
            )
            prev_row = cur.fetchone()
            prev_qty = prev_row[0] if prev_row else 0
            diff_to_add = received_qty - prev_qty

            cur.execute(
                """
                UPDATE PROxREC
                SET pxr_Qty_Recibida = %s,
                    pxr_Motivo = %s,
                    ESTADO_PxREC = 'APR'
                WHERE id_Recibo = %s AND id_Producto = %s
                """,
                (received_qty, reason[:60] if reason else None, receipt_id, prod_id),
            )
            if diff_to_add != 0:
                cur.execute(
                    """
                    UPDATE PRODUCTOS
                    SET pro_Qty_Ingresos = pro_Qty_Ingresos + %s,
                        pro_Saldo_Final = pro_Saldo_Final + %s
                    WHERE id_Producto = %s
                    """,
                    (diff_to_add, diff_to_add, prod_id),
                )

        cur.execute(
            "UPDATE RECEPCIONES SET ESTADO_REC = 'APR' WHERE id_Recibo = %s",
            (receipt_id,),
        )
        conn.commit()
        return {"id": receipt_id, "estado": "APR", "mensaje": "Ingreso a bodega confirmado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/entregas")
def listar_entregas():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(E.id_Entrega) AS id,
                TRIM(E.id_Factura) AS invoiceId,
                E.ent_FechaHora AS date,
                E.ESTADO_ENT AS status,
                E.ent_Descripcion AS description
            FROM ENTREGAS E
            ORDER BY E.ent_FechaHora DESC
            """
        )
        deliveries = cur.fetchall()

        cur.execute(
            """
            SELECT 
                TRIM(D.id_Entrega) AS entregaId,
                TRIM(D.id_Producto) AS productId,
                TRIM(P.pro_Descripcion) AS productName,
                D.pxe_Cantidad AS expectedQty,
                D.pxe_Qty_Entregada AS deliveredQty,
                (D.pxe_Qty_Entregada - D.pxe_Cantidad) AS diff,
                COALESCE(TRIM(D.pxe_Motivo), '') AS reason
            FROM PROxENT D
            INNER JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
            ORDER BY D.id_Entrega
            """
        )
        items_by_delivery: dict[str, list[dict[str, object]]] = {}
        for row in cur.fetchall():
            ent_id = row.pop("entregaId")
            items_by_delivery.setdefault(ent_id, []).append(row)

        for ent in deliveries:
            ent["items"] = items_by_delivery.get(ent["id"], [])
        return deliveries
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/entregas/{delivery_id}/confirmar")
def confirmar_entrega(delivery_id: str, payload: DeliveryConfirmInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        for item in payload.items:
            prod_id = str(item.get("productId", ""))
            delivered_qty = int(item.get("deliveredQty", 0))
            reason = str(item.get("reason", ""))
            cur.execute(
                """
                UPDATE PROxENT
                SET pxe_Qty_Entregada = %s,
                    pxe_Motivo = %s,
                    ESTADO_PxENT = 'APR'
                WHERE id_Entrega = %s AND id_Producto = %s
                """,
                (delivered_qty, reason[:60] if reason else None, delivery_id, prod_id),
            )
        cur.execute(
            "UPDATE ENTREGAS SET ESTADO_ENT = 'APR' WHERE id_Entrega = %s",
            (delivery_id,),
        )
        conn.commit()
        return {"id": delivery_id, "estado": "APR", "mensaje": "Despacho de venta confirmado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 7. MÓDULO BODEGA: AJUSTES FÍSICOS
# ==========================================

@app.get("/api/ajustes")
def listar_ajustes():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(A.id_Ajuste) AS id,
                A.aju_FechaHora AS date,
                TRIM(A.aju_Descripcion) AS reason,
                TRIM(A.id_Empleado) AS responsible,
                A.ESTADO_AJU AS status,
                TRIM(D.id_Producto) AS productId,
                TRIM(P.pro_Descripcion) AS productName,
                D.pxa_Cantidad AS qty,
                IF(D.pxa_Qty_Ajustada >= 0, 'IN', 'OUT') AS type
            FROM AJUSTES A
            LEFT JOIN PROxAJU D ON A.id_Ajuste = D.id_Ajuste
            LEFT JOIN PRODUCTOS P ON D.id_Producto = P.id_Producto
            ORDER BY A.aju_FechaHora DESC
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ajustes")
def crear_ajuste(aju: PhysicalAdjustmentInput):
    adjustment_id = f"AJU{uuid4().hex[:10].upper()}"
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)

        # Invocar SP_AJUSTE_CREAR
        cur.callproc(
            "SP_AJUSTE_CREAR",
            (
                adjustment_id,
                aju.employee_id,
                aju.reason[:30],
                1,
                user_id,
            ),
        )

        signed_qty = aju.quantity if aju.type == "IN" else -aju.quantity
        cur.execute(
            """
            INSERT INTO PROxAJU (id_Ajuste, id_Producto, pxa_Cantidad, pxa_Qty_Ajustada, ESTADO_PxAJU)
            VALUES (%s, %s, %s, %s, 'ABI')
            """,
            (adjustment_id, aju.product_id, aju.quantity, signed_qty),
        )
        conn.commit()
        return {"id": adjustment_id, "estado": "ABI", "mensaje": "Ajuste físico registrado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ajustes/{adjustment_id}/aprobar")
def aprobar_ajuste(adjustment_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_AJUSTE_APROBAR", (adjustment_id, user_id))

        # Al aprobar, impactar en saldo del producto
        cur.execute(
            "SELECT id_Producto, pxa_Qty_Ajustada FROM PROxAJU WHERE id_Ajuste = %s",
            (adjustment_id,),
        )
        for prod_id, delta in cur.fetchall():
            cur.execute(
                """
                UPDATE PRODUCTOS 
                SET pro_Qty_Ajustes = pro_Qty_Ajustes + %s,
                    pro_Saldo_Final = pro_Saldo_Final + %s
                WHERE id_Producto = %s
                """,
                (delta, delta, prod_id),
            )
        conn.commit()
        return {"id": adjustment_id, "estado": "APR", "mensaje": "Ajuste aprobado e impactado en inventario."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ajustes/{adjustment_id}/anular")
def anular_ajuste(adjustment_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_AJUSTE_ANULAR", (adjustment_id, user_id))
        conn.commit()
        return {"id": adjustment_id, "estado": "ANU", "mensaje": "Ajuste anulado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 8. MÓDULO TALENTO HUMANO / NÓMINA
# ==========================================

@app.get("/api/empleados")
def listar_empleados():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(E.id_Empleado) AS id,
                TRIM(E.emp_Cedula) AS ci,
                CONCAT(TRIM(E.emp_Nombre1), ' ', TRIM(E.emp_Apellido1)) AS name,
                COALESCE(TRIM(D.dep_Nombre), 'Administración') AS department,
                'Colaborador' AS role,
                E.emp_Sueldo AS salary,
                IF(E.ESTADO_EMP = 'ACT', 'ACTIVE', 'INACTIVE') AS status,
                0 AS familyDependents
            FROM EMPLEADOS E
            LEFT JOIN DEPARTAMENTOS D ON E.id_Departamento = D.id_Departamento
            ORDER BY E.emp_Apellido1
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/nomina")
def listar_nomina():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(P.id_Pago) AS id,
                P.pag_Fecha_Fin AS date,
                TRIM(D.id_Empleado) AS employeeId,
                D.pxe_Sueldo_Base AS baseSalary,
                D.pxe_Total_Ingresos AS bonus,
                D.pxe_Total_Egresos AS deductions,
                D.pxe_Neto_Pagar AS amount,
                P.ESTADO_PAG AS status
            FROM PAGOS P
            INNER JOIN PAGxEMP D ON P.id_Pago = D.id_Pago
            ORDER BY P.pag_Fecha_Fin DESC
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/nomina")
def crear_rol_pago(payroll: PayrollInput):
    pago_id = f"PAG{uuid4().hex[:7].upper()}"
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc(
            "SP_PAGO_CREAR",
            (
                pago_id,
                payroll.description[:40],
                payroll.start_date,
                payroll.end_date,
                user_id,
            ),
        )
        neto = payroll.base_salary + payroll.bonus - payroll.deductions
        cur.execute(
            """
            INSERT INTO PAGxEMP (id_Pago, id_Empleado, pxe_Sueldo_Base, pxe_Total_Ingresos, pxe_Total_Egresos, pxe_Neto_Pagar, ESTADO_PxE)
            VALUES (%s, %s, %s, %s, %s, %s, 'ABI')
            """,
            (
                pago_id,
                payroll.employee_id,
                payroll.base_salary,
                payroll.bonus,
                payroll.deductions,
                neto,
            ),
        )
        conn.commit()
        return {"id": pago_id, "estado": "ABI", "mensaje": "Rol de pago generado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/nomina/{pago_id}/aprobar")
def aprobar_nomina(pago_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_PAGO_APROBAR", (pago_id, user_id))
        conn.commit()
        return {"id": pago_id, "estado": "APR", "mensaje": "Rol de pago aprobado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/nomina/{pago_id}/anular")
def anular_nomina(pago_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_PAGO_ANULAR", (pago_id, user_id))
        conn.commit()
        return {"id": pago_id, "estado": "ANU", "mensaje": "Rol de pago anulado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 9. MÓDULO CONTABILIDAD
# ==========================================

@app.get("/api/contabilidad/cuentas")
def listar_cuentas():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(C.id_Cuenta) AS id,
                TRIM(C.id_Cuenta) AS code,
                TRIM(C.cue_Descripcion) AS name,
                CASE 
                    WHEN C.id_Cuenta LIKE '1%' THEN 'ASSET'
                    WHEN C.id_Cuenta LIKE '2%' THEN 'LIABILITY'
                    WHEN C.id_Cuenta LIKE '3%' THEN 'EQUITY'
                    WHEN C.id_Cuenta LIKE '4%' THEN 'REVENUE'
                    ELSE 'EXPENSE'
                END AS type,
                COALESCE(C.cue_DEBE00, 0) - COALESCE(C.cue_HABER00, 0) AS balance
            FROM CUENTAS C
            WHERE C.ESTADO_CUE = 'ACT' OR C.ESTADO_CUE IS NULL
            ORDER BY C.id_Cuenta
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/contabilidad/cuentas")
def crear_cuenta(acc: AccountInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("SELECT id_Tipo_Cta FROM tipo_cuenta WHERE id_Tipo_Cta = %s", (acc.type[:3],))
        if not cur.fetchone():
            cur.execute("INSERT IGNORE INTO tipo_cuenta (id_Tipo_Cta, tip_Descripcion) VALUES (%s, %s)", (acc.type[:3], acc.type[:10]))
        cur.execute(
            """
            INSERT INTO CUENTAS (id_Cuenta, cue_Descripcion, cue_Tipo, cue_DEBE00, cue_HABER00, ESTADO_CUE)
            VALUES (%s, %s, %s, 0, 0, 'ACT')
            ON DUPLICATE KEY UPDATE cue_Descripcion = VALUES(cue_Descripcion)
            """,
            (acc.id[:15], acc.name[:60], acc.type[:3]),
        )
        conn.commit()
        return {"id": acc.id, "mensaje": f"Cuenta {acc.id} creada exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/contabilidad/asientos")
def listar_asientos():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(A.id_Asiento) AS id,
                A.asi_FechaHora AS date,
                TRIM(A.asi_Descripcion) AS description,
                A.ESTADO_ASI AS status,
                'MANUAL' AS source
            FROM ASIENTOS A
            ORDER BY A.asi_FechaHora DESC
            """
        )
        entries = cur.fetchall()

        cur.execute(
            """
            SELECT 
                TRIM(D.id_Asiento) AS asientoId,
                TRIM(D.id_Cuenta) AS accountId,
                D.cxa_Debe AS debit,
                D.cxa_Haber AS credit
            FROM CTAxASI D
            ORDER BY D.id_Asiento
            """
        )
        lines_by_entry: dict[str, list[dict[str, object]]] = {}
        for row in cur.fetchall():
            asi_id = row.pop("asientoId")
            lines_by_entry.setdefault(asi_id, []).append(row)

        for ent in entries:
            ent["lines"] = lines_by_entry.get(ent["id"], [])
        return entries
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/contabilidad/asientos")
def crear_asiento(entry: JournalEntryInput):
    total_debe = sum((line.debit for line in entry.lines), Decimal("0"))
    total_haber = sum((line.credit for line in entry.lines), Decimal("0"))
    if total_debe != total_haber:
        raise HTTPException(status_code=422, detail="El asiento debe estar cuadrado (Debe == Haber).")

    asiento_id = f"ASI{uuid4().hex[:7].upper()}"
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc(
            "SP_ASIENTO_CREAR",
            (
                asiento_id,
                entry.description[:30],
                total_debe,
                total_haber,
                user_id,
            ),
        )
        for line in entry.lines:
            cur.execute(
                """
                INSERT INTO CTAxASI (id_Asiento, id_Cuenta, cxa_Debe, cxa_Haber, ESTADO_CXA)
                VALUES (%s, %s, %s, %s, 'ABI')
                """,
                (asiento_id, line.account_id, line.debit, line.credit),
            )
        conn.commit()
        return {"id": asiento_id, "estado": "ABI", "mensaje": "Asiento contable registrado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/contabilidad/asientos/{asiento_id}/aprobar")
def aprobar_asiento(asiento_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_ASIENTO_APROBAR", (asiento_id, user_id))
        conn.commit()
        return {"id": asiento_id, "estado": "CON", "mensaje": "Asiento contabilizado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/contabilidad/asientos/{asiento_id}/anular")
def anular_asiento(asiento_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        cur.callproc("SP_ASIENTO_ANULAR", (asiento_id, user_id))
        conn.commit()
        return {"id": asiento_id, "estado": "ANU", "mensaje": "Asiento anulado."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 10. AUDITORÍA Y BITÁCORA EN VIVO
# ==========================================

@app.get("/api/auditoria")
def listar_auditoria():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(id_Log) AS id,
                TRIM(id_Usuario) AS usuario,
                log_FechaHora AS fechaHora,
                TRIM(log_TablaAfectada) AS tabla,
                TRIM(log_Accion) AS accion,
                log_ValorAnterior AS valorAnterior,
                log_ValorNuevo AS valorNuevo
            FROM LOG_AUDITORIA
            ORDER BY log_FechaHora DESC
            LIMIT 50
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


if __name__ == "__main__":
    import sys
    import uvicorn

    api_dir = Path(__file__).resolve().parent
    workspace_dir = api_dir.parent

    for path_str in [str(api_dir), str(workspace_dir)]:
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    print("Iniciando servidor API en http://127.0.0.1:8000 ...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, app_dir=str(api_dir))

