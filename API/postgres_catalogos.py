from psycopg.rows import dict_row

from postgres_connection import connect_postgres


UNITS_QUERY = """
    SELECT TRIM(id_Unidad_Medida) AS id, TRIM(um_Descripcion) AS nombre,
           um_FactorConversion AS factor
    FROM UNIDADES_MEDIDAS ORDER BY um_Descripcion
"""

CATALOG_QUERIES = (
    ("ciudades", "SELECT TRIM(id_Ciudad) AS id, TRIM(ciu_Descripcion) AS nombre, TRIM(ciu_Provincia) AS provincia, TRIM(ciu_Region) AS region FROM CIUDADES ORDER BY ciu_Descripcion"),
    ("categorias", "SELECT TRIM(id_Categoria) AS id, TRIM(cat_Nombre) AS nombre FROM CATEGORIAS WHERE ESTADO_CAT = 'ACT' OR ESTADO_CAT IS NULL ORDER BY cat_Nombre"),
    ("marcas", "SELECT TRIM(id_Marca) AS id, TRIM(mar_Nombre) AS nombre FROM MARCAS WHERE ESTADO_MAR = 'ACT' OR ESTADO_MAR IS NULL ORDER BY mar_Nombre"),
    ("perchas", "SELECT TRIM(id_Percha) AS id, TRIM(pch_Descripcion) AS nombre, TRIM(pch_Letra) AS letra, pch_Nivel AS nivel FROM PERCHAS WHERE ESTADO_PCH = 'ACT' OR ESTADO_PCH IS NULL ORDER BY pch_Letra, pch_Nivel"),
    ("bancos", "SELECT TRIM(id_Banco) AS id, TRIM(ban_Nombre) AS nombre FROM BANCOS WHERE ESTADO_BAN = 'ACT' OR ESTADO_BAN IS NULL ORDER BY ban_Nombre"),
)


def _units(cursor) -> list[dict]:
    cursor.execute(UNITS_QUERY)
    units = cursor.fetchall()
    for unit in units:
        if unit["factor"] is not None:
            unit["factor"] = float(unit["factor"])
    return units


def listar_unidades(actor: str | None, client_ip: str | None) -> list[dict]:
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            return _units(cursor)


def listar_catalogos(
    actor: str | None, client_ip: str | None, modules: set[str] | None = None,
) -> dict:
    allowed = {
        "ciudades": modules is None or bool(modules),
        "categorias": modules is None or "COMPRAS" in modules,
        "marcas": modules is None or "COMPRAS" in modules,
        "perchas": modules is None or bool(modules & {"COMPRAS", "INVENTARIOS"}),
        "bancos": modules is None or "CONTABILIDAD" in modules,
        "unidadesMedida": modules is None or "COMPRAS" in modules,
    }
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            results = {}
            for name, query in CATALOG_QUERIES:
                if allowed[name]:
                    cursor.execute(query)
                    results[name] = cursor.fetchall()
                else:
                    results[name] = []
            results["unidadesMedida"] = _units(cursor) if allowed["unidadesMedida"] else []
            return results


def registrar_auditoria(
    log_id: str, actor: str | None, table: str, action: str,
    client_ip: str | None, details: str,
) -> None:
    with connect_postgres() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO LOG_AUDITORIA
                    (id_Log, id_Usuario, log_FechaHora, log_TablaAfectada,
                     log_Accion, log_IP, log_ValorAnterior, log_ValorNuevo)
                VALUES (%s, %s, NOW(), %s, %s, %s, NULL, %s)
                """,
                (log_id, actor, table, action, client_ip, details),
            )
