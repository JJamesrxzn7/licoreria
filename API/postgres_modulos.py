"""Consultas PostgreSQL para inventario, talento humano y contabilidad."""

from psycopg.rows import dict_row

from postgres_connection import connect_postgres


QUERIES = {
    "ajustes": """
        SELECT TRIM(a.id_ajuste) AS id, a.aju_fechahora AS date,
               TRIM(a.aju_descripcion) AS reason, TRIM(a.id_empleado) AS responsible,
               a.estado_aju AS status, TRIM(d.id_producto) AS "productId",
               TRIM(p.pro_descripcion) AS "productName", d.pxa_cantidad AS qty,
               CASE WHEN d.pxa_qty_ajustada >= 0 THEN 'IN' ELSE 'OUT' END AS type
        FROM ajustes a LEFT JOIN proxaju d ON a.id_ajuste = d.id_ajuste
        LEFT JOIN productos p ON d.id_producto = p.id_producto ORDER BY a.aju_fechahora DESC
    """,
    "departamentos": """
        SELECT TRIM(id_departamento) AS id, TRIM(dep_nombre) AS nombre
        FROM departamentos WHERE estado_dep = 'ACT' OR estado_dep IS NULL ORDER BY dep_nombre
    """,
    "cargos": "SELECT TRIM(id_cargo) AS id, TRIM(cgo_descripcion) AS nombre FROM cargos ORDER BY cgo_descripcion",
    "empleados": """
        SELECT TRIM(e.id_empleado) AS id, TRIM(e.emp_cedula) AS ci,
               CONCAT_WS(' ', TRIM(e.emp_nombre1), NULLIF(TRIM(e.emp_nombre2), ''),
                         TRIM(e.emp_apellido1), NULLIF(TRIM(e.emp_apellido2), '')) AS name,
               TRIM(e.emp_nombre1) AS nombre1, COALESCE(TRIM(e.emp_nombre2), '') AS nombre2,
               TRIM(e.emp_apellido1) AS apellido1, COALESCE(TRIM(e.emp_apellido2), '') AS apellido2,
               COALESCE(TRIM(d.dep_nombre), 'Ventas') AS department,
               TRIM(e.id_departamento) AS "departmentId",
               COALESCE(TRIM(c.cgo_descripcion), 'Colaborador') AS role,
               COALESCE(TRIM(ce.id_cargo), '') AS "cargoId", e.emp_sueldo AS salary,
               e.emp_fechanacimiento AS "birthDate", COALESCE(TRIM(e.emp_sexo), 'M') AS gender,
               COALESCE(TRIM(e.emp_direccion), '') AS address, COALESCE(TRIM(e.emp_telefono), '') AS phone,
               COALESCE(TRIM(e.emp_celular), '') AS mobile, COALESCE(TRIM(e.emp_mail), '') AS email,
               CASE WHEN e.estado_emp = 'ACT' OR e.estado_emp IS NULL THEN 'ACTIVE' ELSE 'INACTIVE' END AS status,
               (SELECT COUNT(*) FROM cargas cg WHERE cg.id_empleado = e.id_empleado
                AND (cg.estado_car = 'ACT' OR cg.estado_car IS NULL)) AS "familyDependents"
        FROM empleados e LEFT JOIN departamentos d ON d.id_departamento = e.id_departamento
        LEFT JOIN LATERAL (
            SELECT id_cargo FROM cargosxempleado
            WHERE id_empleado = e.id_empleado AND (estado_cxe = 'ACT' OR estado_cxe IS NULL)
            ORDER BY cxe_fecha_inicio DESC NULLS LAST, id_cargo LIMIT 1
        ) ce ON true LEFT JOIN cargos c ON c.id_cargo = ce.id_cargo
        ORDER BY e.emp_apellido1, e.emp_nombre1
    """,
    "historial_cargos": """
        SELECT TRIM(ce.id_cargo) AS "cargoId", TRIM(c.cgo_descripcion) AS "cargoNombre",
               ce.cxe_fecha_inicio AS "fechaInicio", ce.cxe_fecha_fin AS "fechaFin",
               TRIM(ce.estado_cxe) AS estado
        FROM cargosxempleado ce JOIN cargos c ON c.id_cargo = ce.id_cargo
        WHERE ce.id_empleado = %s ORDER BY ce.cxe_fecha_inicio DESC
    """,
    "cargas": """
        SELECT TRIM(id_carga) AS id, TRIM(car_cedula) AS ci,
               CONCAT_WS(' ', TRIM(car_nombre1), NULLIF(TRIM(car_nombre2), ''),
                         TRIM(car_apellido1), NULLIF(TRIM(car_apellido2), '')) AS name,
               TRIM(car_nombre1) AS nombre1, COALESCE(TRIM(car_nombre2), '') AS nombre2,
               TRIM(car_apellido1) AS apellido1, COALESCE(TRIM(car_apellido2), '') AS apellido2,
               COALESCE(TRIM(car_sexo), 'M') AS sexo, car_fechanacimiento AS "fechaNacimiento",
               COALESCE(TRIM(car_parentesco), 'Hijo/a') AS parentesco,
               COALESCE(TRIM(car_estadocivil), 'Soltero/a') AS "estadoCivil",
               COALESCE(TRIM(car_dependencia), 'Total') AS dependencia, TRIM(estado_car) AS estado
        FROM cargas WHERE id_empleado = %s AND (estado_car = 'ACT' OR estado_car IS NULL)
        ORDER BY car_apellido1, car_nombre1
    """,
    "bonificaciones": """
        SELECT TRIM(id_bonificacion) AS id, TRIM(bon_descripcion) AS nombre, bon_valor AS valor,
               COALESCE(TRIM(estado_bon), 'ACT') AS estado FROM bonificaciones ORDER BY bon_descripcion
    """,
    "descuentos": """
        SELECT TRIM(id_descuento) AS id, TRIM(des_descripcion) AS nombre, des_valor AS valor,
               COALESCE(TRIM(estado_des), 'ACT') AS estado FROM descuentos ORDER BY des_descripcion
    """,
    "nomina": """
        SELECT TRIM(p.id_pago) AS id, p.pag_descripcion AS description,
               p.pag_fecha_inicio AS "startDate", p.pag_fecha_fin AS "endDate",
               p.pag_fecha_fin AS date, TRIM(d.id_empleado) AS "employeeId",
               CONCAT_WS(' ', TRIM(e.emp_nombre1), TRIM(e.emp_apellido1)) AS "employeeName",
               COALESCE(TRIM(dep.dep_nombre), 'General') AS department,
               d.pxe_sueldo AS "baseSalary", d.pxe_bonificaciones AS bonus,
               d.pxe_descuentos AS deductions, d.pxe_valor_neto AS amount, p.estado_pag AS status
        FROM pagos p JOIN pagxemp d ON p.id_pago = d.id_pago
        JOIN empleados e ON e.id_empleado = d.id_empleado
        LEFT JOIN departamentos dep ON dep.id_departamento = e.id_departamento
        ORDER BY p.pag_fecha_fin DESC, p.id_pago DESC, d.id_empleado
    """,
    "nomina_bonos": """
        SELECT TRIM(bxp.id_pago) AS "pagoId", TRIM(bxp.id_empleado) AS "employeeId",
               TRIM(bxp.id_bonificacion) AS "bonusId", TRIM(b.bon_descripcion) AS "bonusName",
               bxp.bxe_fecha AS date, bxp.bxe_valor AS amount
        FROM bonxempxpag bxp JOIN bonificaciones b ON bxp.id_bonificacion = b.id_bonificacion
        ORDER BY bxp.id_pago, bxp.bxe_fecha
    """,
    "nomina_descuentos": """
        SELECT TRIM(dxp.id_pago) AS "pagoId", TRIM(dxp.id_empleado) AS "employeeId",
               TRIM(dxp.id_descuento) AS "deductionId", TRIM(d.des_descripcion) AS "deductionName",
               dxp.dxe_fecha AS date, dxp.dxe_valor AS amount
        FROM desxempxpag dxp JOIN descuentos d ON dxp.id_descuento = d.id_descuento
        ORDER BY dxp.id_pago, dxp.dxe_fecha
    """,
    "bancos": """
        SELECT TRIM(id_banco) AS id, TRIM(ban_nombre) AS nombre, COALESCE(estado_ban, 'ACT') AS estado
        FROM bancos ORDER BY id_banco
    """,
    "centros_costos": """
        SELECT TRIM(cc.id_centrocosto) AS id, TRIM(cc.id_departamento) AS "idDepartamento",
               TRIM(COALESCE(d.dep_nombre, 'General')) AS departamento, TRIM(cc.cco_nombre) AS nombre,
               cc.cco_presupuestomensual AS "presupuestoMensual", COALESCE(cc.estado_cco, 'ACT') AS estado
        FROM centros_costos cc LEFT JOIN departamentos d ON cc.id_departamento = d.id_departamento
        ORDER BY cc.id_centrocosto
    """,
    "cuentas": """
        SELECT TRIM(id_cuenta) AS id, TRIM(id_cuenta) AS code, TRIM(cue_descripcion) AS name,
               TRIM(cue_tipo) AS type,
               CASE TRIM(cue_tipo) WHEN 'MAY' THEN 'MAYOR' WHEN 'DET' THEN 'DETALLE'
                    ELSE TRIM(cue_tipo) END AS "accountTypeLabel",
               COALESCE(cue_debe00, 0) - COALESCE(cue_haber00, 0) AS balance
        FROM cuentas WHERE estado_cue = 'ACT' OR estado_cue IS NULL ORDER BY id_cuenta
    """,
    "asientos": """
        SELECT TRIM(id_asiento) AS id, asi_fechahora AS date, TRIM(asi_descripcion) AS description,
               estado_asi AS status, 'MANUAL' AS source FROM asientos ORDER BY asi_fechahora DESC
    """,
    "asiento_lineas": """
        SELECT TRIM(id_asiento) AS "asientoId", TRIM(id_cuenta) AS "accountId",
               cxa_debe AS debit, cxa_haber AS credit FROM ctaxasi ORDER BY id_asiento
    """,
}


def listar(kind, *params):
    with connect_postgres() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(QUERIES[kind], params)
            rows = cursor.fetchall()
            if kind == "asientos":
                cursor.execute(QUERIES["asiento_lineas"])
                details = {}
                for line in cursor.fetchall():
                    entry_id = line.pop("asientoId")
                    details.setdefault(entry_id, []).append(line)
                for row in rows:
                    row["lines"] = details.get(row["id"], [])
            if kind == "nomina":
                for query, field in (("nomina_bonos", "bonusLines"), ("nomina_descuentos", "deductionLines")):
                    cursor.execute(QUERIES[query])
                    details = {}
                    for line in cursor.fetchall():
                        key = (line.pop("pagoId"), line.pop("employeeId"))
                        details.setdefault(key, []).append(line)
                    for row in rows:
                        row[field] = details.get((row["id"], row["employeeId"]), [])
            return rows
