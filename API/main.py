import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

import mysql.connector  # type: ignore
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    if cursor is None:
        raise HTTPException(
            status_code=500,
            detail="No se pudo identificar al usuario que realiza la operación.",
        )

    env_user = os.getenv("MARIADB_USER_ID", "").strip()
    if env_user:
        cursor.execute(
            "SELECT id_Usuario FROM USUARIOS WHERE id_Usuario = %s AND ESTADO_USR = 'ACT' LIMIT 1",
            (env_user,),
        )
        row = cursor.fetchone()
        if row:
            value = row[0] if isinstance(row, (tuple, list)) else row["id_Usuario"]
            return str(value).strip()

    cursor.execute(
        "SELECT id_Usuario FROM USUARIOS WHERE ESTADO_USR = 'ACT' ORDER BY id_Usuario ASC LIMIT 1"
    )
    row = cursor.fetchone()
    if row:
        value = row[0] if isinstance(row, (tuple, list)) else row["id_Usuario"]
        return str(value).strip()

    raise HTTPException(
        status_code=409,
        detail="Primero configura el usuario administrador inicial del sistema.",
    )


def raise_database_error(error: mysql.connector.Error) -> None:
    logger.exception("Error de base de datos.")
    if error.errno in {1045, 2002, 2003, 2005}:
        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar con el servidor de base de datos.",
        ) from error
    if error.errno == 1062:
        raise HTTPException(
            status_code=409,
            detail="El registro ya existe.",
        ) from error
    if error.errno == 1452:
        raise HTTPException(
            status_code=409,
            detail="No se puede completar la operación por dependencias relacionadas.",
        ) from error
    raise HTTPException(
        status_code=500,
        detail="Ocurrió un error al procesar la solicitud.",
    ) from error


# ==========================================
# MODELOS PYDANTIC Y RESTRICCIONES DE SEGURIDAD (ANTI-SQLI / INTEGRIDAD)
# ==========================================

RE_SQLI_DANGEROUS = re.compile(
    r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|EXEC|EXECUTE)\b|--|/\*|\*/|;|'|\"|<script)",
    re.IGNORECASE
)

RE_NAME = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$")
RE_ACCOUNT_CODE = re.compile(r"^\d+(\.\d+)*$")
RE_PHONE_CONV = re.compile(r"^0[2-7]\d{7}$")
RE_MOBILE = re.compile(r"^09\d{8}$")
RE_EMAIL = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
RE_BANK_NAME = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+$")
RE_CCO_NAME = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-_/]+$")
RE_ACCOUNT_NAME = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-_/()]+$")

def validar_cedula_ecuador(cedula: str) -> bool:
    cedula_limpia = str(cedula).strip()
    if not cedula_limpia.isdigit() or len(cedula_limpia) != 10:
        return False
    provincia = int(cedula_limpia[:2])
    if not (1 <= provincia <= 24 or provincia == 30):
        return False
    tercer_digito = int(cedula_limpia[2])
    if tercer_digito >= 6:
        return False
    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    suma = 0
    for i in range(9):
        val = int(cedula_limpia[i]) * coeficientes[i]
        suma += (val - 9) if val >= 10 else val
    verificador = (10 - (suma % 10)) % 10
    return verificador == int(cedula_limpia[9])


class PurchaseItemInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    product_id: str = Field(alias="idProducto", min_length=1, max_length=10)
    quantity: int = Field(alias="cantidad", gt=0, le=100000)
    unit_cost: Decimal = Field(alias="costoUnitario", gt=0, le=Decimal("99999.99"), max_digits=7, decimal_places=2)

    @field_validator("product_id")
    @classmethod
    def validar_producto_id(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio or RE_SQLI_DANGEROUS.search(limpio) or not re.match(r"^[A-Za-z0-9\-]+$", limpio):
            raise ValueError("Identificador de producto inválido.")
        return limpio[:10]


class PurchaseOrderInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    supplier_id: str = Field(alias="idProveedor", min_length=1, max_length=10)
    delivery_date: datetime | date | str | None = Field(default=None, alias="fechaEntrega")
    tax_rate: Decimal = Field(default=Decimal("0"), alias="tasaIVA", ge=0, le=100)
    items: list[PurchaseItemInput] = Field(min_length=1, max_length=100)

    @field_validator("supplier_id")
    @classmethod
    def validar_proveedor_id(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio or RE_SQLI_DANGEROUS.search(limpio) or not re.match(r"^[A-Za-z0-9_\-]+$", limpio):
            raise ValueError("Identificador de proveedor inválido.")
        return limpio[:10]

    @field_validator("delivery_date")
    @classmethod
    def validar_fecha_entrega(cls, v: datetime | date | str | None) -> datetime:
        if not v:
            raise ValueError("La fecha estimada de entrega (fechaEntrega) es obligatoria.")
        res = None
        if isinstance(v, datetime):
            res = v
        elif isinstance(v, date):
            res = datetime.combine(v, datetime.min.time())
        else:
            try:
                cleaned = str(v).strip()
                if len(cleaned) == 10:
                    res = datetime.strptime(cleaned, "%Y-%m-%d")
                else:
                    res = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            except Exception:
                raise ValueError("Formato de fecha de entrega inválido. Utilice el formato YYYY-MM-DD.")

        today = datetime.now().date()
        if res.date() < today:
            raise ValueError(f"La fecha de entrega ({res.date()}) no puede ser anterior a la fecha actual ({today}).")
        if res.date() > today + timedelta(days=730):
            raise ValueError("La fecha de entrega no puede superar 2 años hacia el futuro.")
        return res


class UnidadMedidaInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="id", min_length=1, max_length=3)
    nombre: str = Field(alias="nombre", min_length=2, max_length=20)
    factor: Decimal = Field(default=Decimal("1.00"), alias="factor", gt=0)

    @field_validator("id")
    @classmethod
    def validar_id_um(cls, v: str) -> str:
        limpio = str(v or "").strip().upper()
        if not limpio or len(limpio) > 3 or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El código de unidad de medida debe tener de 1 a 3 caracteres alfanuméricos.")
        if not re.match(r"^[A-Z0-9]+$", limpio):
            raise ValueError("El código de unidad de medida solo puede contener letras y números.")
        return limpio

    @field_validator("nombre")
    @classmethod
    def validar_nombre_um(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 2 or len(limpio) > 20:
            raise ValueError("La descripción de la unidad de medida debe tener entre 2 y 20 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("La descripción contiene caracteres no permitidos (anti-SQLi detectado).")
        return limpio

    @field_validator("factor")
    @classmethod
    def validar_factor_um(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("El factor de conversión debe ser un número positivo mayor a 0.")
        if v > Decimal("99999.99"):
            raise ValueError("El factor de conversión no puede exceder 99,999.99.")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class UnidadMedidaUpdateInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    nombre: str = Field(alias="nombre", min_length=2, max_length=20)
    factor: Decimal = Field(alias="factor", gt=0)

    @field_validator("nombre")
    @classmethod
    def validar_nombre_um(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 2 or len(limpio) > 20:
            raise ValueError("La descripción de la unidad de medida debe tener entre 2 y 20 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("La descripción contiene caracteres no permitidos (anti-SQLi detectado).")
        return limpio

    @field_validator("factor")
    @classmethod
    def validar_factor_um(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("El factor de conversión debe ser un número positivo mayor a 0.")
        if v > Decimal("99999.99"):
            raise ValueError("El factor de conversión no puede exceder 99,999.99.")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SaleItemInput(BaseModel):
    product_id: str = Field(alias="idProducto")
    quantity: int = Field(alias="cantidad", gt=0)
    unit_price: Decimal = Field(alias="precioUnitario", ge=0)


class SaleOrderInput(BaseModel):
    customer_id: str = Field(alias="idCliente")
    employee_id: str = Field(default="EMP-000001", alias="idEmpleado")
    description: str = Field(default="Venta en Punto de Venta", alias="descripcion")
    tax_rate: Decimal = Field(default=Decimal("15"), alias="tasaIVA")
    discount_amount: Decimal = Field(default=Decimal("0"), alias="descuento", ge=0)
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
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = None
    name: str = Field(alias="nombre", min_length=2, max_length=40)
    ruc: str = Field(alias="ruc", min_length=10, max_length=13)
    phone: str = Field(default="", alias="telefono")
    email: str = Field(default="", alias="email")
    city_id: str = Field(default="UIO", alias="idCiudad")
    mobile: str = Field(default="", alias="celular")
    address: str = Field(default="", alias="direccion")
    status: str = Field(default="ACT", alias="estado")

    @field_validator("id")
    @classmethod
    def validar_id(cls, v: str | None) -> str | None:
        if not v:
            return None
        limpio = str(v).strip()
        if not limpio:
            return None
        if len(limpio) > 10 or RE_SQLI_DANGEROUS.search(limpio) or not re.match(r"^[A-Za-z0-9_\-]+$", limpio):
            raise ValueError("El identificador de proveedor contiene caracteres no válidos.")
        return limpio[:10]

    @field_validator("name")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 2 or len(limpio) > 40:
            raise ValueError("La razón social / nombre debe tener entre 2 y 40 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El nombre del proveedor contiene caracteres o sentencias no permitidas (anti-SQLi detectado).")
        return limpio

    @field_validator("ruc")
    @classmethod
    def validar_ruc(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio.isdigit() or len(limpio) not in (10, 13):
            raise ValueError("El RUC / Cédula debe contener exactamente 10 o 13 dígitos numéricos sin letras ni símbolos.")
        if len(limpio) == 10 and not validar_cedula_ecuador(limpio):
            raise ValueError("El número de cédula ingresado no es válido según el algoritmo del Registro Civil del Ecuador.")
        if len(limpio) == 13 and not (limpio.endswith("001") or limpio.endswith("002") or limpio.endswith("003")):
            raise ValueError("El RUC de persona jurídica o natural en Ecuador debe terminar típicamente en 001.")
        return limpio

    @field_validator("phone")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio:
            return ""
        digits = re.sub(r"\D", "", limpio)
        if len(digits) > 10 or (len(digits) > 0 and len(digits) < 7):
            raise ValueError("El teléfono convencional debe tener entre 7 y 10 dígitos numéricos.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El teléfono contiene caracteres no permitidos.")
        return digits[:10]

    @field_validator("mobile")
    @classmethod
    def validar_celular(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio:
            return ""
        digits = re.sub(r"\D", "", limpio)
        if not RE_MOBILE.match(digits):
            raise ValueError("El celular debe tener 10 dígitos y empezar con 09 (ej: 0991234567).")
        return digits

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio:
            return ""
        if len(limpio) > 60 or not RE_EMAIL.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El correo electrónico es inválido o excede 60 caracteres (ej: contacto@proveedor.com).")
        return limpio

    @field_validator("city_id")
    @classmethod
    def validar_ciudad(cls, v: str) -> str:
        limpio = str(v or "").strip().upper()
        if not limpio or len(limpio) > 3 or RE_SQLI_DANGEROUS.search(limpio) or not re.match(r"^[A-Z0-9]+$", limpio):
            raise ValueError("El código de ciudad debe ser un identificador alfanumérico de hasta 3 caracteres (ej: UIO).")
        return limpio

    @field_validator("address")
    @classmethod
    def validar_direccion(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio:
            return ""
        if len(limpio) > 60 or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("La dirección contiene caracteres o sentencias no permitidas o excede 60 caracteres.")
        return limpio[:60]

    @field_validator("status")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        limpio = str(v or "ACT").strip().upper()
        if limpio in ("ACTIVE", "ACT"):
            return "ACT"
        if limpio in ("INACTIVE", "INA"):
            return "INA"
        raise ValueError("El estado del proveedor debe ser 'ACT' (Activo) o 'INA' (Inactivo).")


class ProductInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = None
    name: str = Field(alias="nombre", min_length=2, max_length=40)
    category_id: str = Field(default="CAT-000001", alias="idCategoria")
    brand_id: str = Field(default="MAR-000001", alias="idMarca")
    shelf_id: str | None = Field(default=None, alias="idPercha")
    buy_unit: str = Field(default="CAJ", alias="umCompra")
    sell_unit: str = Field(default="BOT", alias="umVenta")
    buy_cost: Decimal = Field(alias="costoCompra", ge=0, le=Decimal("99999.99"))
    sell_price: Decimal = Field(alias="precioVenta", ge=0, le=Decimal("99999.99"))
    initial_stock: int = Field(default=0, alias="stockInicial", ge=0, le=100000)

    @field_validator("id")
    @classmethod
    def validar_id_producto(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        limpio = str(v).strip().upper()
        if not re.match(r"^[A-Za-z0-9\-]{3,10}$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El código/ID del producto debe ser alfanumérico de 3 a 10 caracteres.")
        return limpio

    @field_validator("name")
    @classmethod
    def validar_nombre_producto(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 2 or len(limpio) > 40:
            raise ValueError("La descripción del producto debe tener entre 2 y 40 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("La descripción contiene caracteres no permitidos (anti-SQLi detectado).")
        return limpio

    @field_validator("category_id", "brand_id")
    @classmethod
    def validar_fk_producto(cls, v: str, info) -> str:
        limpio = str(v or "").strip()
        if not re.match(r"^[A-Za-z0-9\-]+$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError(f"Identificador de {info.field_name} inválido.")
        return limpio[:10]

    @field_validator("shelf_id")
    @classmethod
    def validar_percha_producto(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        limpio = str(v).strip()
        if not re.match(r"^[A-Za-z0-9\-]+$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de percha inválido.")
        return limpio[:10]

    @field_validator("buy_unit", "sell_unit")
    @classmethod
    def validar_unidad_producto(cls, v: str) -> str:
        limpio = str(v or "").strip().upper()
        if not limpio or len(limpio) > 3 or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El código de unidad de medida debe tener de 1 a 3 caracteres alfanuméricos.")
        return limpio

    @field_validator("buy_cost", "sell_price")
    @classmethod
    def validar_montos_producto(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00") or v > Decimal("99999.99"):
            raise ValueError("El costo y precio deben estar entre $0.00 y $99,999.99 (NUMERIC(7,2)).")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @model_validator(mode="after")
    def validar_costo_precio(self):
        if self.sell_price < self.buy_cost:
            raise ValueError("El precio de venta no puede ser inferior al costo de compra.")
        return self


class ProductStatusInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    status: str = Field(alias="estado")

    @field_validator("status")
    @classmethod
    def validar_estado_prod(cls, v: str) -> str:
        limpio = str(v or "").strip().upper()
        if limpio in ("ACT", "ACTIVE", "ACTIVO"):
            return "ACT"
        if limpio in ("INA", "INACTIVE", "INACTIVO"):
            return "INA"
        raise ValueError("El estado del producto debe ser 'ACT' (Activo) o 'INA' (Inactivo).")


class PhysicalAdjustmentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    employee_id: str = Field(default="EMP-000001", alias="idEmpleado")
    product_id: str = Field(alias="idProducto")
    type: str = Field(alias="tipo")  # 'IN' o 'OUT'
    quantity: int = Field(alias="cantidad", gt=0, le=100000)
    reason: str = Field(alias="motivo", min_length=3, max_length=100)

    @field_validator("employee_id")
    @classmethod
    def validar_empleado_ajuste(cls, v: str) -> str:
        limpio = str(v or "EMP-000001").strip()
        if not re.match(r"^[A-Za-z0-9\-]+$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de empleado no válido.")
        return limpio[:10]

    @field_validator("product_id")
    @classmethod
    def validar_producto_ajuste(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not re.match(r"^[A-Za-z0-9\-]+$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de producto no válido.")
        return limpio[:10]

    @field_validator("type")
    @classmethod
    def validar_tipo_ajuste(cls, v: str) -> str:
        limpio = str(v or "").strip().upper()
        if limpio in ("IN", "ENTRADA", "INGRESO"):
            return "IN"
        if limpio in ("OUT", "SALIDA", "EGRESO"):
            return "OUT"
        raise ValueError("El tipo de ajuste debe ser 'IN' (Ingreso) o 'OUT' (Egreso).")

    @field_validator("reason")
    @classmethod
    def validar_motivo_ajuste(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 3 or len(limpio) > 100:
            raise ValueError("El motivo del ajuste debe tener entre 3 y 100 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El motivo del ajuste contiene caracteres no permitidos (anti-SQLi detectado).")
        return limpio


class JournalEntryLineInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    account_id: str = Field(alias="idCuenta")
    debit: Decimal = Field(default=Decimal("0"), alias="debe")
    credit: Decimal = Field(default=Decimal("0"), alias="haber")

    @field_validator("account_id")
    @classmethod
    def validar_cuenta_linea(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not RE_ACCOUNT_CODE.match(limpio):
            raise ValueError(f"El identificador de cuenta '{limpio}' no tiene un formato numérico válido.")
        return limpio

    @field_validator("debit", "credit")
    @classmethod
    def validar_monto_linea(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Los valores del Debe y Haber no pueden ser negativos.")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class JournalEntryInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    description: str = Field(alias="descripcion", min_length=5, max_length=30)
    entry_date: date | datetime | str | None = Field(default=None, alias="fecha")
    lines: list[JournalEntryLineInput] = Field(min_length=2, default_factory=list)

    def __init__(self, **data):
        if "lineas" in data and "lines" not in data:
            data["lines"] = data["lineas"]
        super().__init__(**data)

    @field_validator("description")
    @classmethod
    def validar_asiento_desc(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 5 or len(limpio) > 30:
            raise ValueError("El concepto del asiento contable debe tener entre 5 y 30 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El concepto contiene caracteres o comandos no permitidos (protección SQL Injection).")
        return limpio

    @field_validator("entry_date")
    @classmethod
    def validar_asiento_fecha(cls, v: date | datetime | str | None) -> date | datetime | str | None:
        if v is None:
            return None
        d: date
        if isinstance(v, datetime):
            d = v.date()
        elif isinstance(v, date):
            d = v
        else:
            try:
                d = datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
            except Exception:
                raise ValueError("Formato de fecha inválido. Utilice el formato YYYY-MM-DD.")
        if d < date(2000, 1, 1):
            raise ValueError("La fecha del asiento contable no puede ser anterior al año 2000.")
        if d > date.today() + timedelta(days=365):
            raise ValueError("La fecha del asiento contable no puede superar un año hacia el futuro.")
        return v


class ReceptionItemConfirm(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    product_id: str = Field(alias="productId", min_length=1, max_length=10)
    received_qty: int = Field(alias="receivedQty", ge=0, le=100000)
    reason: str = Field(default="", alias="reason", max_length=100)

    @field_validator("product_id")
    @classmethod
    def validar_prod_recep(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not re.match(r"^[A-Za-z0-9\-]+$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de producto inválido.")
        return limpio[:10]

    @field_validator("reason")
    @classmethod
    def validar_motivo_recep(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if limpio and RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El motivo contiene caracteres o sentencias no permitidas (anti-SQLi detectado).")
        return limpio[:100]


class ReceptionConfirmInput(BaseModel):
    items: list[ReceptionItemConfirm] = Field(min_length=1)


class DeliveryItemConfirm(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    product_id: str = Field(alias="productId", min_length=1, max_length=10)
    delivered_qty: int = Field(alias="deliveredQty", ge=0, le=100000)
    reason: str = Field(default="", alias="reason", max_length=100)

    @field_validator("product_id")
    @classmethod
    def validar_prod_deliv(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not re.match(r"^[A-Za-z0-9\-]+$", limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de producto inválido.")
        return limpio[:10]

    @field_validator("reason")
    @classmethod
    def validar_motivo_deliv(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if limpio and RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El motivo contiene caracteres o sentencias no permitidas (anti-SQLi detectado).")
        return limpio[:100]


class DeliveryConfirmInput(BaseModel):
    items: list[DeliveryItemConfirm] = Field(min_length=1)


class EmployeeInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = None
    ci: str = Field(alias="ci")
    first_name: str = Field(alias="nombre1")
    second_name: str | None = Field(default=None, alias="nombre2")
    last_name1: str = Field(alias="apellido1")
    last_name2: str | None = Field(default=None, alias="apellido2")
    gender: str = Field(default="M", alias="sexo")
    birth_date: date = Field(default=date(1995, 1, 1), alias="fechaNacimiento")
    salary: Decimal = Field(alias="sueldo")
    department_id: str = Field(default="DEP-TEST", alias="idDepartamento")
    cargo_id: str | None = Field(default=None, alias="idCargo")
    phone: str | None = Field(default=None, alias="telefono")
    mobile: str | None = Field(default=None, alias="celular")
    address: str | None = Field(default=None, alias="direccion")
    email: str | None = Field(default=None, alias="email")

    @field_validator("ci")
    @classmethod
    def validar_ci(cls, v: str) -> str:
        ci_clean = re.sub(r"\D", "", str(v or ""))
        if not validar_cedula_ecuador(ci_clean):
            raise ValueError("La cédula ingresada no es válida según el algoritmo de verificación de Ecuador (10 dígitos).")
        return ci_clean

    @field_validator("first_name", "last_name1")
    @classmethod
    def validar_nombre_requerido(cls, v: str, info) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 2 or len(limpio) > 30:
            raise ValueError(f"El campo '{info.field_name}' debe tener entre 2 y 30 caracteres.")
        if not RE_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError(f"El campo '{info.field_name}' solo puede contener letras y espacios, sin números ni sentencias SQL.")
        return limpio

    @field_validator("second_name", "last_name2")
    @classmethod
    def validar_nombre_opcional(cls, v: str | None, info) -> str | None:
        if not v or not str(v).strip():
            return None
        limpio = str(v).strip()
        if len(limpio) > 30:
            raise ValueError(f"El campo '{info.field_name}' no puede exceder 30 caracteres.")
        if not RE_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError(f"El campo '{info.field_name}' solo puede contener letras y espacios.")
        return limpio

    @field_validator("gender")
    @classmethod
    def validar_genero(cls, v: str) -> str:
        g = str(v or "M").strip().upper()
        if g not in {"M", "F"}:
            raise ValueError("El género debe ser 'M' (Masculino) o 'F' (Femenino).")
        return g

    @field_validator("birth_date")
    @classmethod
    def validar_fecha_nacimiento_emp(cls, v: date) -> date:
        hoy = date.today()
        if v > hoy:
            raise ValueError("La fecha de nacimiento no puede ser en el futuro.")
        edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
        if edad < 18:
            raise ValueError(f"El empleado debe ser mayor de edad (al menos 18 años). Edad calculada: {edad} años.")
        if edad > 90:
            raise ValueError("La fecha de nacimiento del colaborador no es válida (edad supera 90 años).")
        return v

    @field_validator("salary")
    @classmethod
    def validar_sueldo(cls, v: Decimal) -> Decimal:
        if v < Decimal("460.00"):
            raise ValueError("El sueldo no puede ser inferior al Salario Básico Unificado vigente ($460.00 USD).")
        if v > Decimal("50000.00"):
            raise ValueError("El sueldo especificado supera el límite corporativo permitido ($50,000.00 USD).")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @field_validator("phone")
    @classmethod
    def validar_telefono(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        clean = re.sub(r"\D", "", str(v).strip())
        if not (clean.startswith("0") and len(clean) == 9) and len(clean) != 7:
            raise ValueError("El teléfono convencional debe tener 7 dígitos o 9 dígitos iniciando con código de provincia (ej. 022345678).")
        return clean

    @field_validator("mobile")
    @classmethod
    def validar_celular(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        clean = re.sub(r"\D", "", str(v).strip())
        if not RE_MOBILE.match(clean):
            raise ValueError("El teléfono celular debe tener 10 dígitos y comenzar con 09 (ej. 0991234567).")
        return clean

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        clean = str(v).strip().lower()
        if not RE_EMAIL.match(clean) or RE_SQLI_DANGEROUS.search(clean) or len(clean) > 60:
            raise ValueError("El formato de correo electrónico es inválido (ej. usuario@dominio.com).")
        return clean

    @field_validator("address")
    @classmethod
    def validar_direccion(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        clean = str(v).strip()
        if RE_SQLI_DANGEROUS.search(clean):
            raise ValueError("La dirección contiene caracteres o sentencias no permitidas (protección SQL Injection).")
        return clean[:60]


class DependentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id_carga: str | None = None
    cedula: str = Field(alias="ci")
    nombre1: str = Field(alias="nombre1")
    nombre2: str | None = Field(default=None, alias="nombre2")
    apellido1: str = Field(alias="apellido1")
    apellido2: str | None = Field(default=None, alias="apellido2")
    gender: str = Field(default="M", alias="sexo")
    birth_date: date = Field(alias="fechaNacimiento")
    relationship: str = Field(default="Hijo/a", alias="parentesco")
    marital_status: str = Field(default="Soltero/a", alias="estadoCivil")
    dependency_type: str = Field(default="Total", alias="dependencia")

    @field_validator("cedula")
    @classmethod
    def validar_ci_carga(cls, v: str) -> str:
        ci_clean = re.sub(r"\D", "", str(v or ""))
        if not validar_cedula_ecuador(ci_clean):
            raise ValueError("La cédula de la carga familiar no es válida según el algoritmo de Ecuador (10 dígitos).")
        return ci_clean

    @field_validator("nombre1", "apellido1")
    @classmethod
    def validar_nombre_carga_req(cls, v: str, info) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 2 or len(limpio) > 30:
            raise ValueError(f"El campo '{info.field_name}' debe tener entre 2 y 30 caracteres.")
        if not RE_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError(f"El campo '{info.field_name}' solo puede contener letras y espacios.")
        return limpio

    @field_validator("nombre2", "apellido2")
    @classmethod
    def validar_nombre_carga_opc(cls, v: str | None, info) -> str | None:
        if not v or not str(v).strip():
            return None
        limpio = str(v).strip()
        if len(limpio) > 30:
            raise ValueError(f"El campo '{info.field_name}' no puede exceder 30 caracteres.")
        if not RE_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError(f"El campo '{info.field_name}' solo puede contener letras y espacios.")
        return limpio

    @field_validator("gender")
    @classmethod
    def validar_genero_carga(cls, v: str) -> str:
        g = str(v or "M").strip().upper()
        if g not in {"M", "F"}:
            raise ValueError("El género debe ser 'M' (Masculino) o 'F' (Femenino).")
        return g

    @field_validator("birth_date")
    @classmethod
    def validar_fecha_nacimiento_carga(cls, v: date) -> date:
        hoy = date.today()
        if v > hoy:
            raise ValueError("La fecha de nacimiento de la carga familiar no puede ser en el futuro.")
        edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
        if edad > 110:
            raise ValueError("La fecha de nacimiento de la carga familiar supera el límite de edad permitido (110 años).")
        return v

    @field_validator("relationship")
    @classmethod
    def validar_parentesco(cls, v: str) -> str:
        validos = {"Hijo/a", "Cónyuge", "Conviviente", "Padre/Madre"}
        if v not in validos:
            raise ValueError(f"Parentesco no válido. Debe ser uno de: {', '.join(sorted(validos))}")
        return v

    @field_validator("marital_status")
    @classmethod
    def validar_estado_civil(cls, v: str) -> str:
        validos = {"Soltero/a", "Casado/a", "Divorciado/a", "Viudo/a", "Unión de Hecho"}
        if v not in validos:
            raise ValueError(f"Estado civil no válido. Debe ser uno de: {', '.join(sorted(validos))}")
        return v

    @field_validator("dependency_type")
    @classmethod
    def validar_dependencia(cls, v: str) -> str:
        validos = {"Total", "Parcial"}
        if v not in validos:
            raise ValueError(f"Tipo de dependencia no válido. Debe ser uno de: {', '.join(sorted(validos))}")
        return v


class CargoAssignInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    cargo_id: str = Field(alias="idCargo")
    start_date: date = Field(alias="fechaInicio")
    end_date: date | None = Field(default=None, alias="fechaFin")

    @field_validator("cargo_id")
    @classmethod
    def validar_cargo_id(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El identificador del cargo no es válido.")
        return limpio[:10]

    @model_validator(mode="after")
    def validar_fechas_cargo(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("La fecha de fin del cargo no puede ser anterior a la fecha de inicio.")
        return self


class PayrollBonusLineInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    bonus_id: str = Field(alias="idBonificacion")
    line_date: date | None = Field(default=None, alias="fecha")
    amount: Decimal = Field(alias="valor", ge=0)

    @field_validator("bonus_id")
    @classmethod
    def validar_bonus_id(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de bonificación inválido.")
        return limpio[:10]

    @field_validator("amount")
    @classmethod
    def validar_monto_bono(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("El valor de la bonificación debe ser un monto positivo mayor a $0.00.")
        if v > Decimal("50000.00"):
            raise ValueError("El valor de la bonificación excede el límite permitido ($50,000.00).")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PayrollDeductionLineInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    deduction_id: str = Field(alias="idDescuento")
    line_date: date | None = Field(default=None, alias="fecha")
    amount: Decimal = Field(alias="valor", ge=0)

    @field_validator("deduction_id")
    @classmethod
    def validar_deduction_id(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("Identificador de descuento inválido.")
        return limpio[:10]

    @field_validator("amount")
    @classmethod
    def validar_monto_descuento(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("El valor del descuento debe ser un monto positivo mayor a $0.00.")
        if v > Decimal("50000.00"):
            raise ValueError("El valor del descuento excede el límite permitido ($50,000.00).")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PayrollInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    description: str = Field(alias="descripcion", min_length=5, max_length=40)
    start_date: date = Field(alias="fechaInicio")
    end_date: date = Field(alias="fechaFin")
    employee_id: str = Field(alias="idEmpleado")
    base_salary: Decimal = Field(alias="sueldoBase")
    bonus: Decimal = Field(default=Decimal("0"), alias="bonificaciones")
    deductions: Decimal = Field(default=Decimal("0"), alias="descuentos")
    bonus_lines: list[PayrollBonusLineInput] = Field(default_factory=list, alias="lineasBonos")
    deduction_lines: list[PayrollDeductionLineInput] = Field(default_factory=list, alias="lineasDescuentos")

    @field_validator("description")
    @classmethod
    def validar_descripcion_rol(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 5 or len(limpio) > 40:
            raise ValueError("La descripción del rol debe tener entre 5 y 40 caracteres.")
        if RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("La descripción contiene caracteres no permitidos (protección SQL Injection).")
        return limpio

    @field_validator("base_salary")
    @classmethod
    def validar_sueldo_rol(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("El sueldo base no puede ser negativo.")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @model_validator(mode="after")
    def validar_fechas_rol(self):
        if self.end_date < self.start_date:
            raise ValueError("La fecha de fin del rol de pago no puede ser anterior a la fecha de inicio.")
        return self


class PayrollCatalogInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(alias="nombre", min_length=3, max_length=60)
    amount: Decimal = Field(alias="valor", ge=0, le=50000)
    status: str = Field(default="ACT", alias="estado")

    @field_validator("name")
    @classmethod
    def validar_nombre_catalogo_nomina(cls, value: str) -> str:
        clean_value = str(value or "").strip()
        if len(clean_value) < 3 or len(clean_value) > 60:
            raise ValueError("El nombre debe tener entre 3 y 60 caracteres.")
        if RE_SQLI_DANGEROUS.search(clean_value):
            raise ValueError("El nombre contiene caracteres no permitidos.")
        return clean_value

    @field_validator("amount")
    @classmethod
    def validar_valor_catalogo_nomina(cls, value: Decimal) -> Decimal:
        return value.quantize(CENT, rounding=ROUND_HALF_UP)

    @field_validator("status")
    @classmethod
    def validar_estado_catalogo_nomina(cls, value: str) -> str:
        clean_value = str(value or "ACT").strip().upper()
        if clean_value not in {"ACT", "INA"}:
            raise ValueError("El estado debe ser 'ACT' (Activo) o 'INA' (Inactivo).")
        return clean_value


class AccountInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="idCuenta", min_length=1, max_length=15)
    name: str = Field(alias="nombre", min_length=3, max_length=60)
    type: str = Field(default="DET", alias="tipo")  # 'MAY' or 'DET'

    @field_validator("id")
    @classmethod
    def validar_cuenta_id(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not RE_ACCOUNT_CODE.match(limpio):
            raise ValueError("El código de cuenta debe tener un formato numérico con puntos (ej. '1', '1.1', '1.1.01').")
        if len(limpio) > 15:
            raise ValueError("El código de cuenta no puede exceder 15 caracteres.")
        return limpio

    @field_validator("name")
    @classmethod
    def validar_cuenta_nombre(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 3 or len(limpio) > 60:
            raise ValueError("El nombre de la cuenta debe tener entre 3 y 60 caracteres.")
        if not RE_ACCOUNT_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El nombre de la cuenta contiene caracteres especiales no válidos o código SQL.")
        return limpio

    @field_validator("type")
    @classmethod
    def validar_cuenta_tipo(cls, v: str) -> str:
        limpio = str(v or "").strip().upper()
        if limpio not in {"MAY", "DET"}:
            raise ValueError("El tipo de cuenta debe ser estrictamente 'MAY' (Mayor) o 'DET' (Detalle).")
        return limpio


class BancoInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = Field(default=None, alias="idBanco")
    name: str = Field(alias="nombre", min_length=3, max_length=50)
    status: str = Field(default="ACT", alias="estado")

    @field_validator("id")
    @classmethod
    def validar_banco_id(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        limpio = str(v).strip()
        if RE_SQLI_DANGEROUS.search(limpio) or len(limpio) > 10:
            raise ValueError("Código de banco inválido.")
        return limpio

    @field_validator("name")
    @classmethod
    def validar_banco_nombre(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 3 or len(limpio) > 50:
            raise ValueError("El nombre de la entidad bancaria debe tener entre 3 y 50 caracteres.")
        if not RE_BANK_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El nombre del banco contiene caracteres no permitidos o sentencias SQL.")
        return limpio

    @field_validator("status")
    @classmethod
    def validar_banco_estado(cls, v: str) -> str:
        limpio = str(v or "ACT").strip().upper()
        if limpio not in {"ACT", "INA"}:
            raise ValueError("El estado del banco debe ser 'ACT' (Activo) o 'INA' (Inactivo).")
        return limpio


class CentroCostoInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = Field(default=None, alias="idCentroCosto")
    department_id: str = Field(alias="idDepartamento")
    name: str = Field(alias="nombre", min_length=3, max_length=50)
    monthly_budget: Decimal = Field(default=Decimal("0.00"), alias="presupuestoMensual", ge=0)
    status: str = Field(default="ACT", alias="estado")

    @field_validator("id")
    @classmethod
    def validar_cco_id(cls, v: str | None) -> str | None:
        if not v or not str(v).strip():
            return None
        limpio = str(v).strip()
        if RE_SQLI_DANGEROUS.search(limpio) or len(limpio) > 10:
            raise ValueError("Código de centro de costo inválido.")
        return limpio

    @field_validator("department_id")
    @classmethod
    def validar_cco_dep(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if not limpio or RE_SQLI_DANGEROUS.search(limpio) or len(limpio) > 10:
            raise ValueError("Departamento asociado inválido.")
        return limpio

    @field_validator("name")
    @classmethod
    def validar_cco_nombre(cls, v: str) -> str:
        limpio = str(v or "").strip()
        if len(limpio) < 3 or len(limpio) > 50:
            raise ValueError("El nombre del centro de costo debe tener entre 3 y 50 caracteres.")
        if not RE_CCO_NAME.match(limpio) or RE_SQLI_DANGEROUS.search(limpio):
            raise ValueError("El nombre del centro de costo contiene caracteres no permitidos o código SQL.")
        return limpio

    @field_validator("monthly_budget")
    @classmethod
    def validar_presupuesto(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("El presupuesto mensual no puede ser negativo.")
        if v > Decimal("1000000000.00"):
            raise ValueError("El presupuesto mensual excede el límite permitido.")
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @field_validator("status")
    @classmethod
    def validar_cco_estado(cls, v: str) -> str:
        limpio = str(v or "ACT").strip().upper()
        if limpio not in {"ACT", "INA"}:
            raise ValueError("El estado del centro de costo debe ser 'ACT' o 'INA'.")
        return limpio


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
        if not unidades:
            default_units = [
                ('BOT', 'Botella', Decimal('1.00')),
                ('CAJ', 'Caja x12', Decimal('12.00')),
                ('SIX', 'Six-pack x6', Decimal('6.00')),
                ('LIT', 'Litro', Decimal('1.00')),
                ('UND', 'Unidad', Decimal('1.00')),
            ]
            for uid, desc, factor in default_units:
                cur.execute(
                    "INSERT IGNORE INTO UNIDADES_MEDIDAS (id_Unidad_Medida, um_Descripcion, um_FactorConversion) VALUES (%s, %s, %s)",
                    (uid, desc, factor)
                )
            conn.commit()
            cur.execute("SELECT TRIM(id_Unidad_Medida) AS id, TRIM(um_Descripcion) AS nombre, um_FactorConversion AS factor FROM UNIDADES_MEDIDAS ORDER BY um_Descripcion")
            unidades = cur.fetchall()

        for u in unidades:
            if u.get("factor") is not None:
                u["factor"] = float(u["factor"])

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
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT TRIM(id_Unidad_Medida) AS id, TRIM(um_Descripcion) AS nombre, um_FactorConversion AS factor FROM UNIDADES_MEDIDAS ORDER BY um_Descripcion")
        rows = cur.fetchall()
        if not rows:
            default_units = [
                ('BOT', 'Botella', Decimal('1.00')),
                ('CAJ', 'Caja x12', Decimal('12.00')),
                ('SIX', 'Six-pack x6', Decimal('6.00')),
                ('LIT', 'Litro', Decimal('1.00')),
                ('UND', 'Unidad', Decimal('1.00')),
            ]
            for uid, desc, factor in default_units:
                cur.execute(
                    "INSERT IGNORE INTO UNIDADES_MEDIDAS (id_Unidad_Medida, um_Descripcion, um_FactorConversion) VALUES (%s, %s, %s)",
                    (uid, desc, factor)
                )
            conn.commit()
            cur.execute("SELECT TRIM(id_Unidad_Medida) AS id, TRIM(um_Descripcion) AS nombre, um_FactorConversion AS factor FROM UNIDADES_MEDIDAS ORDER BY um_Descripcion")
            rows = cur.fetchall()
        for r in rows:
            if r.get("factor") is not None:
                r["factor"] = float(r["factor"])
        return rows
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/unidades-medida")
def crear_unidad_medida(data: UnidadMedidaInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (data.id,))
        if cur.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe una unidad de medida con el código '{data.id}'.",
            )
        cur.execute(
            """
            INSERT INTO UNIDADES_MEDIDAS (id_Unidad_Medida, um_Descripcion, um_FactorConversion)
            VALUES (%s, %s, %s)
            """,
            (data.id, data.nombre, data.factor),
        )
        conn.commit()
        return {
            "mensaje": f"Unidad de medida '{data.id}' registrada exitosamente.",
            "id": data.id,
        }
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/unidades-medida/{id_um}")
def actualizar_unidad_medida(id_um: str, data: UnidadMedidaUpdateInput):
    id_clean = id_um.strip().upper()[:3]
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (id_clean,))
        if not cur.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró la unidad de medida con código '{id_clean}'.",
            )
        cur.execute(
            """
            UPDATE UNIDADES_MEDIDAS
            SET um_Descripcion = %s, um_FactorConversion = %s
            WHERE id_Unidad_Medida = %s
            """,
            (data.nombre, data.factor, id_clean),
        )
        conn.commit()
        return {"mensaje": f"Unidad de medida '{id_clean}' actualizada exitosamente."}
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.delete("/api/unidades-medida/{id_um}")
def eliminar_unidad_medida(id_um: str):
    id_clean = id_um.strip().upper()[:3]
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (id_clean,))
        if not cur.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró la unidad de medida con código '{id_clean}'.",
            )
        cur.execute(
            """
            SELECT COUNT(*) FROM PRODUCTOS
            WHERE pro_UM_Compra = %s OR pro_UM_Venta = %s
            """,
            (id_clean, id_clean),
        )
        count_prod = cur.fetchone()[0]
        if count_prod > 0:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede eliminar la unidad de medida '{id_clean}' porque está asignada a {count_prod} producto(s) en el catálogo.",
            )
        cur.execute("DELETE FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (id_clean,))
        conn.commit()
        return {"mensaje": f"Unidad de medida '{id_clean}' eliminada exitosamente."}
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


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

    order_id = None
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)

        # Generar ID correlativo estándar: COM-000001 (CHAR(10))
        cur.execute("SELECT id_Compra FROM COMPRAS")
        existing_orders = cur.fetchall()
        max_order_num = 0
        for r in existing_orders:
            val = str(r[0] if isinstance(r, (list, tuple)) else r.get("id_Compra", ""))
            m = re.match(r"^(?:COM-|OC-?)(\d+)$", val, re.IGNORECASE)
            if m:
                num = int(m.group(1))
                if num > max_order_num:
                    max_order_num = num
        order_id = f"COM-{max_order_num + 1:06d}"

        cur.execute(
            "SELECT 1 FROM PROVEEDORES WHERE id_Proveedor = %s AND ESTADO_PRV = 'ACT'",
            (purchase.supplier_id,),
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=422, detail="El proveedor seleccionado no existe o no se encuentra activo."
            )
        product_ids = [item.product_id for item in purchase.items]
        placeholders = ", ".join(["%s"] * len(product_ids))
        cur.execute(
            f"SELECT TRIM(id_Producto) FROM PRODUCTOS WHERE ESTADO_PROD = 'ACT' AND id_Producto IN ({placeholders})",
            tuple(product_ids),
        )
        active_product_ids = {row[0] for row in cur.fetchall()}
        missing_ids = set(product_ids) - active_product_ids
        if missing_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Los siguientes productos no existen o no están activos: {', '.join(missing_ids)}.",
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
            try:
                cur.callproc(
                    "SP_COMPRA_AGREGAR_PRODUCTO",
                    (
                        order_id,
                        item.product_id,
                        item.quantity,
                        item.unit_cost,
                        user_id,
                    )
                )
            except mysql.connector.Error as add_err:
                if add_err.errno in {1305, 1452}:
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
                else:
                    raise
        conn.commit()
        return {
            "id": order_id,
            "estado": "ABI",
            "subtotal": str(subtotal),
            "iva": str(tax),
            "total": str(total),
            "mensaje": f"Orden {order_id} creada exitosamente.",
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
    clean_id = str(order_id or "").strip()
    if not clean_id or len(clean_id) > 10 or RE_SQLI_DANGEROUS.search(clean_id) or not re.match(r"^[A-Za-z0-9\-]+$", clean_id):
        raise HTTPException(status_code=422, detail="El identificador de compra no es válido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        # Validar existencia y estado actual de la orden en la BD
        cur.execute("SELECT ESTADO_OC FROM COMPRAS WHERE id_Compra = %s", (clean_id,))
        order_row = cur.fetchone()
        if not order_row:
            raise HTTPException(status_code=404, detail=f"La orden de compra '{clean_id}' no existe.")

        current_state = order_row[0].strip()
        if current_state != "ABI":
            estado_texto = "Aprobada (APR)" if current_state == "APR" else ("Anulada (ANU)" if current_state == "ANU" else current_state)
            raise HTTPException(
                status_code=400,
                detail=f"La orden {clean_id} ya se encuentra en estado '{estado_texto}' y no puede volver a modificarse."
            )

        user_id = get_user_id(cur)
        try:
            cur.callproc(procedure, (clean_id, user_id))
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                new_state = "APR" if procedure == "SP_COMPRA_APROBAR" else "ANU"
                cur.execute("UPDATE COMPRAS SET ESTADO_OC = %s WHERE id_Compra = %s", (new_state, clean_id))
                cur.execute("UPDATE PROxOC SET ESTADO_PxOC = %s WHERE id_Compra = %s", (new_state, clean_id))
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
                (clean_id,),
            )
            receipt = cur.fetchone()
            if receipt is None:
                cur.execute("SELECT id_Recibo FROM RECEPCIONES")
                existing_rec = cur.fetchall()
                max_rec_num = 0
                for r in existing_rec:
                    val = str(r[0] if isinstance(r, (list, tuple)) else r.get("id_Recibo", ""))
                    m = re.match(r"^REC-(\d+)$", val, re.IGNORECASE)
                    if m:
                        num = int(m.group(1))
                        if num > max_rec_num:
                            max_rec_num = num
                receipt_id = f"REC-{max_rec_num + 1:06d}"
                cur.execute(
                    """
                    INSERT INTO RECEPCIONES
                        (id_Recibo, id_Compra, rec_Descripcion, rec_FechaHora,
                         rec_Num_Produc, ESTADO_REC)
                    VALUES (%s, %s, 'Recepción de compra', NOW(), 0, 'PEN')
                    """,
                    (receipt_id, clean_id),
                )
            else:
                receipt_id = receipt[0].strip()
            cur.execute(
                """
                SELECT TRIM(id_Producto), pxo_Cantidad
                FROM PROxOC
                WHERE id_Compra = %s
                """,
                (clean_id,),
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
            "id": clean_id,
            "estado": "APR" if procedure == "SP_COMPRA_APROBAR" else "ANU",
            "mensaje": f"Orden {clean_id} {'aprobada' if procedure == 'SP_COMPRA_APROBAR' else 'anulada'} exitosamente.",
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
        cur.execute("SHOW COLUMNS FROM PRODUCTOS LIKE 'id_Percha'")
        has_shelf = bool(cur.fetchone())
        shelf_select = "COALESCE(TRIM(H.pch_Descripcion), CONCAT('Percha ', TRIM(H.pch_Letra), H.pch_Nivel), 'A1') AS shelf, TRIM(P.id_Percha) AS shelfId," if has_shelf else "'A1' AS shelf, NULL AS shelfId,"
        shelf_join = "LEFT JOIN PERCHAS H ON P.id_Percha = H.id_Percha" if has_shelf else ""

        cur.execute(
            f"""
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
                TRIM(P.pro_UM_Compra) AS buyUnitId,
                COALESCE(TRIM(UC.um_Descripcion), TRIM(P.pro_UM_Compra)) AS buyUnit,
                TRIM(P.pro_UM_Venta) AS sellUnitId,
                COALESCE(TRIM(UV.um_Descripcion), TRIM(P.pro_UM_Venta)) AS sellUnit,
                COALESCE(UC.um_FactorConversion, 1.00) AS purchaseFactor,
                COALESCE(UV.um_FactorConversion, 1.00) AS sellFactor,
                ROUND(COALESCE(UC.um_FactorConversion, 1.00) / NULLIF(COALESCE(UV.um_FactorConversion, 1.00), 0), 2) AS factorConversion,
                {shelf_select}
                IF(P.ESTADO_PROD = 'ACT', 'ACTIVE', 'INACTIVE') AS status
            FROM PRODUCTOS P
            LEFT JOIN MARCAS M ON P.id_Marca = M.id_Marca
            LEFT JOIN CATEGORIAS C ON P.id_Categoria = C.id_Categoria
            LEFT JOIN UNIDADES_MEDIDAS UC ON P.pro_UM_Compra = UC.id_Unidad_Medida
            LEFT JOIN UNIDADES_MEDIDAS UV ON P.pro_UM_Venta = UV.id_Unidad_Medida
            {shelf_join}
            ORDER BY P.pro_Descripcion
            """
        )
        products = cur.fetchall()
        for p in products:
            if p.get("purchaseFactor") is not None:
                p["purchaseFactor"] = float(p["purchaseFactor"])
            if p.get("sellFactor") is not None:
                p["sellFactor"] = float(p["sellFactor"])
            if p.get("factorConversion") is not None:
                p["factorConversion"] = float(p["factorConversion"])
            else:
                p["factorConversion"] = 1.0
        return products
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/productos")
def crear_producto(prod: ProductInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        # Validación anti-duplicados por nombre
        cur.execute(
            "SELECT id_Producto FROM PRODUCTOS WHERE LOWER(TRIM(pro_Descripcion)) = LOWER(TRIM(%s)) LIMIT 1",
            (prod.name,),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un producto registrado con la descripción '{prod.name}'.",
            )

        # Validación de claves foráneas
        cur.execute("SELECT id_Categoria FROM CATEGORIAS WHERE id_Categoria = %s", (prod.category_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La categoría '{prod.category_id}' no existe en el catálogo.")

        cur.execute("SELECT id_Marca FROM MARCAS WHERE id_Marca = %s", (prod.brand_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La marca '{prod.brand_id}' no existe en el catálogo.")

        cur.execute("SELECT id_Unidad_Medida FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (prod.buy_unit,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La unidad de compra '{prod.buy_unit}' no existe en la base de datos.")

        cur.execute("SELECT id_Unidad_Medida FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (prod.sell_unit,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La unidad de venta '{prod.sell_unit}' no existe en la base de datos.")

        cur.execute("SHOW COLUMNS FROM PRODUCTOS LIKE 'id_Percha'")
        has_shelf = bool(cur.fetchone())
        if has_shelf and prod.shelf_id:
            cur.execute("SELECT id_Percha FROM PERCHAS WHERE id_Percha = %s", (prod.shelf_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail=f"La percha '{prod.shelf_id}' no existe.")

        if prod.id and prod.id.strip():
            clean_id = prod.id.strip()[:10]
            cur.execute("SELECT id_Producto FROM PRODUCTOS WHERE id_Producto = %s", (clean_id,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail=f"El código de producto '{clean_id}' ya se encuentra registrado.")
            product_id = clean_id
        else:
            cur.execute("SELECT id_Producto FROM PRODUCTOS")
            existing_rows = cur.fetchall()
            max_id = 0
            for r in existing_rows:
                val = str(r[0] if isinstance(r, (list, tuple)) else r.get("id_Producto", ""))
                m = re.match(r"^PRD-(\d+)$", val, re.IGNORECASE)
                if m:
                    num = int(m.group(1))
                    if num > max_id:
                        max_id = num
            product_id = f"PRD-{max_id + 1:06d}"

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
            if proc_err.errno in {1305, 1318, 1364, 1452}:
                if has_shelf and prod.shelf_id:
                    cur.execute(
                        """
                        INSERT INTO PRODUCTOS (
                            id_Producto, id_Categoria, id_Marca, id_Percha, pro_Descripcion,
                            pro_UM_Compra, pro_UM_Venta, pro_Valor_Compra,
                            pro_Precio_Venta, pro_Saldo_Inicial, pro_Qty_Ingresos,
                            pro_Qty_Egresos, pro_Qty_Ajustes, pro_Saldo_Final, ESTADO_PROD
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, %s, 'ACT')
                        """,
                        (
                            product_id,
                            prod.category_id,
                            prod.brand_id,
                            prod.shelf_id,
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
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/productos/{product_id}")
def actualizar_producto(product_id: str, prod: ProductInput):
    clean_id = str(product_id or "").strip()
    if not re.match(r"^[A-Za-z0-9\-]+$", clean_id) or RE_SQLI_DANGEROUS.search(clean_id):
        raise HTTPException(status_code=400, detail="Identificador de producto no válido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        # Verificar existencia
        cur.execute("SELECT id_Producto FROM PRODUCTOS WHERE id_Producto = %s", (clean_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="El producto especificado no existe.")

        # Verificar duplicado de descripción con otro producto
        cur.execute(
            "SELECT id_Producto FROM PRODUCTOS WHERE LOWER(TRIM(pro_Descripcion)) = LOWER(TRIM(%s)) AND id_Producto != %s LIMIT 1",
            (prod.name, clean_id),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe otro producto registrado con la descripción '{prod.name}'.",
            )

        # Validar claves foráneas
        cur.execute("SELECT id_Categoria FROM CATEGORIAS WHERE id_Categoria = %s", (prod.category_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La categoría '{prod.category_id}' no existe.")

        cur.execute("SELECT id_Marca FROM MARCAS WHERE id_Marca = %s", (prod.brand_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La marca '{prod.brand_id}' no existe.")

        cur.execute("SELECT id_Unidad_Medida FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (prod.buy_unit,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La unidad de compra '{prod.buy_unit}' no existe.")

        cur.execute("SELECT id_Unidad_Medida FROM UNIDADES_MEDIDAS WHERE id_Unidad_Medida = %s", (prod.sell_unit,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"La unidad de venta '{prod.sell_unit}' no existe.")

        cur.execute("SHOW COLUMNS FROM PRODUCTOS LIKE 'id_Percha'")
        has_shelf = bool(cur.fetchone())

        if has_shelf and prod.shelf_id:
            cur.execute("SELECT id_Percha FROM PERCHAS WHERE id_Percha = %s", (prod.shelf_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail=f"La percha '{prod.shelf_id}' no existe.")
            cur.execute(
                """
                UPDATE PRODUCTOS
                SET pro_Descripcion = %s,
                    id_Categoria = %s,
                    id_Marca = %s,
                    id_Percha = %s,
                    pro_UM_Compra = %s,
                    pro_UM_Venta = %s,
                    pro_Valor_Compra = %s,
                    pro_Precio_Venta = %s
                WHERE id_Producto = %s
                """,
                (prod.name[:40], prod.category_id, prod.brand_id, prod.shelf_id, prod.buy_unit[:3], prod.sell_unit[:3], prod.buy_cost, prod.sell_price, clean_id),
            )
        else:
            cur.execute(
                """
                UPDATE PRODUCTOS
                SET pro_Descripcion = %s,
                    id_Categoria = %s,
                    id_Marca = %s,
                    pro_UM_Compra = %s,
                    pro_UM_Venta = %s,
                    pro_Valor_Compra = %s,
                    pro_Precio_Venta = %s
                WHERE id_Producto = %s
                """,
                (prod.name[:40], prod.category_id, prod.brand_id, prod.buy_unit[:3], prod.sell_unit[:3], prod.buy_cost, prod.sell_price, clean_id),
            )
        conn.commit()
        return {"id": clean_id, "mensaje": "Producto actualizado exitosamente."}
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/productos/{product_id}/estado")
def cambiar_estado_producto(product_id: str, payload: ProductStatusInput):
    clean_id = str(product_id or "").strip()
    if not re.match(r"^[A-Za-z0-9\-]+$", clean_id) or RE_SQLI_DANGEROUS.search(clean_id):
        raise HTTPException(status_code=400, detail="Identificador de producto no válido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("SELECT id_Producto FROM PRODUCTOS WHERE id_Producto = %s", (clean_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="El producto especificado no existe.")

        cur.execute(
            "UPDATE PRODUCTOS SET ESTADO_PROD = %s WHERE id_Producto = %s",
            (payload.status, clean_id),
        )
        conn.commit()
        return {
            "id": clean_id,
            "estado": payload.status,
            "mensaje": f"Estado del producto actualizado a {payload.status}.",
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
            ORDER BY P.id_Proveedor DESC
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

        # 1. Validar que no exista otro proveedor con el mismo RUC/Cédula
        cur.execute("SELECT id_Proveedor, prv_Nombre FROM PROVEEDORES WHERE prv_RUC_CED = %s", (prv.ruc,))
        duplicado = cur.fetchone()
        if duplicado:
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe un proveedor registrado con el RUC/Cédula {prv.ruc} ({duplicado[1].strip()})."
            )

        # 2. Validar que la ciudad exista
        cur.execute("SELECT 1 FROM CIUDADES WHERE id_Ciudad = %s", (prv.city_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail=f"La ciudad con código '{prv.city_id}' no existe en el catálogo.")

        # 3. ID de proveedor seguro y correlativo
        if prv.id and prv.id.strip():
            supplier_id = prv.id.strip()[:10]
            cur.execute("SELECT 1 FROM PROVEEDORES WHERE id_Proveedor = %s", (supplier_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe un proveedor con el ID {supplier_id}.")
        else:
            cur.execute("SELECT id_Proveedor FROM PROVEEDORES")
            existing_rows = cur.fetchall()
            max_id = 0
            for row in existing_rows:
                id_val = str(row[0] if isinstance(row, (list, tuple)) else row.get("id_Proveedor", ""))
                m = re.match(r"^prv_(\d+)$", id_val, re.IGNORECASE)
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
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/proveedores/{supplier_id}")
def actualizar_proveedor(supplier_id: str, prv: SupplierInput):
    clean_id = str(supplier_id or "").strip()
    if not clean_id or len(clean_id) > 10 or RE_SQLI_DANGEROUS.search(clean_id) or not re.match(r"^[A-Za-z0-9_\-]+$", clean_id):
        raise HTTPException(status_code=422, detail="Identificador de proveedor inválido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        # Verificar existencia
        cur.execute("SELECT 1 FROM PROVEEDORES WHERE id_Proveedor = %s", (clean_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"El proveedor {clean_id} no existe.")

        # Verificar RUC duplicado en otro proveedor
        cur.execute(
            "SELECT id_Proveedor, prv_Nombre FROM PROVEEDORES WHERE prv_RUC_CED = %s AND id_Proveedor != %s",
            (prv.ruc, clean_id)
        )
        duplicado = cur.fetchone()
        if duplicado:
            raise HTTPException(
                status_code=409,
                detail=f"El RUC/Cédula {prv.ruc} ya pertenece a otro proveedor registrado ({duplicado[1].strip()})."
            )

        # Validar ciudad
        cur.execute("SELECT 1 FROM CIUDADES WHERE id_Ciudad = %s", (prv.city_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=422, detail=f"La ciudad con código '{prv.city_id}' no existe en el catálogo.")

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
                clean_id,
            ),
        )
        conn.commit()
        return {"id": clean_id, "mensaje": "Proveedor actualizado exitosamente."}
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.patch("/api/proveedores/{supplier_id}/estado")
def cambiar_estado_proveedor(supplier_id: str, payload: dict):
    clean_id = str(supplier_id or "").strip()
    if not clean_id or len(clean_id) > 10 or RE_SQLI_DANGEROUS.search(clean_id) or not re.match(r"^[A-Za-z0-9_\-]+$", clean_id):
        raise HTTPException(status_code=422, detail="Identificador de proveedor inválido.")

    raw_estado = str(payload.get("estado", "")).strip().upper()
    if raw_estado in ["ACTIVE", "ACT"]:
        db_estado = "ACT"
    elif raw_estado in ["INACTIVE", "INA"]:
        db_estado = "INA"
    else:
        raise HTTPException(status_code=422, detail="Estado inválido. Solo se admite 'ACT' (Activo) o 'INA' (Inactivo).")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        cur.execute("SELECT prv_Nombre FROM PROVEEDORES WHERE id_Proveedor = %s", (clean_id,))
        prov = cur.fetchone()
        if not prov:
            raise HTTPException(status_code=404, detail=f"El proveedor {clean_id} no existe.")

        cur.execute(
            "UPDATE PROVEEDORES SET ESTADO_PRV = %s WHERE id_Proveedor = %s",
            (db_estado, clean_id),
        )
        conn.commit()
        return {
            "id": clean_id,
            "estado": "ACTIVE" if db_estado == "ACT" else "INACTIVE",
            "mensaje": f"Estado del proveedor {prov[0].strip()} actualizado a {'Activo' if db_estado == 'ACT' else 'Inactivo'}.",
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
                F.fac_Descuento AS discount,
                15.00 AS taxRate,
                F.fac_IVA AS tax,
                F.fac_Total AS total,
                F.fac_FormaPago AS paymentMethod,
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

        discount = sale.discount_amount.quantize(CENT, rounding=ROUND_HALF_UP)
        if discount > subtotal:
            raise HTTPException(status_code=422, detail="El descuento no puede superar el subtotal de la venta.")
        taxable_subtotal = subtotal - discount
        tax = (taxable_subtotal * sale.tax_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        total = taxable_subtotal + tax

        # 3. Invocar SP_FACTURA_CREAR
        cur.callproc(
            "SP_FACTURA_CREAR",
            (
                invoice_id,
                sale.customer_id,
                employee_id,
                sale.description[:60],
                Decimal("0"),
                discount,
                Decimal("0"),
                Decimal("0"),
                sale.payment_method,
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
            VALUES (%s, %s, 'PRUEBA Entrega venta POS', NOW(), %s, 'PEN')
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
    clean_id = str(receipt_id or "").strip()
    if not re.match(r"^[A-Za-z0-9\-]+$", clean_id) or RE_SQLI_DANGEROUS.search(clean_id):
        raise HTTPException(status_code=400, detail="Identificador de recibo inválido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        cur.execute("SELECT ESTADO_REC FROM RECEPCIONES WHERE id_Recibo = %s", (clean_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="El recibo de mercadería especificado no existe.")
        status_rec = row[0] if isinstance(row, (tuple, list)) else row.get("ESTADO_REC")
        if status_rec in ("APR", "COMPLETED", "APROBADO"):
            raise HTTPException(status_code=400, detail="Esta recepción ya fue confirmada previamente.")
        if status_rec in ("ANU", "ANULADO"):
            raise HTTPException(status_code=400, detail="No se puede confirmar una recepción que se encuentra anulada.")

        for item in payload.items:
            prod_id = item.product_id
            received_qty = item.received_qty
            reason = item.reason.strip()

            cur.execute(
                "SELECT pxr_Cantidad, pxr_Qty_Recibida FROM PROxREC WHERE id_Recibo = %s AND id_Producto = %s",
                (clean_id, prod_id),
            )
            detail_row = cur.fetchone()
            if not detail_row:
                raise HTTPException(status_code=404, detail=f"El producto '{prod_id}' no forma parte de este recibo.")
            expected_qty = detail_row[0]
            prev_qty = detail_row[1] or 0
            diff = received_qty - expected_qty
            if diff != 0 and not reason:
                raise HTTPException(
                    status_code=422,
                    detail=f"Debe registrar un motivo para la diferencia de cantidad en el producto {prod_id} (esperado: {expected_qty}, recibido: {received_qty}).",
                )

            diff_to_add = received_qty - prev_qty

            cur.execute(
                """
                UPDATE PROxREC
                SET pxr_Qty_Recibida = %s,
                    pxr_Motivo = %s,
                    ESTADO_PxREC = 'APR'
                WHERE id_Recibo = %s AND id_Producto = %s
                """,
                (received_qty, reason[:60] if reason else None, clean_id, prod_id),
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
            (clean_id,),
        )
        conn.commit()
        return {"id": clean_id, "estado": "APR", "mensaje": "Ingreso a bodega confirmado exitosamente."}
    except HTTPException:
        if conn: conn.rollback()
        raise
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
    clean_id = str(delivery_id or "").strip()
    if not re.match(r"^[A-Za-z0-9\-]+$", clean_id) or RE_SQLI_DANGEROUS.search(clean_id):
        raise HTTPException(status_code=400, detail="Identificador de entrega no válido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        cur.execute("SELECT ESTADO_ENT FROM ENTREGAS WHERE id_Entrega = %s", (clean_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="La orden de entrega especificada no existe.")
        status_ent = row[0] if isinstance(row, (tuple, list)) else row.get("ESTADO_ENT")
        if status_ent in ("APR", "COMPLETED", "APROBADO"):
            raise HTTPException(status_code=400, detail="Este despacho de entrega ya fue confirmado previamente.")
        if status_ent in ("ANU", "ANULADO"):
            raise HTTPException(status_code=400, detail="No se puede confirmar un despacho que ha sido anulado.")

        for item in payload.items:
            prod_id = item.product_id
            delivered_qty = item.delivered_qty
            reason = item.reason.strip()

            cur.execute(
                "SELECT pxe_Cantidad FROM PROxENT WHERE id_Entrega = %s AND id_Producto = %s",
                (clean_id, prod_id),
            )
            detail_row = cur.fetchone()
            if not detail_row:
                raise HTTPException(status_code=404, detail=f"El producto '{prod_id}' no forma parte de este despacho.")
            expected_qty = detail_row[0]
            diff = delivered_qty - expected_qty
            if diff != 0 and not reason:
                raise HTTPException(
                    status_code=422,
                    detail=f"Debe registrar un motivo para la diferencia de cantidad en el producto {prod_id} (facturado: {expected_qty}, entregado: {delivered_qty}).",
                )

            cur.execute(
                """
                UPDATE PROxENT
                SET pxe_Qty_Entregada = %s,
                    pxe_Motivo = %s,
                ESTADO_PxENT = 'ENT'
                WHERE id_Entrega = %s AND id_Producto = %s
                """,
                (delivered_qty, reason[:60] if reason else None, clean_id, prod_id),
            )

        cur.execute(
            "UPDATE ENTREGAS SET ESTADO_ENT = 'ENT' WHERE id_Entrega = %s",
            (clean_id,),
        )
        conn.commit()
        return {"id": clean_id, "estado": "ENT", "mensaje": "Despacho de venta confirmado exitosamente."}
    except HTTPException:
        if conn: conn.rollback()
        raise
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
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        # Validar existencia de producto
        cur.execute("SELECT pro_Saldo_Final, ESTADO_PROD FROM PRODUCTOS WHERE id_Producto = %s", (aju.product_id,))
        prod_row = cur.fetchone()
        if not prod_row:
            raise HTTPException(status_code=404, detail=f"El producto '{aju.product_id}' no existe en el catálogo.")
        if prod_row[1] != "ACT":
            raise HTTPException(status_code=400, detail="No se pueden realizar ajustes sobre un producto inactivo.")

        # Validar empleado
        cur.execute("SELECT id_Empleado FROM EMPLEADOS WHERE id_Empleado = %s", (aju.employee_id,))
        if not cur.fetchone():
            cur.execute("SELECT id_Empleado FROM EMPLEADOS ORDER BY id_Empleado ASC LIMIT 1")
            emp_fallback = cur.fetchone()
            if emp_fallback:
                aju.employee_id = emp_fallback[0]
            else:
                raise HTTPException(status_code=400, detail="No existe un empleado responsable registrado.")

        # Generar ID secuencial AJU-000001
        cur.execute("SELECT id_Ajuste FROM AJUSTES")
        existing_rows = cur.fetchall()
        max_id = 0
        for r in existing_rows:
            val = str(r[0] if isinstance(r, (list, tuple)) else r.get("id_Ajuste", ""))
            m = re.match(r"^AJU-(\d+)$", val, re.IGNORECASE)
            if m:
                num = int(m.group(1))
                if num > max_id:
                    max_id = num
        adjustment_id = f"AJU-{max_id + 1:06d}"

        user_id = get_user_id(cur)

        try:
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
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1318, 1452}:
                cur.execute(
                    """
                    INSERT INTO AJUSTES (id_Ajuste, id_Empleado, aju_FechaHora, aju_Descripcion, ESTADO_AJU)
                    VALUES (%s, %s, NOW(), %s, 'ABI')
                    """,
                    (adjustment_id, aju.employee_id, aju.reason[:30]),
                )
            else:
                raise

        signed_qty = aju.quantity if aju.type == "IN" else -aju.quantity
        cur.execute(
            """
            INSERT INTO PROxAJU (id_Ajuste, id_Producto, pxa_Cantidad, pxa_Qty_Ajustada, ESTADO_PxAJU)
            VALUES (%s, %s, %s, %s, 'ABI')
            """,
            (adjustment_id, aju.product_id, aju.quantity, signed_qty),
        )
        conn.commit()
        return {"id": adjustment_id, "estado": "ABI", "mensaje": "Ajuste físico registrado en estado Abierto (ABI)."}
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ajustes/{adjustment_id}/aprobar")
def aprobar_ajuste(adjustment_id: str):
    clean_id = str(adjustment_id or "").strip()
    if not re.match(r"^[A-Za-z0-9\-]+$", clean_id) or RE_SQLI_DANGEROUS.search(clean_id):
        raise HTTPException(status_code=400, detail="Identificador de ajuste no válido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        cur.execute("SELECT ESTADO_AJU FROM AJUSTES WHERE id_Ajuste = %s", (clean_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="El ajuste de inventario no existe.")
        estado = row[0]
        if estado == "APR":
            raise HTTPException(status_code=400, detail="El ajuste ya se encuentra aprobado.")
        if estado == "ANU":
            raise HTTPException(status_code=400, detail="No se puede aprobar un ajuste que ha sido anulado.")
        if estado != "ABI":
            raise HTTPException(status_code=400, detail=f"Solo se pueden aprobar ajustes en estado Abierto (estado actual: {estado}).")

        user_id = get_user_id(cur)
        try:
            cur.callproc("SP_AJUSTE_APROBAR", (clean_id, user_id))
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1318, 1452}:
                cur.execute("UPDATE AJUSTES SET ESTADO_AJU = 'APR' WHERE id_Ajuste = %s", (clean_id,))
                cur.execute("UPDATE PROxAJU SET ESTADO_PxAJU = 'APR' WHERE id_Ajuste = %s", (clean_id,))
            else:
                raise

        conn.commit()
        return {"id": clean_id, "estado": "APR", "mensaje": "Ajuste aprobado e impactado en inventario."}
    except HTTPException:
        if conn: conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/ajustes/{adjustment_id}/anular")
def anular_ajuste(adjustment_id: str):
    clean_id = str(adjustment_id or "").strip()
    if not re.match(r"^[A-Za-z0-9\-]+$", clean_id) or RE_SQLI_DANGEROUS.search(clean_id):
        raise HTTPException(status_code=400, detail="Identificador de ajuste no válido.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        cur.execute("SELECT ESTADO_AJU FROM AJUSTES WHERE id_Ajuste = %s", (clean_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="El ajuste de inventario no existe.")
        estado = row[0]
        if estado == "ANU":
            raise HTTPException(status_code=400, detail="El ajuste ya se encuentra anulado.")
        if estado == "APR":
            raise HTTPException(status_code=400, detail="No se puede anular un ajuste que ya ha sido aprobado e impactado en inventario.")
        if estado != "ABI":
            raise HTTPException(status_code=400, detail=f"Solo se pueden anular ajustes en estado Abierto (estado actual: {estado}).")

        user_id = get_user_id(cur)
        try:
            cur.callproc("SP_AJUSTE_ANULAR", (clean_id, user_id))
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1318, 1452}:
                cur.execute("UPDATE AJUSTES SET ESTADO_AJU = 'ANU' WHERE id_Ajuste = %s", (clean_id,))
                cur.execute("UPDATE PROxAJU SET ESTADO_PxAJU = 'ANU' WHERE id_Ajuste = %s", (clean_id,))
            else:
                raise

        conn.commit()
        return {"id": clean_id, "estado": "ANU", "mensaje": "Ajuste anulado exitosamente."}
    except HTTPException:
        if conn: conn.rollback()
        raise
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 8. MÓDULO TALENTO HUMANO / NÓMINA
# ==========================================

@app.get("/api/departamentos")
def listar_departamentos():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT TRIM(id_Departamento) AS id, TRIM(dep_Nombre) AS nombre
            FROM DEPARTAMENTOS
            WHERE ESTADO_DEP = 'ACT' OR ESTADO_DEP IS NULL
            ORDER BY dep_Nombre
            """
        )
        rows = cur.fetchall()
        if not rows:
            cur.execute("SELECT 1 FROM DEPARTAMENTOS LIMIT 1")
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO DEPARTAMENTOS
                        (id_Departamento, dep_Nombre, ESTADO_DEP)
                    VALUES ('DEP-000001', 'Administración', 'ACT')
                    """
                )
                conn.commit()
                cur.execute(
                    """
                    SELECT TRIM(id_Departamento) AS id, TRIM(dep_Nombre) AS nombre
                    FROM DEPARTAMENTOS
                    WHERE ESTADO_DEP = 'ACT' OR ESTADO_DEP IS NULL
                    ORDER BY dep_Nombre
                    """
                )
                rows = cur.fetchall()
        return rows
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/cargos")
def listar_cargos():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT TRIM(id_Cargo) AS id, TRIM(cgo_Descripcion) AS nombre FROM CARGOS ORDER BY cgo_Descripcion")
        rows = cur.fetchall()
        if not rows:
            cur.execute("INSERT IGNORE INTO CARGOS (id_Cargo, cgo_Descripcion, ESTADO_CGO) VALUES ('CGO-000001', 'Administrador', 'ACT'), ('CGO-000002', 'Vendedor / Cajero', 'ACT'), ('CGO-000003', 'Bodeguero', 'ACT')")
            conn.commit()
            cur.execute("SELECT TRIM(id_Cargo) AS id, TRIM(cgo_Descripcion) AS nombre FROM CARGOS ORDER BY cgo_Descripcion")
            rows = cur.fetchall()
        return rows
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


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
                CONCAT(TRIM(E.emp_Nombre1), ' ', COALESCE(CONCAT(TRIM(E.emp_Nombre2), ' '), ''), TRIM(E.emp_Apellido1), ' ', COALESCE(TRIM(E.emp_Apellido2), '')) AS name,
                TRIM(E.emp_Nombre1) AS nombre1,
                COALESCE(TRIM(E.emp_Nombre2), '') AS nombre2,
                TRIM(E.emp_Apellido1) AS apellido1,
                COALESCE(TRIM(E.emp_Apellido2), '') AS apellido2,
                COALESCE(TRIM(D.dep_Nombre), 'Ventas') AS department,
                TRIM(E.id_Departamento) AS departmentId,
                COALESCE(TRIM(C.cgo_Descripcion), 'Colaborador') AS role,
                COALESCE(TRIM(CXE.id_Cargo), '') AS cargoId,
                E.emp_Sueldo AS salary,
                E.emp_FechaNacimiento AS birthDate,
                COALESCE(TRIM(E.emp_Sexo), 'M') AS gender,
                COALESCE(TRIM(E.emp_Direccion), '') AS address,
                COALESCE(TRIM(E.emp_Telefono), '') AS phone,
                COALESCE(TRIM(E.emp_Celular), '') AS mobile,
                COALESCE(TRIM(E.emp_Mail), '') AS email,
                IF(E.ESTADO_EMP = 'ACT' OR E.ESTADO_EMP IS NULL, 'ACTIVE', 'INACTIVE') AS status,
                (SELECT COUNT(*) FROM CARGAS CG WHERE CG.id_Empleado = E.id_Empleado AND (CG.ESTADO_CAR = 'ACT' OR CG.ESTADO_CAR IS NULL)) AS familyDependents
            FROM EMPLEADOS E
            LEFT JOIN DEPARTAMENTOS D ON E.id_Departamento = D.id_Departamento
            LEFT JOIN (
                SELECT CE1.id_Empleado, CE1.id_Cargo
                FROM CARGOSxEMPLEADO CE1
                INNER JOIN (
                    SELECT id_Empleado, MAX(cxe_Fecha_Inicio) AS max_fecha
                    FROM CARGOSxEMPLEADO
                    WHERE ESTADO_CxE = 'ACT' OR ESTADO_CxE IS NULL
                    GROUP BY id_Empleado
                ) CE2 ON CE1.id_Empleado = CE2.id_Empleado AND CE1.cxe_Fecha_Inicio = CE2.max_fecha
            ) CXE ON E.id_Empleado = CXE.id_Empleado
            LEFT JOIN CARGOS C ON CXE.id_Cargo = C.id_Cargo
            GROUP BY E.id_Empleado
            ORDER BY E.emp_Apellido1, E.emp_Nombre1
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/empleados")
def crear_empleado(emp: EmployeeInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)

        if emp.id and emp.id.strip():
            employee_id = emp.id.strip()[:10]
        else:
            import re
            cur.execute("SELECT id_Empleado FROM EMPLEADOS")
            existing_rows = cur.fetchall()
            max_num = 0
            for r in existing_rows:
                val = str(r[0] if isinstance(r, (list, tuple)) else r.get("id_Empleado", ""))
                m = re.match(r"^EMP-(\d+)$", val, re.IGNORECASE)
                if m:
                    num = int(m.group(1))
                    if num > max_num:
                        max_num = num
            employee_id = f"EMP-{max_num + 1:06d}"

        # Asegurar que el departamento exista para FK
        dep_id = emp.department_id[:10]
        cur.execute("SELECT id_Departamento FROM DEPARTAMENTOS WHERE id_Departamento = %s", (dep_id,))
        dept_row = cur.fetchone()
        if not dept_row:
            cur.execute("INSERT IGNORE INTO DEPARTAMENTOS (id_Departamento, dep_Nombre, ESTADO_DEP) VALUES (%s, 'General', 'ACT')", (dep_id,))

        # Validar duplicidad de cédula
        cur.execute("SELECT id_Empleado FROM EMPLEADOS WHERE emp_Cedula = %s LIMIT 1", (emp.ci,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe un empleado registrado con la cédula {emp.ci}.")

        cur.execute(
            """
            INSERT INTO EMPLEADOS (
                id_Empleado, id_Departamento, emp_Cedula, emp_Apellido1, emp_Apellido2,
                emp_Nombre1, emp_Nombre2, emp_Sexo, emp_FechaNacimiento, emp_Sueldo,
                emp_Direccion, emp_Telefono, emp_Celular, emp_Mail, USER_ID, ESTADO_EMP
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACT')
            """,
            (
                employee_id,
                dep_id,
                emp.ci[:20],
                emp.last_name1[:30],
                emp.last_name2[:30] if emp.last_name2 else None,
                emp.first_name[:30],
                emp.second_name[:30] if emp.second_name else None,
                emp.gender[:1].upper() if emp.gender else 'M',
                emp.birth_date,
                emp.salary,
                emp.address[:60] if emp.address else None,
                emp.phone[:10] if emp.phone else None,
                emp.mobile[:10] if emp.mobile else None,
                emp.email[:60] if emp.email else None,
                user_id,
            ),
        )

        if emp.cargo_id:
            cur.execute("SELECT id_Cargo FROM CARGOS WHERE id_Cargo = %s", (emp.cargo_id[:10],))
            if not cur.fetchone():
                cur.execute("INSERT IGNORE INTO CARGOS (id_Cargo, cgo_Descripcion, ESTADO_CGO) VALUES (%s, 'General', 'ACT')", (emp.cargo_id[:10],))
            cur.execute(
                """
                INSERT INTO CARGOSxEMPLEADO (id_Cargo, id_Empleado, cxe_Fecha_Inicio, USER_ID, ESTADO_CxE)
                VALUES (%s, %s, CURDATE(), %s, 'ACT')
                ON DUPLICATE KEY UPDATE ESTADO_CxE = 'ACT'
                """,
                (emp.cargo_id[:10], employee_id, user_id),
            )

        conn.commit()
        return {"id": employee_id, "mensaje": f"Empleado {emp.first_name} {emp.last_name1} ({employee_id}) registrado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/empleados/{employee_id}")
def actualizar_empleado(employee_id: str, emp: EmployeeInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        dep_id = emp.department_id[:10]
        cur.execute("SELECT id_Departamento FROM DEPARTAMENTOS WHERE id_Departamento = %s", (dep_id,))
        if not cur.fetchone():
            cur.execute("INSERT IGNORE INTO DEPARTAMENTOS (id_Departamento, dep_Nombre, ESTADO_DEP) VALUES (%s, 'General', 'ACT')", (dep_id,))

        # Validar duplicidad de cédula en otro empleado
        cur.execute("SELECT id_Empleado FROM EMPLEADOS WHERE emp_Cedula = %s AND id_Empleado <> %s LIMIT 1", (emp.ci, employee_id))
        dupe = cur.fetchone()
        if dupe:
            raise HTTPException(status_code=409, detail=f"La cédula {emp.ci} ya se encuentra asignada a otro colaborador ({dupe[0]}).")

        cur.execute(
            """
            UPDATE EMPLEADOS
            SET emp_Cedula = %s,
                emp_Apellido1 = %s,
                emp_Apellido2 = %s,
                emp_Nombre1 = %s,
                emp_Nombre2 = %s,
                emp_Sexo = %s,
                emp_FechaNacimiento = %s,
                emp_Sueldo = %s,
                emp_Direccion = %s,
                emp_Telefono = %s,
                emp_Celular = %s,
                emp_Mail = %s,
                id_Departamento = %s,
                USER_ID = %s
            WHERE id_Empleado = %s
            """,
            (
                emp.ci[:20],
                emp.last_name1[:30],
                emp.last_name2[:30] if emp.last_name2 else None,
                emp.first_name[:30],
                emp.second_name[:30] if emp.second_name else None,
                emp.gender[:1].upper() if emp.gender else 'M',
                emp.birth_date,
                emp.salary,
                emp.address[:60] if emp.address else None,
                emp.phone[:10] if emp.phone else None,
                emp.mobile[:10] if emp.mobile else None,
                emp.email[:60] if emp.email else None,
                dep_id,
                user_id,
                employee_id,
            ),
        )

        if emp.cargo_id:
            cur.execute("SELECT id_Cargo FROM CARGOS WHERE id_Cargo = %s", (emp.cargo_id[:10],))
            if not cur.fetchone():
                cur.execute("INSERT IGNORE INTO CARGOS (id_Cargo, cgo_Descripcion, ESTADO_CGO) VALUES (%s, 'General', 'ACT')", (emp.cargo_id[:10],))
            cur.execute(
                """
                INSERT INTO CARGOSxEMPLEADO (id_Cargo, id_Empleado, cxe_Fecha_Inicio, USER_ID, ESTADO_CxE)
                VALUES (%s, %s, CURDATE(), %s, 'ACT')
                ON DUPLICATE KEY UPDATE ESTADO_CxE = 'ACT'
                """,
                (emp.cargo_id[:10], employee_id, user_id),
            )

        conn.commit()
        return {"id": employee_id, "mensaje": f"Ficha de {emp.first_name} {emp.last_name1} actualizada exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/empleados/{employee_id}/cargos")
def listar_historial_cargos(employee_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(CE.id_Cargo) AS cargoId,
                TRIM(C.cgo_Descripcion) AS cargoNombre,
                CE.cxe_Fecha_Inicio AS fechaInicio,
                CE.cxe_Fecha_Fin AS fechaFin,
                TRIM(CE.ESTADO_CxE) AS estado
            FROM CARGOSxEMPLEADO CE
            INNER JOIN CARGOS C ON CE.id_Cargo = C.id_Cargo
            WHERE CE.id_Empleado = %s
            ORDER BY CE.cxe_Fecha_Inicio DESC
            """,
            (employee_id,),
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/empleados/{employee_id}/cargos")
def asignar_cargo_empleado(employee_id: str, cargo: CargoAssignInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        
        # Cerrar cargo previo activo si la fecha fin era nula
        cur.execute(
            """
            UPDATE CARGOSxEMPLEADO
            SET cxe_Fecha_Fin = %s, ESTADO_CxE = 'INA'
            WHERE id_Empleado = %s AND (cxe_Fecha_Fin IS NULL OR cxe_Fecha_Fin >= %s) AND id_Cargo <> %s
            """,
            (cargo.start_date, employee_id, cargo.start_date, cargo.cargo_id[:10]),
        )
        
        cur.execute(
            """
            INSERT INTO CARGOSxEMPLEADO (id_Cargo, id_Empleado, cxe_Fecha_Inicio, cxe_Fecha_Fin, USER_ID, ESTADO_CxE)
            VALUES (%s, %s, %s, %s, %s, 'ACT')
            ON DUPLICATE KEY UPDATE cxe_Fecha_Fin = VALUES(cxe_Fecha_Fin), ESTADO_CxE = 'ACT'
            """,
            (cargo.cargo_id[:10], employee_id, cargo.start_date, cargo.end_date, user_id),
        )
        conn.commit()
        return {"mensaje": "Cargo asignado y registrado en el historial de crecimiento empresarial."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/empleados/{employee_id}/cargas")
def listar_cargas_empleado(employee_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(id_Carga) AS id,
                TRIM(car_Cedula) AS ci,
                CONCAT(TRIM(car_Nombre1), ' ', COALESCE(CONCAT(TRIM(car_Nombre2), ' '), ''), TRIM(car_Apellido1), ' ', COALESCE(TRIM(car_Apellido2), '')) AS name,
                TRIM(car_Nombre1) AS nombre1,
                COALESCE(TRIM(car_Nombre2), '') AS nombre2,
                TRIM(car_Apellido1) AS apellido1,
                COALESCE(TRIM(car_Apellido2), '') AS apellido2,
                COALESCE(TRIM(car_Sexo), 'M') AS sexo,
                car_FechaNacimiento AS fechaNacimiento,
                COALESCE(TRIM(car_Parentesco), 'Hijo/a') AS parentesco,
                COALESCE(TRIM(car_EstadoCivil), 'Soltero/a') AS estadoCivil,
                COALESCE(TRIM(car_Dependencia), 'Total') AS dependencia,
                TRIM(ESTADO_CAR) AS estado
            FROM CARGAS
            WHERE id_Empleado = %s AND (ESTADO_CAR = 'ACT' OR ESTADO_CAR IS NULL)
            ORDER BY car_Apellido1, car_Nombre1
            """,
            (employee_id,),
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/empleados/{employee_id}/cargas")
def registrar_carga_empleado(employee_id: str, carga: DependentInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)

        if carga.id_carga and carga.id_carga.strip():
            carga_id = carga.id_carga.strip()[:10]
        else:
            import re
            cur.execute("SELECT id_Carga FROM CARGAS")
            existing = cur.fetchall()
            max_num = 0
            for r in existing:
                val = str(r[0] if isinstance(r, (list, tuple)) else "")
                m = re.match(r"^CAR-(\d+)$", val, re.IGNORECASE)
                if m:
                    n = int(m.group(1))
                    if n > max_num:
                        max_num = n
            carga_id = f"CAR-{max_num + 1:06d}"

        # Validar duplicidad de cédula en cargas familiares activas
        cur.execute("SELECT id_Carga FROM CARGAS WHERE car_Cedula = %s AND (ESTADO_CAR = 'ACT' OR ESTADO_CAR IS NULL) LIMIT 1", (carga.cedula,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe una carga familiar activa registrada con la cédula {carga.cedula}.")

        cur.execute(
            """
            INSERT INTO CARGAS (
                id_Carga, id_Empleado, car_Cedula, car_Apellido1, car_Apellido2,
                car_Nombre1, car_Nombre2, car_Sexo, car_FechaNacimiento,
                car_Parentesco, car_EstadoCivil, car_Dependencia, USER_ID, ESTADO_CAR
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACT')
            """,
            (
                carga_id,
                employee_id,
                carga.cedula[:20],
                carga.apellido1[:30],
                carga.apellido2[:30] if carga.apellido2 else None,
                carga.nombre1[:30],
                carga.nombre2[:30] if carga.nombre2 else None,
                carga.gender[:1].upper() if carga.gender else 'M',
                carga.birth_date,
                carga.relationship[:20],
                carga.marital_status[:20],
                carga.dependency_type[:20],
                user_id,
            ),
        )
        conn.commit()
        return {"id": carga_id, "mensaje": f"Carga familiar {carga.nombre1} {carga.apellido1} registrada exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/empleados/{employee_id}/cargas/{carga_id}")
def actualizar_carga_empleado(employee_id: str, carga_id: str, carga: DependentInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)
        # Validar duplicidad de cédula en otras cargas familiares activas
        cur.execute("SELECT id_Carga FROM CARGAS WHERE car_Cedula = %s AND id_Carga <> %s AND (ESTADO_CAR = 'ACT' OR ESTADO_CAR IS NULL) LIMIT 1", (carga.cedula, carga_id))
        dupe_carga = cur.fetchone()
        if dupe_carga:
            raise HTTPException(status_code=409, detail=f"La cédula {carga.cedula} ya se encuentra registrada en otra carga familiar ({dupe_carga[0]}).")

        cur.execute(
            """
            UPDATE CARGAS
            SET car_Cedula = %s,
                car_Apellido1 = %s,
                car_Apellido2 = %s,
                car_Nombre1 = %s,
                car_Nombre2 = %s,
                car_Sexo = %s,
                car_FechaNacimiento = %s,
                car_Parentesco = %s,
                car_EstadoCivil = %s,
                car_Dependencia = %s,
                USER_ID = %s
            WHERE id_Carga = %s AND id_Empleado = %s
            """,
            (
                carga.cedula[:20],
                carga.apellido1[:30],
                carga.apellido2[:30] if carga.apellido2 else None,
                carga.nombre1[:30],
                carga.nombre2[:30] if carga.nombre2 else None,
                carga.gender[:1].upper() if carga.gender else 'M',
                carga.birth_date,
                carga.relationship[:20],
                carga.marital_status[:20],
                carga.dependency_type[:20],
                user_id,
                carga_id,
                employee_id,
            ),
        )
        conn.commit()
        return {"id": carga_id, "mensaje": f"Carga familiar {carga.nombre1} {carga.apellido1} actualizada exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.delete("/api/empleados/{employee_id}/cargas/{carga_id}")
def eliminar_carga_empleado(employee_id: str, carga_id: str):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("UPDATE CARGAS SET ESTADO_CAR = 'INA' WHERE id_Carga = %s AND id_Empleado = %s", (carga_id, employee_id))
        conn.commit()
        return {"id": carga_id, "mensaje": "Carga familiar removida."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/nomina/bonificaciones")
def listar_bonificaciones():
    return _listar_catalogo_nomina("bonificaciones")


@app.get("/api/nomina/descuentos")
def listar_descuentos():
    return _listar_catalogo_nomina("descuentos")


PAYROLL_CATALOG_CONFIG = {
    "bonificaciones": ("BONIFICACIONES", "id_Bonificacion", "bon_Descripcion", "bon_Valor", "ESTADO_BON", "BON"),
    "descuentos": ("DESCUENTOS", "id_Descuento", "des_Descripcion", "des_Valor", "ESTADO_DES", "DES"),
}


def _listar_catalogo_nomina(tipo: str):
    table, id_column, name_column, value_column, status_column, _ = PAYROLL_CATALOG_CONFIG[tipo]
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT TRIM({id_column}) AS id, TRIM({name_column}) AS nombre, "
            f"{value_column} AS valor, COALESCE(TRIM({status_column}), 'ACT') AS estado "
            f"FROM {table} ORDER BY {name_column}"
        )
        rows = cur.fetchall()
        if not rows:
            default_rows = {
                "bonificaciones": [
                    ("BON-000001", "Horas Extras 50%", 25.00, "ACT"),
                    ("BON-000002", "Horas Extras 100%", 45.00, "ACT"),
                    ("BON-000003", "Bono Puntualidad y Asistencia", 30.00, "ACT"),
                    ("BON-000004", "Comisión por Cumplimiento de Ventas", 50.00, "ACT"),
                    ("BON-000005", "Bono de Responsabilidad y Desempeño", 60.00, "ACT"),
                    ("BON-000006", "Subsidio de Alimentación / Transporte", 40.00, "ACT"),
                ],
                "descuentos": [
                    ("DES-000001", "Aporte Individual IESS (9.45%)", 0.00, "ACT"),
                    ("DES-000002", "Préstamo Quirografario BIESS", 50.00, "ACT"),
                    ("DES-000003", "Préstamo Hipotecario BIESS", 120.00, "ACT"),
                    ("DES-000004", "Anticipo Quincenal de Sueldo", 100.00, "ACT"),
                    ("DES-000005", "Atrasos y Multas Disciplinarias", 15.00, "ACT"),
                    ("DES-000006", "Retención Judicial / Pensión Alimenticia", 80.00, "ACT"),
                ],
            }[tipo]
            cur.executemany(
                f"INSERT IGNORE INTO {table} ({id_column}, {name_column}, {value_column}, {status_column}) "
                "VALUES (%s, %s, %s, %s)",
                default_rows,
            )
            conn.commit()
            cur.execute(
                f"SELECT TRIM({id_column}) AS id, TRIM({name_column}) AS nombre, "
                f"{value_column} AS valor, COALESCE(TRIM({status_column}), 'ACT') AS estado "
                f"FROM {table} ORDER BY {name_column}"
            )
            rows = cur.fetchall()
        return rows
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


def _crear_catalogo_nomina(tipo: str, data: PayrollCatalogInput):
    table, id_column, name_column, value_column, status_column, prefix = PAYROLL_CATALOG_CONFIG[tipo]
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM {table} WHERE LOWER(TRIM({name_column})) = LOWER(%s) LIMIT 1", (data.name,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe un concepto con el nombre '{data.name}'.")
        cur.execute(
            f"SELECT COALESCE(MAX(CAST(SUBSTRING({id_column}, 5) AS UNSIGNED)), 0) "
            f"FROM {table} WHERE {id_column} LIKE %s",
            (f"{prefix}-%",),
        )
        next_number = int(cur.fetchone()[0] or 0) + 1
        catalog_id = f"{prefix}-{next_number:06d}"
        cur.execute(
            f"INSERT INTO {table} ({id_column}, {name_column}, {value_column}, {status_column}) "
            "VALUES (%s, %s, %s, %s)",
            (catalog_id, data.name, data.amount, data.status),
        )
        conn.commit()
        return {"id": catalog_id, "mensaje": f"Concepto '{data.name}' creado correctamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


def _actualizar_catalogo_nomina(tipo: str, catalog_id: str, data: PayrollCatalogInput):
    table, id_column, name_column, value_column, status_column, _ = PAYROLL_CATALOG_CONFIG[tipo]
    clean_id = catalog_id.strip().upper()
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM {table} WHERE {id_column} = %s", (clean_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"No se encontró el concepto '{clean_id}'.")
        cur.execute(
            f"SELECT 1 FROM {table} WHERE LOWER(TRIM({name_column})) = LOWER(%s) "
            f"AND {id_column} <> %s LIMIT 1",
            (data.name, clean_id),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe otro concepto con el nombre '{data.name}'.")
        cur.execute(
            f"UPDATE {table} SET {name_column} = %s, {value_column} = %s, {status_column} = %s "
            f"WHERE {id_column} = %s",
            (data.name, data.amount, data.status, clean_id),
        )
        conn.commit()
        return {"id": clean_id, "mensaje": f"Concepto '{clean_id}' actualizado correctamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


def _eliminar_catalogo_nomina(tipo: str, catalog_id: str):
    table, id_column, _, _, status_column, _ = PAYROLL_CATALOG_CONFIG[tipo]
    clean_id = catalog_id.strip().upper()
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM {table} WHERE {id_column} = %s", (clean_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"No se encontró el concepto '{clean_id}'.")
        cur.execute(f"UPDATE {table} SET {status_column} = 'INA' WHERE {id_column} = %s", (clean_id,))
        conn.commit()
        return {"id": clean_id, "mensaje": f"Concepto '{clean_id}' desactivado correctamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/nomina/bonificaciones")
def crear_bonificacion(data: PayrollCatalogInput):
    return _crear_catalogo_nomina("bonificaciones", data)


@app.put("/api/nomina/bonificaciones/{catalog_id}")
def actualizar_bonificacion(catalog_id: str, data: PayrollCatalogInput):
    return _actualizar_catalogo_nomina("bonificaciones", catalog_id, data)


@app.delete("/api/nomina/bonificaciones/{catalog_id}")
def eliminar_bonificacion(catalog_id: str):
    return _eliminar_catalogo_nomina("bonificaciones", catalog_id)


@app.post("/api/nomina/descuentos")
def crear_descuento(data: PayrollCatalogInput):
    return _crear_catalogo_nomina("descuentos", data)


@app.put("/api/nomina/descuentos/{catalog_id}")
def actualizar_descuento(catalog_id: str, data: PayrollCatalogInput):
    return _actualizar_catalogo_nomina("descuentos", catalog_id, data)


@app.delete("/api/nomina/descuentos/{catalog_id}")
def eliminar_descuento(catalog_id: str):
    return _eliminar_catalogo_nomina("descuentos", catalog_id)


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
                P.pag_Descripcion AS description,
                P.pag_Fecha_Inicio AS startDate,
                P.pag_Fecha_Fin AS endDate,
                P.pag_Fecha_Fin AS date,
                TRIM(D.id_Empleado) AS employeeId,
                CONCAT(TRIM(E.emp_Nombre1), ' ', TRIM(E.emp_Apellido1)) AS employeeName,
                COALESCE(TRIM(DEP.dep_Nombre), 'General') AS department,
                D.pxe_Sueldo AS baseSalary,
                D.pxe_Bonificaciones AS bonus,
                D.pxe_Descuentos AS deductions,
                D.pxe_Valor_Neto AS amount,
                P.ESTADO_PAG AS status
            FROM PAGOS P
            INNER JOIN PAGxEMP D ON P.id_Pago = D.id_Pago
            INNER JOIN EMPLEADOS E ON D.id_Empleado = E.id_Empleado
            LEFT JOIN DEPARTAMENTOS DEP ON E.id_Departamento = DEP.id_Departamento
            ORDER BY P.pag_Fecha_Fin DESC, P.id_Pago DESC
            """
        )
        payrolls = cur.fetchall()

        cur.execute(
            """
            SELECT 
                TRIM(BXP.id_Pago) AS pagoId,
                TRIM(BXP.id_Bonificacion) AS bonusId,
                TRIM(B.bon_Descripcion) AS bonusName,
                BXP.bxe_Fecha AS date,
                BXP.bxe_Valor AS amount
            FROM BONxEMPxPAG BXP
            INNER JOIN BONIFICACIONES B ON BXP.id_Bonificacion = B.id_Bonificacion
            ORDER BY BXP.id_Pago, BXP.bxe_Fecha
            """
        )
        bonuses_by_pay: dict[str, list[dict[str, object]]] = {}
        for row in cur.fetchall():
            pid = row.pop("pagoId")
            bonuses_by_pay.setdefault(pid, []).append(row)

        cur.execute(
            """
            SELECT 
                TRIM(DXP.id_Pago) AS pagoId,
                TRIM(DXP.id_Descuento) AS deductionId,
                TRIM(D.des_Descripcion) AS deductionName,
                DXP.dxe_Fecha AS date,
                DXP.dxe_Valor AS amount
            FROM DESxEMPxPAG DXP
            INNER JOIN DESCUENTOS D ON DXP.id_Descuento = D.id_Descuento
            ORDER BY DXP.id_Pago, DXP.dxe_Fecha
            """
        )
        deductions_by_pay: dict[str, list[dict[str, object]]] = {}
        for row in cur.fetchall():
            pid = row.pop("pagoId")
            deductions_by_pay.setdefault(pid, []).append(row)

        for p in payrolls:
            p["bonusLines"] = bonuses_by_pay.get(p["id"], [])
            p["deductionLines"] = deductions_by_pay.get(p["id"], [])

        return payrolls
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/nomina")
def crear_rol_pago(payroll: PayrollInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        user_id = get_user_id(cur)

        import re
        cur.execute("SELECT id_Pago FROM PAGOS")
        existing = cur.fetchall()
        max_num = 0
        for r in existing:
            val = str(r[0] if isinstance(r, (list, tuple)) else "")
            m = re.match(r"^PAG-(\d+)$", val, re.IGNORECASE)
            if m:
                n = int(m.group(1))
                if n > max_num:
                    max_num = n
        pago_id = f"PAG-{max_num + 1:06d}"

        # Totales calculados con precisión
        if payroll.bonus_lines:
            total_bonos = sum((line.amount for line in payroll.bonus_lines), Decimal("0"))
        else:
            total_bonos = payroll.bonus

        if payroll.deduction_lines:
            total_descuentos = sum((line.amount for line in payroll.deduction_lines), Decimal("0"))
        else:
            total_descuentos = payroll.deductions

        if payroll.start_date > payroll.end_date:
            raise HTTPException(status_code=422, detail="La fecha de inicio del rol no puede ser posterior a la fecha de fin.")

        cur.execute("SELECT id_Empleado, ESTADO_EMP FROM EMPLEADOS WHERE id_Empleado = %s LIMIT 1", (payroll.employee_id,))
        emp_exists = cur.fetchone()
        if not emp_exists:
            raise HTTPException(status_code=404, detail=f"No se encontró el colaborador con código {payroll.employee_id}.")

        neto = (payroll.base_salary + total_bonos - total_descuentos).quantize(CENT, rounding=ROUND_HALF_UP)
        if neto < Decimal("0.00"):
            raise HTTPException(status_code=422, detail="El valor neto a pagar no puede ser negativo. Los descuentos superan los ingresos del colaborador.")

        try:
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
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                cur.execute(
                    """
                    INSERT INTO PAGOS (id_Pago, pag_Descripcion, pag_Fecha_Inicio, pag_Fecha_Fin, USER_ID, ESTADO_PAG)
                    VALUES (%s, %s, %s, %s, %s, 'ABI')
                    """,
                    (pago_id, payroll.description[:40], payroll.start_date, payroll.end_date, user_id),
                )
            else:
                raise

        cur.execute(
            """
            INSERT INTO PAGxEMP (id_Pago, id_Empleado, pxe_Sueldo, pxe_Bonificaciones, pxe_Descuentos, pxe_Valor_Neto, ESTADO_PxE)
            VALUES (%s, %s, %s, %s, %s, %s, 'ABI')
            """,
            (
                pago_id,
                payroll.employee_id,
                payroll.base_salary,
                total_bonos,
                total_descuentos,
                neto,
            ),
        )

        for line in payroll.bonus_lines:
            cur.execute(
                """
                INSERT INTO BONxEMPxPAG (id_Pago, id_Empleado, id_Bonificacion, bxe_Fecha, bxe_Valor, ESTADO_BXE)
                VALUES (%s, %s, %s, %s, %s, 'ACT')
                """,
                (
                    pago_id,
                    payroll.employee_id,
                    line.bonus_id[:10],
                    line.line_date or payroll.end_date,
                    line.amount,
                ),
            )

        for line in payroll.deduction_lines:
            cur.execute(
                """
                INSERT INTO DESxEMPxPAG (id_Pago, id_Empleado, id_Descuento, dxe_Fecha, dxe_Valor, ESTADO_DXE)
                VALUES (%s, %s, %s, %s, %s, 'ACT')
                """,
                (
                    pago_id,
                    payroll.employee_id,
                    line.deduction_id[:10],
                    line.line_date or payroll.end_date,
                    line.amount,
                ),
            )

        conn.commit()
        return {
            "id": pago_id,
            "estado": "ABI",
            "neto": str(neto),
            "mensaje": f"Rol de pago {pago_id} generado correctamente.",
        }
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
        try:
            cur.callproc("SP_PAGO_APROBAR", (pago_id, user_id))
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                cur.execute("UPDATE PAGOS SET ESTADO_PAG = 'APR' WHERE id_Pago = %s", (pago_id,))
                cur.execute("UPDATE PAGxEMP SET ESTADO_PxE = 'APR' WHERE id_Pago = %s", (pago_id,))
            else:
                raise
        conn.commit()
        return {"id": pago_id, "estado": "APR", "mensaje": "Rol de pago aprobado exitosamente."}
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
        try:
            cur.callproc("SP_PAGO_ANULAR", (pago_id, user_id))
        except mysql.connector.Error as proc_err:
            if proc_err.errno in {1305, 1452}:
                cur.execute("UPDATE PAGOS SET ESTADO_PAG = 'ANU' WHERE id_Pago = %s", (pago_id,))
                cur.execute("UPDATE PAGxEMP SET ESTADO_PxE = 'ANU' WHERE id_Pago = %s", (pago_id,))
            else:
                raise
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

@app.get("/api/contabilidad/bancos")
def listar_bancos():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(id_Banco) AS id,
                TRIM(ban_Nombre) AS nombre,
                COALESCE(ESTADO_BAN, 'ACT') AS estado
            FROM BANCOS
            ORDER BY id_Banco
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/contabilidad/bancos")
def crear_banco(banco: BancoInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        banco_id = banco.id.strip().upper() if banco.id and banco.id.strip() else ""
        if not banco_id:
            cur.execute("SELECT MAX(CAST(SUBSTRING(id_Banco, 5) AS UNSIGNED)) FROM BANCOS WHERE id_Banco LIKE 'BAN-%'")
            row = cur.fetchone()
            seq = (row[0] or 0) + 1 if row else 1
            banco_id = f"BAN-{seq:06d}"
        if len(banco_id) > 10 or not re.match(r"^[A-Z0-9-]+$", banco_id):
            raise HTTPException(status_code=422, detail="El código del banco no es válido.")

        cur.execute("SELECT id_Banco FROM BANCOS WHERE id_Banco = %s LIMIT 1", (banco_id,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe un banco con el código {banco_id}.")

        # Validar duplicidad de nombre de banco
        cur.execute("SELECT id_Banco FROM BANCOS WHERE LOWER(TRIM(ban_Nombre)) = LOWER(%s) LIMIT 1", (banco.name.strip(),))
        existing_ban = cur.fetchone()
        if existing_ban:
            raise HTTPException(status_code=409, detail=f"Ya existe una entidad bancaria registrada con el nombre '{banco.name.strip()}'.")

        cur.execute(
            """
            INSERT INTO BANCOS (id_Banco, ban_Nombre, ESTADO_BAN)
            VALUES (%s, %s, %s)
            """,
            (banco_id, banco.name[:50].strip(), (banco.status[:3].upper() if banco.status else 'ACT'))
        )
        conn.commit()
        return {"id": banco_id, "mensaje": f"Banco '{banco.name}' registrado exitosamente con código {banco_id}."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/contabilidad/bancos/{banco_id}")
def actualizar_banco(banco_id: str, banco: BancoInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE BANCOS 
            SET ban_Nombre = %s, ESTADO_BAN = %s
            WHERE id_Banco = %s
            """,
            (banco.name[:50].strip(), (banco.status[:3].upper() if banco.status else 'ACT'), banco_id.strip())
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"No se encontró el banco con código {banco_id}.")
        conn.commit()
        return {"id": banco_id, "mensaje": f"Banco {banco_id} actualizado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/contabilidad/centros-costos")
def listar_centros_costos():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                TRIM(CC.id_CentroCosto) AS id,
                TRIM(CC.id_Departamento) AS idDepartamento,
                TRIM(COALESCE(D.dep_Nombre, 'General')) AS departamento,
                TRIM(CC.cco_Nombre) AS nombre,
                CC.cco_PresupuestoMensual AS presupuestoMensual,
                COALESCE(CC.ESTADO_CCO, 'ACT') AS estado
            FROM CENTROS_COSTOS CC
            LEFT JOIN DEPARTAMENTOS D ON CC.id_Departamento = D.id_Departamento
            ORDER BY CC.id_CentroCosto
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/contabilidad/centros-costos")
def crear_centro_costo(cco: CentroCostoInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cco_id = cco.id.strip().upper() if cco.id and cco.id.strip() else ""
        if not cco_id:
            cur.execute("SELECT MAX(CAST(SUBSTRING(id_CentroCosto, 5) AS UNSIGNED)) FROM CENTROS_COSTOS WHERE id_CentroCosto LIKE 'CCO-%'")
            row = cur.fetchone()
            seq = (row[0] or 0) + 1 if row else 1
            cco_id = f"CCO-{seq:06d}"

        dep_id = cco.department_id.strip()[:10]
        cur.execute("SELECT id_Departamento FROM DEPARTAMENTOS WHERE id_Departamento = %s", (dep_id,))
        if not cur.fetchone():
            cur.execute("INSERT IGNORE INTO DEPARTAMENTOS (id_Departamento, dep_Nombre, ESTADO_DEP) VALUES (%s, 'General', 'ACT')", (dep_id,))

        # Validar duplicidad de nombre de centro de costo en el departamento
        cur.execute("SELECT id_CentroCosto FROM CENTROS_COSTOS WHERE LOWER(TRIM(cco_Nombre)) = LOWER(%s) AND id_Departamento = %s LIMIT 1", (cco.name.strip(), dep_id))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Ya existe un centro de costo con el nombre '{cco.name.strip()}' en este departamento.")

        cur.execute(
            """
            INSERT INTO CENTROS_COSTOS (id_CentroCosto, id_Departamento, cco_Nombre, cco_PresupuestoMensual, ESTADO_CCO)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                id_Departamento = VALUES(id_Departamento),
                cco_Nombre = VALUES(cco_Nombre),
                cco_PresupuestoMensual = VALUES(cco_PresupuestoMensual),
                ESTADO_CCO = VALUES(ESTADO_CCO)
            """,
            (
                cco_id[:10],
                dep_id,
                cco.name[:50].strip(),
                cco.monthly_budget,
                (cco.status[:3].upper() if cco.status else 'ACT')
            )
        )
        conn.commit()
        return {"id": cco_id, "mensaje": f"Centro de Costo '{cco.name}' registrado exitosamente con código {cco_id}."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/contabilidad/centros-costos/{cco_id}")
def actualizar_centro_costo(cco_id: str, cco: CentroCostoInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        dep_id = cco.department_id.strip()[:10]
        cur.execute("SELECT id_Departamento FROM DEPARTAMENTOS WHERE id_Departamento = %s", (dep_id,))
        if not cur.fetchone():
            cur.execute("INSERT IGNORE INTO DEPARTAMENTOS (id_Departamento, dep_Nombre, ESTADO_DEP) VALUES (%s, 'General', 'ACT')", (dep_id,))

        cur.execute(
            """
            UPDATE CENTROS_COSTOS
            SET id_Departamento = %s,
                cco_Nombre = %s,
                cco_PresupuestoMensual = %s,
                ESTADO_CCO = %s
            WHERE id_CentroCosto = %s
            """,
            (
                dep_id,
                cco.name[:50].strip(),
                cco.monthly_budget,
                (cco.status[:3].upper() if cco.status else 'ACT'),
                cco_id.strip()
            )
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"No se encontró el Centro de Costo con código {cco_id}.")
        conn.commit()
        return {"id": cco_id, "mensaje": f"Centro de Costo {cco_id} actualizado exitosamente."}
    except mysql.connector.Error as error:
        if conn: conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/contabilidad/cuentas")
def listar_cuentas():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("INSERT IGNORE INTO TIPO_CUENTA (id_Tipo_Cta, tip_Descripcion) VALUES ('MAY', 'Mayor'), ('DET', 'Detalle')")
        conn.commit()
        cur.execute(
            """
            SELECT 
                TRIM(C.id_Cuenta) AS id,
                TRIM(C.id_Cuenta) AS code,
                TRIM(C.cue_Descripcion) AS name,
                TRIM(C.cue_Tipo) AS type,
                CASE 
                    WHEN TRIM(C.cue_Tipo) = 'MAY' THEN 'MAYOR'
                    WHEN TRIM(C.cue_Tipo) = 'DET' THEN 'DETALLE'
                    ELSE TRIM(C.cue_Tipo)
                END AS accountTypeLabel,
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
    acc_type = (acc.type or "DET").strip().upper()
    if acc_type not in ("MAY", "DET"):
        raise HTTPException(
            status_code=422,
            detail="El tipo de cuenta debe ser únicamente 'MAY' (Cuenta de Mayor) o 'DET' (Cuenta de Detalle)."
        )

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute("INSERT IGNORE INTO TIPO_CUENTA (id_Tipo_Cta, tip_Descripcion) VALUES ('MAY', 'Mayor'), ('DET', 'Detalle')")
        cur.execute(
            """
            INSERT INTO CUENTAS (id_Cuenta, cue_Descripcion, cue_Tipo, cue_DEBE00, cue_HABER00, ESTADO_CUE)
            VALUES (%s, %s, %s, 0, 0, 'ACT')
            ON DUPLICATE KEY UPDATE 
                cue_Descripcion = VALUES(cue_Descripcion),
                cue_Tipo = VALUES(cue_Tipo)
            """,
            (acc.id[:15], acc.name[:60], acc_type),
        )
        conn.commit()
        tipo_lbl = "MAYOR" if acc_type == "MAY" else "DETALLE"
        return {"id": acc.id, "mensaje": f"Cuenta {acc.id} registrada exitosamente como tipo {tipo_lbl}."}
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
    if total_debe <= Decimal("0"):
        raise HTTPException(status_code=422, detail="El valor total del asiento debe ser un monto positivo mayor a cero.")
    if total_debe != total_haber:
        raise HTTPException(status_code=422, detail="El asiento debe estar cuadrado (Debe == Haber).")
    for idx, line in enumerate(entry.lines, 1):
        if line.debit == Decimal("0") and line.credit == Decimal("0"):
            raise HTTPException(status_code=422, detail=f"Línea #{idx}: Debe ingresar un valor en el Debe o en el Haber.")
        if line.debit > Decimal("0") and line.credit > Decimal("0"):
            raise HTTPException(status_code=422, detail=f"Línea #{idx}: Una línea no puede tener importes simultáneos en Debe y Haber.")

    asiento_id = f"ASI{uuid4().hex[:7].upper()}"
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()

        # Validación vital: ninguna cuenta del asiento puede ser de tipo MAYOR
        acc_ids = [line.account_id.strip() for line in entry.lines]
        if acc_ids:
            format_strings = ','.join(['%s'] * len(acc_ids))
            cur.execute(
                f"SELECT TRIM(id_Cuenta), TRIM(cue_Tipo), TRIM(cue_Descripcion) FROM CUENTAS WHERE id_Cuenta IN ({format_strings})",
                tuple(acc_ids)
            )
            found_accounts = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
            for line in entry.lines:
                acc_clean = line.account_id.strip()
                acc_info = found_accounts.get(acc_clean)
                if acc_info and acc_info[0] == 'MAY':
                    raise HTTPException(
                        status_code=422,
                        detail=f"Validación contable: No se permite realizar asientos en cuentas de MAYOR. La cuenta '{acc_clean}' ({acc_info[1]}) es de MAYOR. Utilice cuentas de DETALLE (DET)."
                    )

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

        # Si se especificó una fecha de transacción manual, actualizar el TIMESTAMP en ASIENTOS
        if entry.entry_date:
            date_val = str(entry.entry_date).strip()
            if len(date_val) == 10:
                date_val = f"{date_val} 12:00:00"
            cur.execute(
                "UPDATE ASIENTOS SET asi_FechaHora = %s WHERE id_Asiento = %s",
                (date_val, asiento_id)
            )

        for line in entry.lines:
            cur.execute(
                """
                INSERT INTO CTAxASI (id_Asiento, id_Cuenta, cxa_Debe, cxa_Haber, ESTADO_CXA)
                VALUES (%s, %s, %s, %s, 'ABI')
                """,
                (asiento_id, line.account_id.strip(), line.debit, line.credit),
            )
        conn.commit()
        return {"id": asiento_id, "estado": "ABI", "mensaje": "Asiento contable registrado exitosamente."}
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

# ==========================================
# 11. AUTENTICACIÓN, ROLES Y CONTROL DE ACCESO (RBAC)
# ==========================================

PASSWORD_SALT = "licoreria_salt_"
PASSWORD_HASH_ITERATIONS = 310_000
AUTH_TOKEN_TTL_SECONDS = 8 * 60 * 60
configured_token_secret = os.getenv("AUTH_TOKEN_SECRET", "").strip()
if configured_token_secret.startswith("replace-with-"):
    configured_token_secret = ""
AUTH_TOKEN_SECRET = configured_token_secret.encode("utf-8") or secrets.token_bytes(32)
bearer_scheme = HTTPBearer(auto_error=False)

def hash_password(raw_password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", raw_password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_HASH_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )

def verify_password(raw_password: str, stored_hash: str) -> bool:
    if not stored_hash or not raw_password:
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_text, digest_text = stored_hash.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
            actual = hashlib.pbkdf2_hmac(
                "sha256", raw_password.encode("utf-8"), salt, int(iterations)
            )
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    # Legacy SHA-256 hashes are accepted so existing accounts can continue to log in.
    if hmac.compare_digest(
        hashlib.sha256(f"{PASSWORD_SALT}{raw_password}".encode("utf-8")).hexdigest(),
        stored_hash,
    ):
        return True
    return hmac.compare_digest(
        hashlib.sha256(raw_password.encode("utf-8")).hexdigest(), stored_hash
    )


def create_auth_token(user_id: str) -> str:
    expires_at = int(time.time()) + AUTH_TOKEN_TTL_SECONDS
    payload = base64.urlsafe_b64encode(
        f"{user_id}:{expires_at}".encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        AUTH_TOKEN_SECRET, payload.encode("ascii"), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload}.{encoded_signature}"


class InitialAdminEmployeeInput(EmployeeInput):
    salary: Decimal = Field(default=Decimal("480.00"), alias="sueldo")


class InitialAdminSetupInput(BaseModel):
    employee: InitialAdminEmployeeInput
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)

    @field_validator("username")
    @classmethod
    def validar_username(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,50}", clean):
            raise ValueError("El nombre de usuario contiene caracteres no permitidos.")
        return clean


@app.get("/api/auth/setup-status")
def estado_configuracion_inicial():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT EXISTS(SELECT 1 FROM USUARIOS LIMIT 1) AS initialized")
        return {"initialized": bool(cur.fetchone()["initialized"])}
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


@app.post("/api/auth/setup", status_code=201)
def configurar_administrador_inicial(payload: InitialAdminSetupInput):
    conn, cur = None, None
    setup_lock_acquired = False
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT GET_LOCK('licoreria_initial_admin_setup', 10) AS acquired")
        setup_lock_acquired = cur.fetchone()["acquired"] == 1
        if not setup_lock_acquired:
            raise HTTPException(
                status_code=503,
                detail="No se pudo iniciar la configuración. Intenta nuevamente.",
            )

        cur.execute("SELECT 1 FROM USUARIOS LIMIT 1")
        if cur.fetchone():
            raise HTTPException(
                status_code=409,
                detail="El sistema ya tiene usuarios. La configuración inicial está cerrada.",
            )

        employee = payload.employee
        cur.execute(
            """
            SELECT id_Departamento
            FROM DEPARTAMENTOS
            WHERE id_Departamento = %s AND (ESTADO_DEP = 'ACT' OR ESTADO_DEP IS NULL)
            LIMIT 1
            """,
            (employee.department_id,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Selecciona un departamento activo.")

        cur.execute("SELECT 1 FROM EMPLEADOS WHERE emp_Cedula = %s LIMIT 1", (employee.ci,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Ya existe un empleado con esa cédula.")
        cur.execute(
            "SELECT 1 FROM USUARIOS WHERE usr_Username = %s LIMIT 1",
            (payload.username,),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="El nombre de usuario ya está en uso.")

        cur.execute("SELECT id_Empleado FROM EMPLEADOS")
        employee_ids = cur.fetchall()
        highest_employee_number = 0
        for row in employee_ids:
            match = re.fullmatch(r"EMP-(\d+)", str(row["id_Empleado"]).strip(), re.IGNORECASE)
            if match:
                highest_employee_number = max(highest_employee_number, int(match.group(1)))
        employee_id = f"EMP-{highest_employee_number + 1:06d}"
        if len(employee_id) > 10:
            raise HTTPException(status_code=409, detail="No hay espacio para generar otro código de empleado.")

        user_id = f"USR-{uuid4().hex[:12].upper()}"
        cur.execute(
            """
            SELECT id_Rol
            FROM ROLES
            WHERE LOWER(TRIM(rol_Nombre)) IN ('admin', 'administrador', 'superadministrador')
              AND (ESTADO_ROL = 'ACT' OR ESTADO_ROL IS NULL)
            ORDER BY id_Rol
            LIMIT 1
            """
        )
        admin_role = cur.fetchone()
        if admin_role:
            role_id = str(admin_role["id_Rol"]).strip()
        else:
            cur.execute("SELECT id_Rol FROM ROLES WHERE id_Rol = 'ROL-ADMIN' LIMIT 1")
            role_conflict = cur.fetchone()
            if role_conflict:
                raise HTTPException(
                    status_code=409,
                    detail="El identificador reservado para el rol administrador ya está ocupado.",
                )
            role_id = "ROL-ADMIN"
            cur.execute(
                """
                INSERT INTO ROLES (id_Rol, rol_Nombre, rol_Descripcion, ESTADO_ROL)
                VALUES (%s, 'Administrador', 'Acceso administrativo inicial', 'ACT')
                """,
                (role_id,),
            )

        cur.execute(
            """
            INSERT INTO EMPLEADOS (
                id_Empleado, id_Departamento, emp_Cedula, emp_Apellido1, emp_Apellido2,
                emp_Nombre1, emp_Nombre2, emp_Sexo, emp_FechaNacimiento, emp_Sueldo,
                emp_Direccion, emp_Telefono, emp_Celular, emp_Mail, USER_ID, ESTADO_EMP
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACT')
            """,
            (
                employee_id,
                employee.department_id,
                employee.ci,
                employee.last_name1,
                employee.last_name2,
                employee.first_name,
                employee.second_name,
                employee.gender,
                employee.birth_date,
                employee.salary,
                employee.address,
                employee.phone,
                employee.mobile,
                employee.email,
                user_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO USUARIOS
                (id_Usuario, id_Empleado, usr_Username, usr_PasswordHash, ESTADO_USR)
            VALUES (%s, %s, %s, %s, 'ACT')
            """,
            (user_id, employee_id, payload.username, hash_password(payload.password)),
        )
        cur.execute(
            "INSERT INTO USUARIOSxROLES (id_Usuario, id_Rol, ESTADO_UxR) VALUES (%s, %s, 'ACT')",
            (user_id, role_id),
        )
        cur.execute(
            """
            INSERT INTO LOG_AUDITORIA
                (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada,
                 log_Accion, log_ValorAnterior, log_ValorNuevo)
            VALUES (%s, %s, NOW(), 'USUARIOS', 'INSERT', NULL, %s)
            """,
            (
                f"LOG-{uuid4().hex[:10].upper()}",
                user_id,
                f"Administrador inicial creado: {payload.username}",
            ),
        )
        conn.commit()
        return {
            "idEmpleado": employee_id,
            "idUsuario": user_id,
            "mensaje": "Empleado y administrador inicial creados. Ya puedes iniciar sesión.",
        }
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if setup_lock_acquired and cur:
            cur.execute("SELECT RELEASE_LOCK('licoreria_initial_admin_setup')")
            cur.fetchone()
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Debes iniciar sesión para continuar.")
    try:
        payload, encoded_signature = credentials.credentials.split(".", 1)
        expected_signature = hmac.new(
            AUTH_TOKEN_SECRET, payload.encode("ascii"), hashlib.sha256
        ).digest()
        supplied_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError("Firma inválida.")
        decoded_payload = base64.urlsafe_b64decode(
            payload + "=" * (-len(payload) % 4)
        ).decode("utf-8")
        user_id, expires_at = decoded_payload.rsplit(":", 1)
        if int(expires_at) <= int(time.time()):
            raise ValueError("Token expirado.")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="La sesión no es válida o expiró.")

    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM USUARIOS WHERE id_Usuario = %s AND ESTADO_USR = 'ACT' LIMIT 1",
            (user_id,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=401, detail="La sesión ya no está activa.")
        return user_id
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


def require_user_manager(user_id: str = Depends(get_authenticated_user)) -> str:
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM USUARIOSxROLES ur
            JOIN ROLES r ON r.id_Rol = ur.id_Rol
            WHERE ur.id_Usuario = %s
              AND ur.ESTADO_UxR = 'ACT'
              AND r.ESTADO_ROL = 'ACT'
              AND (
                  LOWER(r.rol_Nombre) IN ('admin', 'administrador', 'superadministrador')
                  OR LOWER(r.rol_Nombre) = 'jefe_talento_humano'
                  OR EXISTS (
                      SELECT 1
                      FROM ROLESxPERMISOS rp
                      JOIN PERMISOS p ON p.id_Permiso = rp.id_Permiso
                      WHERE rp.id_Rol = r.id_Rol
                        AND rp.ESTADO_RxP = 'ACT'
                        AND p.ESTADO_PRM = 'ACT'
                        AND p.id_Permiso = 'PRM-USU'
                  )
              )
            LIMIT 1
            """,
            (user_id,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="No tienes permiso para administrar usuarios.")
        return user_id
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


def require_administrator(user_id: str = Depends(get_authenticated_user)) -> str:
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM USUARIOSxROLES ur
            JOIN ROLES r ON r.id_Rol = ur.id_Rol
            WHERE ur.id_Usuario = %s
              AND ur.ESTADO_UxR = 'ACT'
              AND r.ESTADO_ROL = 'ACT'
              AND (
                  r.id_Rol = 'ROL-ADMIN'
                  OR LOWER(TRIM(r.rol_Nombre)) IN ('admin', 'administrador', 'superadministrador')
              )
            LIMIT 1
            """,
            (user_id,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="No tienes permiso para consultar la auditoría.")
        return user_id
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


@app.get("/api/auditoria")
def listar_auditoria(_: str = Depends(require_administrator)):
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
            LIMIT 100
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


PERMISSION_TO_ROUTES_MAP = {
    "PRM-DASH": ["dashboard"],
    "PRM-POS": ["pos"],
    "PRM-FAC": ["sales"],
    "PRM-CLI": ["customers"],
    "PRM-AJU": ["adjustments"],
    "PRM-REC": ["receptions"],
    "PRM-ENT": ["deliveries"],
    "PRM-COM": ["pos_orders"],
    "PRM-PRV": ["suppliers"],
    "PRM-PRD": ["products", "catalog"],
    "PRM-MED": ["units"],
    "PRM-EMP": ["employees", "hr"],
    "PRM-NOM": ["payroll"],
    "PRM-CON": ["accounting"],
    "PRM-BAN": ["bancos"],
    "PRM-CCO": ["cost_centers"],
    "PRM-REP": ["reports"],
}

ALL_FRONTEND_ROUTES = [
    "dashboard", "pos", "sales", "customers", "adjustments",
    "receptions", "deliveries", "pos_orders", "suppliers",
    "products", "units", "employees", "payroll", "audit",
    "accounting", "bancos", "cost_centers", "reports", "usuarios"
]

def puede_administrar_usuarios(role_names: list[str], permission_ids: list[str]) -> bool:
    return "PRM-USU" in permission_ids or any(
        role.strip().lower() in {"admin", "administrador", "superadministrador", "jefe_talento_humano"}
        for role in role_names
    )


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=3, max_length=100)

    @field_validator("username")
    @classmethod
    def validar_username(cls, v: str) -> str:
        clean = str(v or "").strip()
        if not clean or RE_SQLI_DANGEROUS.search(clean) or not re.match(r"^[A-Za-z0-9_\-\.@]+$", clean):
            raise ValueError("El nombre de usuario contiene caracteres no permitidos.")
        return clean

class LogoutInput(BaseModel):
    user_id: str | None = Field(default=None, alias="userId")
    username: str | None = Field(default=None, alias="username")

@app.post("/api/auth/login")
def login_usuario(payload: LoginInput, request: Request):
    conn, cur = None, None
    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)

        # 1. Buscar usuario
        cur.execute(
            """
            SELECT 
                u.id_Usuario,
                u.id_Empleado,
                u.usr_Username,
                u.usr_PasswordHash,
                u.usr_IntentosFallidos,
                u.ESTADO_USR,
                e.emp_Nombre1,
                e.emp_Apellido1,
                d.dep_Nombre
            FROM USUARIOS u
            LEFT JOIN EMPLEADOS e ON u.id_Empleado = e.id_Empleado
            LEFT JOIN DEPARTAMENTOS d ON e.id_Departamento = d.id_Departamento
            WHERE u.usr_Username = %s
            LIMIT 1
            """,
            (payload.username,)
        )
        user_row = cur.fetchone()

        if not user_row:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

        if user_row["ESTADO_USR"] != "ACT":
            if user_row["ESTADO_USR"] == "PEN":
                raise HTTPException(status_code=403, detail="Tu solicitud de usuario está pendiente de aprobación.")
            raise HTTPException(status_code=403, detail="El usuario se encuentra inactivo. Contacte al administrador.")

        if (user_row["usr_IntentosFallidos"] or 0) >= 5:
            raise HTTPException(
                status_code=403, 
                detail="La cuenta se encuentra bloqueada por superar el límite de intentos fallidos (5). Solicite desbloqueo al administrador."
            )

        stored_hash = user_row["usr_PasswordHash"] or ""
        if not verify_password(payload.password, stored_hash):
            # Incrementar intentos fallidos
            cur.execute(
                "UPDATE USUARIOS SET usr_IntentosFallidos = COALESCE(usr_IntentosFallidos, 0) + 1 WHERE id_Usuario = %s",
                (user_row["id_Usuario"],)
            )
            conn.commit()
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

        # Contraseña correcta: resetear intentos y actualizar último acceso
        cur.execute(
            "UPDATE USUARIOS SET usr_IntentosFallidos = 0, usr_UltimoAcceso = NOW() WHERE id_Usuario = %s",
            (user_row["id_Usuario"],)
        )

        # 2. Obtener roles asignados
        cur.execute(
            """
            SELECT r.id_Rol, r.rol_Nombre
            FROM USUARIOSxROLES ur
            JOIN ROLES r ON ur.id_Rol = r.id_Rol
            WHERE ur.id_Usuario = %s AND ur.ESTADO_UxR = 'ACT' AND r.ESTADO_ROL = 'ACT'
            """,
            (user_row["id_Usuario"],)
        )
        roles = cur.fetchall()
        role_ids = [str(r["id_Rol"]).strip() for r in roles]
        role_names = [r["rol_Nombre"] for r in roles]

        # 3. Obtener permisos de todos los roles
        permissions = []
        if role_ids:
            format_strings = ','.join(['%s'] * len(role_ids))
            cur.execute(
                f"""
                SELECT DISTINCT p.id_Permiso, p.prm_Modulo, p.prm_Accion, p.prm_Descripcion
                FROM ROLESxPERMISOS rp
                JOIN PERMISOS p ON rp.id_Permiso = p.id_Permiso
                WHERE rp.id_Rol IN ({format_strings}) AND rp.ESTADO_RxP = 'ACT' AND p.ESTADO_PRM = 'ACT'
                """,
                tuple(role_ids)
            )
            permissions = cur.fetchall()

        perm_ids = [str(p["id_Permiso"]).strip() for p in permissions]

        # 4. Calcular rutas permitidas
        can_manage_users = puede_administrar_usuarios(role_names, perm_ids)
        is_admin = ("ROL-ADMIN" in role_ids) or any(
            str(role).strip().lower() in {"admin", "administrador", "superadministrador"} for role in role_names
        )
        if is_admin:
            allowed_routes = list(ALL_FRONTEND_ROUTES)
        else:
            allowed_set = set(["dashboard"])
            for pid in perm_ids:
                if pid in PERMISSION_TO_ROUTES_MAP:
                    allowed_set.update(PERMISSION_TO_ROUTES_MAP[pid])
            if can_manage_users:
                allowed_set.add("usuarios")
            # Mantener orden coherente de navItems
            allowed_routes = [r for r in ALL_FRONTEND_ROUTES if r in allowed_set]

        # 5. Registrar en LOG_AUDITORIA
        log_id = f"LOG-{uuid4().hex[:10].upper()}"
        cur.execute(
            """
            INSERT INTO LOG_AUDITORIA (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_ValorAnterior, log_ValorNuevo)
            VALUES (%s, %s, NOW(), 'USUARIOS', 'LOGIN', NULL, %s)
            """,
            (log_id, user_row["id_Usuario"], f"Inicio de sesión exitoso desde {client_ip}")
        )
        conn.commit()

        full_name = f"{user_row['emp_Nombre1'] or ''} {user_row['emp_Apellido1'] or ''}".strip() or user_row["usr_Username"]
        primary_role = role_names[0] if role_names else "Usuario"

        return {
            "success": True,
            "token": create_auth_token(user_row["id_Usuario"].strip()),
            "user": {
                "id": user_row["id_Usuario"].strip(),
                "username": user_row["usr_Username"].strip(),
                "employeeId": (user_row["id_Empleado"] or "").strip(),
                "fullName": full_name,
                "department": (user_row["dep_Nombre"] or "General").strip(),
                "primaryRole": primary_role,
                "roles": role_names,
                "roleIds": role_ids,
                "permissions": perm_ids,
                "allowedRoutes": allowed_routes,
            }
        }
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()

@app.post("/api/auth/logout")
def logout_usuario(payload: LogoutInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        user_id = payload.user_id
        if not user_id and payload.username:
            cur.execute("SELECT id_Usuario FROM USUARIOS WHERE usr_Username = %s LIMIT 1", (payload.username,))
            row = cur.fetchone()
            if row:
                user_id = row["id_Usuario"]

        if user_id:
            log_id = f"LOG-{uuid4().hex[:10].upper()}"
            cur.execute(
                """
                INSERT INTO LOG_AUDITORIA (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_ValorAnterior, log_ValorNuevo)
                VALUES (%s, %s, NOW(), 'USUARIOS', 'LOGOUT', NULL, 'Cierre de sesión de usuario')
                """,
                (log_id, user_id)
            )
            conn.commit()
        return {"success": True, "mensaje": "Sesión finalizada correctamente."}
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()

@app.get("/api/auth/demo-accounts")
def listar_cuentas_demo():
    return [
        {
            "role": "Administrador",
            "roleId": "ROL-ADMIN",
            "username": "admin",
            "password": "Admin123*",
            "description": "Acceso total a todos los módulos y configuraciones del sistema.",
            "color": "#6366f1"
        },
        {
            "role": "Ventas / Caja",
            "roleId": "ROL-VENTAS",
            "username": "vendedor",
            "password": "Ventas123*",
            "description": "Punto de venta (POS), facturación y cartera de clientes.",
            "color": "#10b981"
        },
        {
            "role": "Bodega e Inventario",
            "roleId": "ROL-BODEGA",
            "username": "bodeguero",
            "password": "Bodega123*",
            "description": "Ajustes físicos, recepciones de mercadería, entregas y stock.",
            "color": "#f59e0b"
        },
        {
            "role": "Compras / Abastecimiento",
            "roleId": "ROL-COMPRA",
            "username": "compras",
            "password": "Compras123*",
            "description": "Órdenes de compra a proveedores, unidades de medida y catálogo.",
            "color": "#0ea5e9"
        },
        {
            "role": "Contabilidad",
            "roleId": "ROL-CONTA",
            "username": "contador",
            "password": "Conta123*",
            "description": "Libro diario, catálogo de cuentas, bancos, centros de costos y balances.",
            "color": "#8b5cf6"
        },
        {
            "role": "Talento Humano",
            "roleId": "ROL-RRHH",
            "username": "rrhh",
            "password": "Rrhh123*",
            "description": "Ficha del personal, dependientes y liquidación de roles de pago.",
            "color": "#ec4899"
        }
    ]

@app.get("/api/auth/roles")
def listar_roles_catalogo(_: str = Depends(require_user_manager)):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT 
                r.id_Rol AS id,
                r.rol_Nombre AS nombre,
                r.rol_Descripcion AS descripcion,
                r.ESTADO_ROL AS estado,
                COUNT(ur.id_Usuario) AS usuariosAsignados
            FROM ROLES r
            LEFT JOIN USUARIOSxROLES ur ON r.id_Rol = ur.id_Rol AND ur.ESTADO_UXR = 'ACT'
            GROUP BY r.id_Rol, r.rol_Nombre, r.rol_Descripcion, r.ESTADO_ROL
            ORDER BY r.id_Rol ASC
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


# ==========================================
# 12. GESTIÓN DE USUARIOS (CRUD + ROLES)
# ==========================================

class RegistroPublicoInput(BaseModel):
    cedula: str = Field(min_length=10, max_length=20)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)

    @field_validator("username")
    @classmethod
    def validar_username(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,50}", clean):
            raise ValueError("El nombre de usuario contiene caracteres no permitidos.")
        return clean

    @field_validator("cedula")
    @classmethod
    def validar_cedula(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean.isdigit() or not 10 <= len(clean) <= 20:
            raise ValueError("Ingresa la cédula registrada en la ficha del empleado.")
        return clean


@app.post("/api/auth/registro", status_code=201)
def registrar_solicitud_usuario(payload: RegistroPublicoInput):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id_Empleado
            FROM EMPLEADOS
            WHERE emp_Cedula = %s AND ESTADO_EMP = 'ACT'
            LIMIT 2
            """,
            (payload.cedula,),
        )
        matching_employees = cur.fetchall()
        if not matching_employees:
            raise HTTPException(
                status_code=400,
                detail="No encontramos una ficha activa con esa cédula. Contacta al administrador para registrar tus datos laborales.",
            )
        if len(matching_employees) > 1:
            raise HTTPException(
                status_code=409,
                detail="La cédula está asociada a más de una ficha. Contacta al administrador para corregir los datos.",
            )
        employee_id = str(matching_employees[0]["id_Empleado"]).strip()

        cur.execute(
            "SELECT 1 FROM USUARIOS WHERE usr_Username = %s OR id_Empleado = %s LIMIT 1",
            (payload.username, employee_id),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=409,
                detail="El usuario ya existe o el empleado ya tiene una cuenta.",
            )

        new_id = f"USR-{uuid4().hex[:12].upper()}"
        cur.execute(
            """
            INSERT INTO USUARIOS
                (id_Usuario, id_Empleado, usr_Username, usr_PasswordHash, ESTADO_USR)
            VALUES (%s, %s, %s, %s, 'PEN')
            """,
            (new_id, employee_id, payload.username, hash_password(payload.password)),
        )
        cur.execute(
            """
            INSERT INTO LOG_AUDITORIA
                (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada,
                 log_Accion, log_ValorAnterior, log_ValorNuevo)
            VALUES (%s, %s, NOW(), 'USUARIOS', 'INSERT', NULL, %s)
            """,
            (
                f"LOG-{uuid4().hex[:10].upper()}",
                new_id,
                f"Solicitud de cuenta: {payload.username}",
            ),
        )
        conn.commit()
        return {
            "id": new_id,
            "mensaje": "Solicitud registrada. Un administrador debe asignar roles y activar la cuenta.",
        }
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


class UsuarioCreate(BaseModel):
    id_Empleado: str = Field(min_length=1, max_length=10)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    rol_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("username")
    @classmethod
    def validar_username(cls, v: str) -> str:
        clean = str(v or "").strip()
        if not clean or RE_SQLI_DANGEROUS.search(clean) or not re.match(r"^[A-Za-z0-9_\-\.@]+$", clean):
            raise ValueError("El nombre de usuario contiene caracteres no permitidos.")
        return clean

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        if len(str(v or "")) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return str(v)

    @field_validator("rol_ids")
    @classmethod
    def validar_roles(cls, roles: list[str]) -> list[str]:
        if len(set(roles)) != len(roles):
            raise ValueError("No se puede asignar el mismo rol más de una vez.")
        if any(not re.fullmatch(r"[A-Za-z0-9-]{1,10}", role) for role in roles):
            raise ValueError("Uno o más identificadores de rol no son válidos.")
        return roles


class UsuarioUpdate(BaseModel):
    id_Empleado: str | None = Field(default=None, max_length=10)
    username: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=100)
    ESTADO_USR: str | None = None

    @field_validator("username")
    @classmethod
    def validar_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,50}", clean):
            raise ValueError("El nombre de usuario contiene caracteres no permitidos.")
        return clean

    @field_validator("ESTADO_USR")
    @classmethod
    def validar_estado(cls, value: str | None) -> str | None:
        if value is not None and value not in {"ACT", "INA", "PEN"}:
            raise ValueError("El estado de usuario no es válido.")
        return value


class UsuarioOut(BaseModel):
    id_Usuario: str
    id_Empleado: str
    username: str
    ESTADO_USR: str
    emp_Nombre1: str | None
    emp_Apellido1: str | None
    dep_Nombre: str | None
    roles: list[str]


@app.get("/api/usuarios")
def listar_usuarios(_: str = Depends(require_user_manager)):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT u.id_Usuario, u.id_Empleado, u.usr_Username AS username, u.ESTADO_USR, e.emp_Nombre1, e.emp_Apellido1, d.dep_Nombre FROM USUARIOS u LEFT JOIN EMPLEADOS e ON u.id_Empleado = e.id_Empleado LEFT JOIN DEPARTAMENTOS d ON e.id_Departamento = d.id_Departamento ORDER BY u.usr_Username ASC")
        usuarios = cur.fetchall()
        resultado = []
        for u in usuarios:
            cur.execute("SELECT r.rol_Nombre FROM USUARIOSxROLES ur JOIN ROLES r ON ur.id_Rol = r.id_Rol WHERE ur.id_Usuario = %s AND ur.ESTADO_UxR = 'ACT' AND r.ESTADO_ROL = 'ACT' ORDER BY r.rol_Nombre ASC", (u["id_Usuario"],))
            roles = [r["rol_Nombre"] for r in cur.fetchall()]
            resultado.append({"id_Usuario": u["id_Usuario"].strip(), "id_Empleado": u["id_Empleado"].strip(), "username": u["username"].strip(), "ESTADO_USR": u["ESTADO_USR"].strip(), "emp_Nombre1": u["emp_Nombre1"], "emp_Apellido1": u["emp_Apellido1"], "dep_Nombre": u["dep_Nombre"], "roles": roles})
        return resultado
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/usuarios/empleados-disponibles")
def listar_empleados_disponibles(_: str = Depends(require_user_manager)):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                e.id_Empleado AS id,
                e.emp_Nombre1 AS nombre,
                e.emp_Apellido1 AS apellido,
                d.dep_Nombre AS departamento
            FROM EMPLEADOS e
            LEFT JOIN DEPARTAMENTOS d ON d.id_Departamento = e.id_Departamento
            LEFT JOIN USUARIOS u ON u.id_Empleado = e.id_Empleado
            WHERE e.ESTADO_EMP = 'ACT' AND u.id_Usuario IS NULL
            ORDER BY e.emp_Nombre1, e.emp_Apellido1
            """
        )
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur:
            cur.close()
        if conn and conn.is_connected():
            conn.close()


@app.get("/api/usuarios/{usuario_id}/roles")
def obtener_roles_usuario(usuario_id: str, _: str = Depends(require_user_manager)):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT r.id_Rol AS id, r.rol_Nombre AS nombre FROM USUARIOSxROLES ur JOIN ROLES r ON ur.id_Rol = r.id_Rol WHERE ur.id_Usuario = %s AND ur.ESTADO_UxR = 'ACT' AND r.ESTADO_ROL = 'ACT' ORDER BY r.rol_Nombre ASC", (usuario_id,))
        return cur.fetchall()
    except mysql.connector.Error as error:
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.post("/api/usuarios")
def crear_usuario(
    payload: UsuarioCreate,
    actor_id: str = Depends(require_user_manager),
):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id_Usuario FROM USUARIOS WHERE usr_Username = %s OR id_Empleado = %s LIMIT 1",
            (payload.username, payload.id_Empleado),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="El nombre de usuario ya existe o el empleado ya tiene una cuenta.")
        cur.execute(
            "SELECT id_Empleado FROM EMPLEADOS WHERE id_Empleado = %s AND ESTADO_EMP = 'ACT' LIMIT 1",
            (payload.id_Empleado,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="El empleado no existe o está inactivo.")
        for rol_id in payload.rol_ids:
            cur.execute(
                "SELECT id_Rol FROM ROLES WHERE id_Rol = %s AND ESTADO_ROL = 'ACT' LIMIT 1",
                (rol_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail=f"El rol {rol_id} no existe o está inactivo.")
        new_id = f"USR-{uuid4().hex[:12].upper()}"
        password_hash = hash_password(payload.password)
        cur.execute("INSERT INTO USUARIOS (id_Usuario, id_Empleado, usr_Username, usr_PasswordHash, ESTADO_USR) VALUES (%s, %s, %s, %s, 'ACT')", (new_id, payload.id_Empleado, payload.username, password_hash))
        for rol_id in payload.rol_ids:
            cur.execute("INSERT INTO USUARIOSxROLES (id_Usuario, id_Rol, ESTADO_UxR) VALUES (%s, %s, 'ACT')", (new_id, rol_id))
        log_id = f"LOG-{uuid4().hex[:10].upper()}"
        cur.execute("INSERT INTO LOG_AUDITORIA (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_ValorAnterior, log_ValorNuevo) VALUES (%s, %s, NOW(), 'USUARIOS', 'INSERT', NULL, %s)", (log_id, actor_id, f"Usuario creado: {payload.username}"))
        conn.commit()
        return {"id": new_id, "mensaje": "Usuario creado exitosamente."}
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.put("/api/usuarios/{usuario_id}")
def actualizar_usuario(
    usuario_id: str,
    payload: UsuarioUpdate,
    actor_id: str = Depends(require_user_manager),
):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id_Usuario, ESTADO_USR FROM USUARIOS WHERE id_Usuario = %s LIMIT 1", (usuario_id,))
        existing_user = cur.fetchone()
        if not existing_user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if usuario_id == actor_id and payload.ESTADO_USR in {"INA", "PEN"}:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
        if payload.ESTADO_USR == "ACT":
            cur.execute(
                """
                SELECT 1
                FROM USUARIOSxROLES ur
                JOIN ROLES r ON r.id_Rol = ur.id_Rol
                WHERE ur.id_Usuario = %s AND ur.ESTADO_UxR = 'ACT' AND r.ESTADO_ROL = 'ACT'
                LIMIT 1
                """,
                (usuario_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Asigna al menos un rol activo antes de activar la cuenta.")
        if payload.id_Empleado is not None:
            cur.execute(
                "SELECT id_Empleado FROM EMPLEADOS WHERE id_Empleado = %s AND ESTADO_EMP = 'ACT' LIMIT 1",
                (payload.id_Empleado,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="El empleado seleccionado no existe o está inactivo.")
            cur.execute(
                "SELECT 1 FROM USUARIOS WHERE id_Empleado = %s AND id_Usuario <> %s LIMIT 1",
                (payload.id_Empleado, usuario_id),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="El empleado ya tiene otra cuenta de usuario.")
        if payload.username is not None:
            cur.execute(
                "SELECT 1 FROM USUARIOS WHERE usr_Username = %s AND id_Usuario <> %s LIMIT 1",
                (payload.username, usuario_id),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="El nombre de usuario ya existe.")
        updates = []
        values = []
        if payload.id_Empleado is not None:
            updates.append("id_Empleado = %s"); values.append(payload.id_Empleado)
        if payload.username is not None:
            updates.append("usr_Username = %s"); values.append(payload.username)
        if payload.password is not None:
            updates.append("usr_PasswordHash = %s"); values.append(hash_password(payload.password))
            updates.append("usr_IntentosFallidos = 0")
        if payload.ESTADO_USR is not None:
            updates.append("ESTADO_USR = %s"); values.append(payload.ESTADO_USR)
        if not updates:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar.")
        values.append(usuario_id)
        cur.execute(f"UPDATE USUARIOS SET {', '.join(updates)} WHERE id_Usuario = %s", tuple(values))
        log_id = f"LOG-{uuid4().hex[:10].upper()}"
        cur.execute("INSERT INTO LOG_AUDITORIA (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_ValorAnterior, log_ValorNuevo) VALUES (%s, %s, NOW(), 'USUARIOS', 'UPDATE', NULL, %s)", (log_id, actor_id, f"Usuario actualizado: {usuario_id}"))
        conn.commit()
        return {"mensaje": "Usuario actualizado exitosamente."}
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.delete("/api/usuarios/{usuario_id}")
def desactivar_usuario(
    usuario_id: str,
    actor_id: str = Depends(require_user_manager),
):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id_Usuario FROM USUARIOS WHERE id_Usuario = %s LIMIT 1", (usuario_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if usuario_id == actor_id:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
        cur.execute("UPDATE USUARIOS SET ESTADO_USR = 'INA' WHERE id_Usuario = %s", (usuario_id,))
        log_id = f"LOG-{uuid4().hex[:10].upper()}"
        cur.execute("INSERT INTO LOG_AUDITORIA (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada, log_Accion, log_ValorAnterior, log_ValorNuevo) VALUES (%s, %s, NOW(), 'USUARIOS', 'DELETE', NULL, %s)", (log_id, actor_id, f"Usuario desactivado: {usuario_id}"))
        conn.commit()
        return {"mensaje": "Usuario desactivado exitosamente."}
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


class AsignarRolInput(BaseModel):
    rol_id: str = Field(min_length=1, max_length=10)


@app.post("/api/usuarios/{usuario_id}/roles")
def asignar_rol_usuario(
    usuario_id: str,
    payload: AsignarRolInput,
    actor_id: str = Depends(require_user_manager),
):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        rol_id = payload.rol_id
        cur.execute("SELECT id_Usuario FROM USUARIOS WHERE id_Usuario = %s LIMIT 1", (usuario_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        cur.execute("SELECT id_Rol FROM ROLES WHERE id_Rol = %s AND ESTADO_ROL = 'ACT' LIMIT 1", (rol_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="El rol no existe o está inactivo.")
        cur.execute(
            "SELECT ESTADO_UxR FROM USUARIOSxROLES WHERE id_Usuario = %s AND id_Rol = %s LIMIT 1",
            (usuario_id, rol_id),
        )
        assigned_role = cur.fetchone()
        if assigned_role and assigned_role["ESTADO_UxR"] == "ACT":
            raise HTTPException(status_code=409, detail="El rol ya está asignado a este usuario.")
        if assigned_role:
            cur.execute(
                "UPDATE USUARIOSxROLES SET ESTADO_UxR = 'ACT' WHERE id_Usuario = %s AND id_Rol = %s",
                (usuario_id, rol_id),
            )
        else:
            cur.execute("INSERT INTO USUARIOSxROLES (id_Usuario, id_Rol, ESTADO_UxR) VALUES (%s, %s, 'ACT')", (usuario_id, rol_id))
        cur.execute(
            """
            INSERT INTO LOG_AUDITORIA
                (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada,
                 log_Accion, log_ValorAnterior, log_ValorNuevo)
            VALUES (%s, %s, NOW(), 'USUARIOS', 'INSERT', NULL, %s)
            """,
            (f"LOG-{uuid4().hex[:10].upper()}", actor_id, f"{rol_id} asignado a {usuario_id}"),
        )
        conn.commit()
        return {"mensaje": "Rol asignado exitosamente."}
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.delete("/api/usuarios/{usuario_id}/roles/{rol_id}")
def remover_rol_usuario(
    usuario_id: str,
    rol_id: str,
    actor_id: str = Depends(require_user_manager),
):
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT ESTADO_USR FROM USUARIOS WHERE id_Usuario = %s LIMIT 1", (usuario_id,))
        user_row = cur.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if user_row["ESTADO_USR"] == "ACT":
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM USUARIOSxROLES ur
                JOIN ROLES r ON r.id_Rol = ur.id_Rol
                WHERE ur.id_Usuario = %s
                  AND ur.ESTADO_UxR = 'ACT'
                  AND r.ESTADO_ROL = 'ACT'
                """,
                (usuario_id,),
            )
            if cur.fetchone()["total"] <= 1:
                raise HTTPException(status_code=409, detail="No se puede remover el último rol de una cuenta activa.")
        cur.execute("UPDATE USUARIOSxROLES SET ESTADO_UxR = 'INA' WHERE id_Usuario = %s AND id_Rol = %s AND ESTADO_UxR = 'ACT'", (usuario_id, rol_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="El rol no está asignado a este usuario.")
        cur.execute(
            """
            INSERT INTO LOG_AUDITORIA
                (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada,
                 log_Accion, log_ValorAnterior, log_ValorNuevo)
            VALUES (%s, %s, NOW(), 'USUARIOS', 'DELETE', NULL, %s)
            """,
            (f"LOG-{uuid4().hex[:10].upper()}", actor_id, f"{rol_id} removido de {usuario_id}"),
        )
        conn.commit()
        return {"mensaje": "Rol removido exitosamente."}
    except HTTPException:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    except mysql.connector.Error as error:
        if conn and conn.is_connected():
            conn.rollback()
        raise_database_error(error)
    finally:
        if cur: cur.close()
        if conn and conn.is_connected(): conn.close()


@app.get("/api/empleados")
def listar_empleados():
    conn, cur = None, None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT e.id_Empleado AS id, e.emp_Nombre1 AS nombre, e.emp_Apellido1 AS apellido, d.dep_Nombre AS departamento FROM EMPLEADOS e LEFT JOIN DEPARTAMENTOS d ON e.id_Departamento = d.id_Departamento ORDER BY e.emp_Nombre1 ASC, e.emp_Apellido1 ASC")
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
