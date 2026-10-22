# Informe de incidencias y pruebas de datos

## Resumen ejecutivo

Se ejecutaron pruebas con registros ficticios plausibles marcados con `PRUEBA` en las secciones de Abastecimiento, Bodega, Ventas y Administración. Los conteos se consultaron en MariaDB; no se contaron registros que existieran solo en el estado local del navegador.

La mayoría de los catálogos y operaciones principales alcanzaron 20 registros. El trabajo no puede declararse completo: Usuarios, Reportes y Auditoría no se pudieron verificar porque la sesión administrativa expiró y la interfaz devolvió HTTP 401. Además, algunas relaciones de Recursos Humanos tienen menos de 20 filas y los asientos generados siguen pendientes.

## Conteos verificados en la base de datos

| Sección | Tabla o vista | Registros | Resultado / estado |
|---|---|---:|---|
| Abastecimiento | Proveedores | 20 | Umbral alcanzado |
| Abastecimiento | Compras | 20 | 20 aprobadas (`APR`) |
| Abastecimiento | Recepciones | 20 | 20 aprobadas (`APR`) |
| Bodega | Unidades de medida | 20 | Umbral alcanzado |
| Bodega | Productos | 20 | Umbral alcanzado |
| Bodega | Ajustes | 20 | 20 aprobados (`APR`) |
| Bodega | Entregas | 20 | 20 confirmadas (`ENT`) |
| Ventas | Clientes | 20 | Umbral alcanzado |
| Ventas | Facturas | 20 | 20 abiertas (`ABI`) |
| Administración | Cuentas contables | 20 | Umbral alcanzado |
| Administración | Centros de costo | 20 | Umbral alcanzado |
| Administración | Bancos | 20 | Umbral alcanzado |
| Administración | Bonificaciones | 20 | Catálogo |
| Administración | Descuentos | 20 | Catálogo |
| Administración | Empleados | 20 | Umbral alcanzado |
| Administración | Roles de pago | 20 | 20 abiertos (`ABI`) |
| Administración | Asientos | 40 | 40 pendientes (`PEN`); la vista de detalle contiene 60 líneas |
| Administración | Usuarios | 15 | Faltan 5 para llegar a 20; bloqueado por sesión expirada |

También se observaron relaciones de Recursos Humanos por debajo de 20: cargos asignados a empleados (18), empleados asociados a departamentos (19), cargas familiares (13), bonificaciones asociadas a roles (3) y descuentos asociados a roles (2). Son relaciones distintas de los catálogos y de los 20 empleados/roles creados; deben completarse si el requisito de 20 aplica también a cada relación visible.

## Problemas encontrados y correcciones

### Compras y ajustes de inventario

- **Causa:** Los triggers de aprobación requerían un centro de costo activo, y los procedimientos enviaban acciones de auditoría que el `CHECK` de `LOG_AUDITORIA` no acepta.
- **Corrección:** Se ajustaron el trigger y los procedimientos en [20261022_fix_purchase_accounting_cost_center.sql](./API/migrations/20261022_fix_purchase_accounting_cost_center.sql) para usar un centro de costo válido y acciones permitidas.
- **Problema adicional en ajustes:** La aprobación podía actualizar existencias dos veces (trigger y API), y el trigger generaba identificadores/descripciones que excedían los límites de `ASIENTOS`.
- **Corrección:** Se eliminó la actualización duplicada desde la API, se acotaron los valores de asiento y se aplicó el signo correcto para sobrantes y mermas.

### Registro de ventas desde el POS

- **Causa:** La API invocaba `SP_FACTURA_CREAR` con menos argumentos de los requeridos. Además, ante un error el POS guardaba una factura y una entrega solo en `localStorage`, presentándolas como exitosas.
- **Corrección:** Se completaron los argumentos, se envía el descuento y el POS ya informa los errores de API sin fabricar resultados locales. Se sincronizan las listas con la respuesta del servidor.
- **Verificación:** Se registraron de nuevo 20 facturas y se verificó que persistieran en MariaDB.

### Confirmación de entregas

- **Causa:** La API guardaba el estado `APR`, pero el trigger de inventario procesa la transición a `ENT`.
- **Corrección:** La confirmación ahora persiste `ENT`; se verificaron 20 entregas con ese estado.

### Alta de bancos

- **Causa:** El endpoint calculaba el identificador consecutivo, pero no lo asignaba al registro. Con el código vacío, la operación de inserción podía sobrescribir por clave duplicada.
- **Corrección:** Se asigna el código `BAN-######`, se validan duplicados y se evita sobrescribir registros existentes. Se retiró únicamente el registro defectuoso creado durante la prueba y se volvieron a cargar los 20 bancos.

### Bonificaciones y descuentos

- **Causa:** La interfaz de nómina no exponía las acciones CRUD para ambos catálogos.
- **Corrección:** Se incorporaron las acciones de creación, edición, baja lógica y reactivación en [PayrollManagement.tsx](./frontend/src/pages/PayrollManagement.tsx). La baja lógica conserva el historial.
- **Verificación:** Hay 20 filas en cada catálogo.

### Gestión de roles de pago

- **Aprobación:** Los procedimientos registraban acciones de auditoría no aceptadas por la restricción de la tabla, y el trigger contable intentaba usar códigos de cuenta inexistentes. La migración [20261022_fix_payroll_workflow.sql](./API/migrations/20261022_fix_payroll_workflow.sql) corrige las acciones, resuelve cuentas activas de gasto de nómina y obligaciones laborales y crea asientos balanceados con códigos propios del módulo.
- **Edición y eliminación:** La pantalla no ofrecía editar ni eliminar roles; solo permitía aprobar o anular. Se agregaron edición transaccional y eliminación física limitada a roles abiertos (`ABI`), con auditoría. Los roles aprobados/anulados no se pueden editar ni eliminar.
- **Verificación:** Se probó la aprobación con un rol ficticio dentro de una transacción y se revirtió: el cambio de estado, asiento, líneas contables y auditoría se generaron correctamente y no dejaron cambios persistentes. También se probó crear, editar y eliminar un rol; el conteo volvió a 20.

### Usuarios, Reportes y Auditoría

- **Bloqueo pendiente:** Tras reiniciar la API, la interfaz indicó que la sesión no era válida o había expirado; las llamadas protegidas devolvieron HTTP 401. No se inventaron credenciales ni se crearon usuarios sin una sesión administrativa válida.
- **Impacto:** Usuarios permanece en 15 registros y no se completó la verificación funcional de Usuarios, Reportes ni Auditoría.
- **Siguiente paso:** Reautenticar desde la interfaz y continuar esas pruebas con autorización válida.

## Validaciones técnicas

- `npm --prefix frontend run build`: correcto.
- `python -m py_compile API\main.py`: correcto.
- `git diff --check`: correcto.
- API local, `/openapi.json`: HTTP 200.
- Conteos y estados consultados directamente en MariaDB.

## Pendientes y límites de la prueba

1. Reautenticar una sesión administrativa y verificar Usuarios, Reportes y Auditoría; completar los 5 usuarios faltantes solo desde una sesión autorizada.
2. Confirmar si el mínimo de 20 debe aplicarse también a las relaciones de Recursos Humanos listadas arriba y, de ser así, completarlas.
3. Revisar y aprobar contablemente los 40 asientos pendientes antes de considerarlos contabilizados. Las facturas y los roles de pago están abiertos (`ABI`); no se reportan como pagados o cerrados.
4. Revisar la advertencia del navegador por una expresión `pattern` incompatible con el modo `v`; no bloqueó las operaciones verificadas.

## Archivos de código involucrados

- [main.py](./API/main.py)
- [20261022_fix_purchase_accounting_cost_center.sql](./API/migrations/20261022_fix_purchase_accounting_cost_center.sql)
- [api.ts](./frontend/src/api.ts)
- [POS.tsx](./frontend/src/pages/POS.tsx)
- [FinancialPages.tsx](./frontend/src/pages/FinancialPages.tsx)
- [InventoryPages.tsx](./frontend/src/pages/InventoryPages.tsx)
- [types.ts](./frontend/src/types.ts)
- [PayrollManagement.tsx](./frontend/src/pages/PayrollManagement.tsx)
