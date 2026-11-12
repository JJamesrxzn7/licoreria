# Configuración de permisos en MariaDB

## PostgreSQL / Supabase

`20261111_nomina_aprobacion_postgresql.sql` reemplaza el trigger de aprobación
de nómina por la regla anterior de MariaDB: registra sueldo más bonos como
gasto y deuda en un asiento pendiente sin separar los descuentos. Selecciona
cuentas activas de detalle por descripción o prefijo y un centro de costo activo
del departamento. Se probó únicamente en una copia local aislada. Revisar las
cuentas elegidas, RLS y privilegios efectivos de la cuenta API antes de aplicar
la migración a Supabase; no se ha aplicado allí. Mantener
`PAYROLL_APPROVAL_ENABLED` deshabilitado hasta completar esa revisión. La API
comprueba además que el trigger actualizado esté instalado antes de aprobar.

`20261108_matriz_permisos_postgresql.sql` es una adaptación para PostgreSQL,
no una migración automática. Ejecutarla modifica el catálogo de permisos:
primero comprueba respaldo, roles y permisos activos, revisa el script y
pruébalo en una base aislada. Falla si faltan roles o permisos, si hay
duplicados o si la matriz no contiene 50 asignaciones. Conserva los permisos
adicionales del Administrador, desactiva permisos adicionales de los 15 roles
indicados y no asigna roles a usuarios. Debe ejecutarse íntegramente en una
conexión que se detenga ante errores; si falla, realiza `ROLLBACK`.
No se ha ejecutado en Supabase.

La API PostgreSQL comprueba la matriz por nombres de roles activos en cada
solicitud. El catálogo SQL por sí solo no protege los endpoints. La API y
sus operaciones todavía están en migración y no deben exponerse en producción.

`20261108_compras_postgresql.sql` añade la tasa de IVA a las compras y
corrige el recálculo de subtotales del trigger. Conserva los importes ya
guardados y estima la tasa de registros anteriores a partir de IVA y
subtotal; esa estimación puede diferir de la tasa original por redondeo.
La aprobación sigue dependiendo de las cuentas y centro de costo que usa el
trigger contable existente. Si no existen, la operación falla y se revierte.
Aplicada en Supabase; no repetir sin revisar previamente su estado.

`20261108_ventas_postgresql.sql` agrega el IVA por factura y el control
idempotente de ventas, corrige el doble descuento de inventario y permite
entregas parciales acumuladas. También modifica triggers y restringe las rutas
antiguas de aprobación y anulación. Las facturas históricas sin control no se
pueden aprobar ni anular mediante la nueva API hasta conciliarlas. La
aprobación crea un asiento pendiente sin detalle contable completo. La migración
está aplicada en Supabase, pero sigue pendiente conciliar facturas históricas.
No volver a ejecutarla: no es idempotente.
`ventas_control` tiene políticas RLS de SELECT, INSERT y UPDATE, pero estas
políticas no otorgan privilegios de tabla. Un administrador debe conceder esos
tres privilegios únicamente al rol dedicado de la API. Se verificó que la cuenta
dedicada no es propietaria ni tiene `BYPASSRLS`; la autorización de negocio
sigue correspondiendo a la API.

`20261108_sesiones_postgresql.sql` crea el registro de tokens revocados por
su hash, con RLS y sin privilegios de tabla para PUBLIC. Las políticas RLS
permiten SELECT e INSERT a cuentas con privilegios explícitos; el administrador
debe otorgar ambos exclusivamente a la cuenta de la API y verificar que pueda
ver e insertar filas, incluso si no es propietaria. La aplicación falla de forma
cerrada si falta la tabla o sus privilegios. Los registros vencidos pueden
eliminarse posteriormente con una tarea administrativa controlada que borre
solo filas con `expira_en <= now()`. La migración está aplicada en Supabase;
no volver a ejecutarla: no es idempotente.

`20261108_api_role_rls_postgresql.sql` prepara el rol de grupo sin LOGIN
`licoreria_api_access`, concede SELECT sobre las 43 tablas utilizadas por los
módulos PostgreSQL (incluidas las dos añadidas por las migraciones de ventas y
sesiones) e INSERT/UPDATE únicamente sobre las tablas escritas por los handlers.
No concede DELETE, secuencias, DDL, propiedad ni `BYPASSRLS`. Añade políticas
RLS de acceso total por fila para ese grupo y EXECUTE solo sobre los cuatro
procedimientos de compras y su helper de auditoría `sp_registrar_log`, después
de comprobar que existan y no sean `SECURITY DEFINER`. Esta configuración
confía plenamente en el backend para las filas de esas tablas: nunca asignes
el rol a una conexión de usuario final.
El administrador ya creó una cuenta LOGIN dedicada con membresía heredada.
La migración está aplicada en Supabase y no es idempotente: no volver a
ejecutarla. Mediante TLS y en modo de solo lectura, se comprobó que la cuenta
puede consultar las 43 tablas, que estas tienen RLS habilitado y que los cinco
procedimientos de compras/auditoría son ejecutables.

Con el esquema actualizado sin datos, privilegios efectivos equivalentes y datos
ficticios en PostgreSQL local, se probaron compras, recepciones, ventas,
entregas, anulación, idempotencia, stock y auditoría. También se probó la
matriz HTTP de ventas con roles simulados y se rechazaron DELETE y CREATE.
Se ejecutaron 24 pruebas focalizadas sin fallos. Esto no sustituye pruebas de
escritura reales, conciliación contable ni la revisión de otros módulos.
La API aún no se ha desplegado en Render.

`20261108_dba_limitado_postgresql.sql` prepara un rol PostgreSQL sin LOGIN,
sin capacidades administrativas y sin `CREATE` sobre el esquema público;
solo otorga lectura y escritura de datos en los objetos actuales. El rol no
se asigna automáticamente y está sujeto a RLS. Las membresías, permisos de
`PUBLIC`, propiedad de objetos y funciones `SECURITY DEFINER` pueden ampliar
el acceso efectivo de cualquier cuenta. La capacidad de borrar filas incluye
tablas de seguridad y auditoría; no garantiza que los datos estén protegidos
frente a borrado. Los objetos futuros necesitan permisos adicionales. No se
ha ejecutado en Supabase.

La cuenta administrativa anterior poseía las tablas y tenía `BYPASSRLS`;
no debe usarse para la API. El rol DBA limitado tampoco es una cuenta para
la API. `postgres_connection.py` rechaza roles superusuario,
con `BYPASSRLS`, privilegios de administración o `CREATE` en `public`, y roles
propietarios o miembros de propietarios de objetos o de la base conectada.
También rechaza membresía en roles administrativos. Esta comprobación es un
bloqueo preventivo; no otorga los permisos faltantes ni demuestra que las
políticas RLS permitan las operaciones legítimas.

## MariaDB

Los scripts `20261107_matriz_permisos.sql` y `20261107_rol_dba_limitado.sql`
están preparados para la base `licoreriadatabase` en MariaDB. No se ejecutan
automáticamente. Antes de usarlos, realiza una copia de seguridad y revisa
los permisos de la cuenta que los ejecutará.

Desde un cliente MariaDB con soporte para `SOURCE` y `DELIMITER`, situado en
esta carpeta, utiliza una conexión administrativa dedicada:

```sql
SOURCE 20261107_matriz_permisos.sql;
SOURCE 20261107_rol_dba_limitado.sql;
```

Ejecuta cada archivo por separado y detente si aparece un error. No uses
`--force`. La matriz comprueba el catálogo y los motores antes de actualizar;
si faltan roles o permisos, hay duplicados o están inactivos, informa del
problema y no los crea ni activa. Actualiza los 15 roles de módulo para que
tengan exactamente las dos acciones indicadas y agrega las veinte acciones al
Administrador. Los demás roles no se modifican. Las asignaciones de varios
roles activos a un usuario se suman.

El segundo archivo crea un rol **de MariaDB**, separado de los roles de la
aplicación, sin asignarlo a ninguna cuenta. Solo concede `SELECT`, `INSERT`,
`UPDATE`, `DELETE` y `SHOW VIEW` en esta base. Es deliberadamente distinto
de un DBA completo: no concede `DROP`, `ALTER`, `CREATE`, `EXECUTE`,
administración de cuentas ni `GRANT OPTION`. Si ya existe el nombre del rol,
el script falla en vez de aprovechar sus permisos desconocidos. `CREATE ROLE`
y `GRANT` producen confirmaciones implícitas: si falla el `GRANT`, el rol puede
haber quedado creado; un administrador debe inspeccionarlo antes de corregirlo.

El rol puede modificar **todos los datos**, incluidas tablas de seguridad y
auditoría, y `DELETE` puede vaciar tablas. No impide alterar la autorización de
la aplicación ni garantiza que no se pierdan datos. Los privilegios directos,
globales y otros roles de la cuenta se suman; no existe una denegación que
anule un `DROP` ya concedido. Antes de asignar el rol, revisa `SHOW GRANTS`
de la cuenta y sus otros roles, las rutinas `SQL SECURITY DEFINER`, los
disparadores y las cuentas compartidas. El propio SQL incluye un ejemplo
comentado para asignarlo después.

**Importante:** esta matriz configura datos de autorización, pero por sí sola
no protege los endpoints. La API aún debe autenticar y verificar cada acción
contra los permisos vigentes. Una cuenta compartida de la API con privilegios
amplios tampoco queda restringida por el rol DBA. No expongas el sistema a
usuarios no confiables hasta completar y probar esa protección.
