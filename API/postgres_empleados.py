"""Creación de empleados en PostgreSQL con historial de cargo y auditoría."""

import re
from uuid import uuid4

from fastapi import HTTPException

from postgres_compras import _set_actor
from postgres_connection import connect_postgres


def crear_empleado(employee, actor: str, ip: str | None) -> dict:
    employee_id = employee.id.strip().upper() if employee.id else ""
    if employee_id and not re.fullmatch(r"[A-Z0-9-]{1,10}", employee_id):
        raise HTTPException(status_code=422, detail="El código del empleado no es válido.")

    department_id = employee.department_id.strip().upper()
    cargo_id = employee.cargo_id.strip().upper() if employee.cargo_id else None
    with connect_postgres() as conn:
        with conn.cursor() as cur:
            _set_actor(cur, actor, ip)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('licoreria_empleados_id'))")
            if not employee_id:
                cur.execute(
                    """SELECT COALESCE(MAX(
                           CASE WHEN TRIM(id_empleado) ~ '^EMP-[0-9]{6}$'
                                THEN SUBSTRING(TRIM(id_empleado) FROM 5)::integer ELSE 0 END
                       ), 0) FROM empleados"""
                )
                sequence = cur.fetchone()[0] + 1
                if sequence > 999999:
                    raise HTTPException(status_code=409, detail="Se agotaron los códigos disponibles para empleados.")
                employee_id = f"EMP-{sequence:06d}"
            cur.execute("SELECT 1 FROM empleados WHERE id_empleado = %s", (employee_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="El código de empleado ya está registrado.")

            cur.execute(
                "SELECT 1 FROM departamentos WHERE id_departamento = %s AND COALESCE(estado_dep, 'ACT') = 'ACT' FOR SHARE",
                (department_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=422, detail="El departamento no existe o no está activo.")
            if cargo_id:
                cur.execute(
                    "SELECT 1 FROM cargos WHERE id_cargo = %s AND COALESCE(estado_cgo, 'ACT') = 'ACT' FOR SHARE",
                    (cargo_id,),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=422, detail="El cargo no existe o no está activo.")

            cur.execute("SELECT 1 FROM empleados WHERE TRIM(emp_cedula) = %s", (employee.ci,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Ya existe un empleado registrado con la cédula {employee.ci}.")

            cur.execute(
                """INSERT INTO empleados (
                       id_empleado, id_departamento, emp_cedula, emp_apellido1, emp_apellido2,
                       emp_nombre1, emp_nombre2, emp_sexo, emp_fechanacimiento, emp_sueldo,
                       emp_direccion, emp_telefono, emp_celular, emp_mail, user_id, estado_emp
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACT')""",
                (
                    employee_id, department_id, employee.ci, employee.last_name1, employee.last_name2,
                    employee.first_name, employee.second_name, employee.gender, employee.birth_date,
                    employee.salary, employee.address, employee.phone, employee.mobile, employee.email, actor,
                ),
            )
            if cargo_id:
                cur.execute(
                    """INSERT INTO cargosxempleado
                       (id_cargo, id_empleado, cxe_fecha_inicio, user_id, estado_cxe)
                       VALUES (%s, %s, CURRENT_DATE, %s, 'ACT')""",
                    (cargo_id, employee_id, actor),
                )
            return {
                "id": employee_id,
                "mensaje": f"Empleado {employee.first_name} {employee.last_name1} ({employee_id}) registrado exitosamente.",
            }
