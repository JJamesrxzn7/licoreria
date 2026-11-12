# Migración de la API a PostgreSQL/Supabase y preparación del despliegue

> **Estado:** el destino elegido es Supabase/PostgreSQL. La migración funcional
> sigue en curso; el Blueprint de Render prepara un despliegue controlado, no
> certifica que todos los módulos estén migrados ni que la aplicación esté
> lista para operar con datos reales.

## Migración a PostgreSQL: estado actual

Se probaron la conexión TLS a Supabase, el inicio de sesión y consultas de
lectura en una copia local del esquema sin datos reales. Con
`DATABASE_BACKEND=postgresql`, están disponibles el inicio de sesión, el
estado de configuración, catálogos, y consultas de compras, ventas,
recepciones y entregas, así como listas de productos, clientes y proveedores.
El administrador también puede consultar usuarios, roles, empleados disponibles
y los últimos 100 eventos de auditoría. Estas consultas se probaron con datos
sintéticos; las columnas utilizadas se verificaron contra el esquema de
Supabase sin leer registros. La gestión de usuarios en PostgreSQL aún es
de solo lectura: crear, editar, activar y asignar roles siguen sin migrar.
Se añadieron consultas PostgreSQL de ajustes de inventario; departamentos,
cargos, empleados, cargas, historial de cargos, nómina y sus catálogos; y
bancos, centros de costos, cuentas y asientos con detalle. Estas consultas se
validaron contra una copia local del esquema real sin datos. No crean registros
predeterminados al leer. Los detalles de nómina se agrupan por pago y
empleado. En inventario, la creación y anulación de ajustes abiertos ya están
implementadas: se identifica al responsable a partir de la sesión, el motivo
admite hasta 30 caracteres y ninguna de esas acciones modifica existencias.
En talento humano, el rol operativo puede crear empleados en PostgreSQL,
validando cédula no duplicada y departamento/cargo activos; la asignación del
cargo inicial y la auditoría se guardan en la misma transacción. Edición,
asignaciones posteriores de cargo y escrituras de cargas familiares continúan
bloqueadas y ocultas en la interfaz. La comprobación de cédula duplicada se
serializa entre solicitudes de la API, pero la tabla no tiene una restricción
única: otros clientes que escriban directamente en la base no quedan cubiertos.
La cuenta de API y RLS aún deben probarse antes de permitir esta escritura en
Supabase.
La creación, edición y cambio de estado de bancos están disponibles para roles
con permiso CREAR en contabilidad, como en la interfaz anterior. La API
serializa estas operaciones y comprueba duplicados, pero el
esquema todavía no impide que escrituras externas posteriores dupliquen un
nombre. Antes de permitir otros clientes de escritura se necesita revisar los
datos históricos y reforzar esa regla en la base. El bloqueo transaccional
requiere privilegio UPDATE sobre bancos además de SELECT e INSERT; la cuenta
de la API aún debe probarse con sus permisos y políticas RLS reales. Esos
privilegios de base no sustituyen la autorización por rol de la aplicación.
También se pueden crear cuentas contables MAY o DET con permiso CREAR.
El código debe ser nuevo: a diferencia de la operación anterior de MariaDB,
no se actualizan cuentas existentes ni sus saldos. El tipo correspondiente
debe existir en `tipo_cuenta`; la API no crea catálogos automáticamente.
Una prueba local con un rol restringido confirmó que los permisos de tabla
solos no bastan cuando faltan políticas RLS. Las políticas del rol de la API
ya están aplicadas en Supabase; la creación de cuentas aún requiere pruebas
funcionales con ese rol antes del despliegue.
La creación de asientos manuales abiertos valida cuentas activas de detalle,
montos cuadrados y una sola línea por cuenta, y registra cabecera y líneas
con auditoría en una transacción. No contabiliza ni cambia saldos. Aprobar,
anular y corregir asientos permanece bloqueado en PostgreSQL; el origen de
asientos existentes aún no se distingue de forma fiable. La creación no tiene
clave de idempotencia: si se pierde la respuesta, consulta el libro diario
antes de reintentar. El bloqueo de las cuentas exige SELECT y UPDATE y una
política RLS de UPDATE aplicable además de la de SELECT: sin ella la consulta
de bloqueo no ve las filas aun cuando una consulta normal sí las vea. Se
comprobó en la copia aislada una política temporal con `USING (true)` y
`WITH CHECK (false)`, sin aplicarla a Supabase; hay que revisar los permisos
efectivos y otras políticas antes de adoptar cualquier configuración.
La aprobación de ajustes sigue bloqueada: el disparador original suma incluso las salidas
y crea un asiento pendiente sin detalle. Debe corregirse y probarse el impacto
contable antes de habilitarla. La creación aún no tiene clave de idempotencia:
si se pierde la respuesta, consulta el historial antes de reintentar.
Las restantes operaciones de escritura de estos módulos todavía no están
migradas y continúan bloqueadas con 503. La selección completa de
departamentos para centros de costos requiere permiso de lectura de talento
humano; sin él se muestran únicamente los departamentos asociados a centros
existentes y se informa que el catálogo está incompleto.
Los conceptos de bonificaciones y descuentos permiten creación, edición y
reactivación por el rol operativo y desactivación por el jefe de talento
humano. No se puede desactivar un concepto mediante la ruta de edición. El
nombre tiene un máximo de 40 caracteres en PostgreSQL; los nuevos conceptos se
crean activos. La API serializa creaciones y ediciones, pero las escrituras
externas posteriores pueden duplicar nombres. El bloqueo
requiere privilegios y políticas RLS adecuados para la cuenta API; aún no se
han validado en Supabase.
También se pueden crear roles de pago abiertos para empleados activos, con
detalle de conceptos, totales verificados y auditoría transaccional. Los
conceptos deben estar activos y los importes se acumulan por código y fecha
para respetar las claves compuestas existentes. El jefe de talento humano puede
anular roles abiertos sin afectar la contabilidad; editar y eliminar
permanecen bloqueados. Se preparó una migración PostgreSQL de aprobación con
la regla anterior de MariaDB, elegida por el usuario: sueldo más bonos se
registran como gasto y deuda, sin separar los descuentos. Selecciona cuentas
activas de detalle por descripción o prefijos y un centro de costo activo del
departamento; genera un asiento pendiente sin actualizar saldos. Se probó
únicamente en una copia local. Hasta revisar y aplicar la migración en Supabase,
comprobar las cuentas y RLS reales y activar `PAYROLL_APPROVAL_ENABLED=true`,
la aprobación permanece deshabilitada. La operación de
creación no tiene clave de idempotencia. Las pruebas locales se hicieron como
propietario del esquema; los privilegios y políticas RLS de las tablas de
nómina aún deben revisarse con la cuenta API real antes de cualquier despliegue.
La creación, aprobación y anulación de compras y la confirmación de
recepciones están conectadas a PostgreSQL y respetan la matriz de roles:
Auxiliar aprueba y Jefe anula; Operativo no puede ejecutar esas acciones.
La aprobación genera la recepción pendiente mediante la lógica existente de
la base. El código de los endpoints y la matriz se validan con pruebas, pero
las operaciones requieren la migración SQL de compras descrita abajo y aún no
se han probado contra la base real. No las uses en Supabase hasta aplicar esa
migración y validar allí los procedimientos, triggers y permisos necesarios.
También se implementaron la creación, aprobación y anulación de ventas y la
confirmación acumulada de entregas parciales en la copia aislada. Requieren
la migración de ventas y una clave de idempotencia para crear facturas.
La venta descuenta el stock al facturar y usa la tasa de IVA del documento.
La aprobación genera un asiento pendiente sin líneas; no constituye una
contabilización completa. Las facturas históricas no conciliadas no se pueden
aprobar ni anular mediante esta nueva ruta.
La autorización se comprueba por módulo y acción según los roles activos en
cada solicitud. Las operaciones que todavía
dependen de MariaDB responden con error 503, en lugar de conectarse
silenciosamente a otra base.
Además, el middleware PostgreSQL ahora permite pasar solo los pares
ruta/método que ya tienen una implementación PostgreSQL; las rutas administrativas
de escritura, catálogos generales y otras operaciones aún no migradas responden
503 y no alcanzan las funciones MariaDB.

Los catálogos ya no crean unidades predeterminadas al hacer un GET en
PostgreSQL: devuelven una lista vacía si no existen unidades, para evitar que
un rol de lectura modifique datos. El catálogo general solo devuelve las
secciones correspondientes a los módulos autorizados. Las solicitudes GET
registran auditoría; por ello una llamada HTTP no es una prueba de solo
lectura aunque la consulta del catálogo lo sea.

`DATABASE_URL` y `POSTGRES_SSL_ROOT_CERT` configuran la conexión verificada.
El certificado debe provenir del proveedor; no publiques la URL ni la clave.
Si `DATABASE_BACKEND` no está configurado, la API continúa usando MariaDB.
La autorización implementada corresponde al backend PostgreSQL; no protege
los endpoints de MariaDB. El cierre de sesión PostgreSQL revoca únicamente el
token presentado y exige la migración `20261108_sesiones_postgresql.sql`,
con permisos de tabla explícitos para la cuenta de la API. Sin ella, las
solicitudes protegidas fallan de forma cerrada. La interfaz informa si no
se puede revocar y mantiene la sesión local para poder reintentar.
Si el servidor responde que la sesión ya no es válida (401), la interfaz
elimina la sesión local para permitir un nuevo inicio.
El registro, muchos listados y varias operaciones de negocio aún no están
migrados. En PostgreSQL solo se permiten explícitamente las combinaciones de
ruta y método implementadas; el resto falla de forma cerrada con 503. La
configuración de Render no habilita esas operaciones ni equivale a una
validación de producción.
La herramienta local `restablecer_contrasena.py` rechaza explícitamente
PostgreSQL; todavía no restablece contraseñas ni invalida todas las sesiones.

Se detectaron incompatibilidades en el esquema de Supabase: al crear una
compra con subtotal de 20, el procedimiento y el trigger dejaron subtotal
de 40; al facturar y confirmar una entrega de dos unidades, el stock bajó
dos veces. Para compras se preparó
`migrations/20261108_compras_postgresql.sql`, que conserva los importes
históricos, estima la tasa de IVA histórica desde esos importes y corrige el
recálculo. La migración ya está aplicada en Supabase. En la copia local se
verificaron tasas de 0 %, 12,5 % y 15 %, concurrencia y reversión ante fallos.
La migración `migrations/20261108_ventas_postgresql.sql` también se aplicó en
Supabase y no debe repetirse. Cambia triggers y bloquea rutas anteriores de
aprobación y anulación; sigue pendiente conciliar facturas históricas.
`ventas_control` utiliza RLS con políticas de lectura,
inserción y actualización; dichas políticas no otorgan privilegios de tabla.
Se validó en una copia local que un rol no propietario puede usarla con esos
privilegios explícitos. Otros procesos siguen requiriendo trabajo antes del
despliegue.

Como validación local se exportó únicamente el esquema `public` de Supabase con
TLS verificado, sin filas de datos. En PostgreSQL aislado se aplicaron las
migraciones de compras, ventas, sesiones y DBA limitado; la matriz se probó
con roles y permisos sintéticos. La suite API completa pasó 92 pruebas. Esto
valida la sintaxis y los flujos sobre el esquema clonado, pero no verifica los
privilegios/RLS de la cuenta real de la API ni equivale a una autorización
para ejecutar los scripts en Supabase.

La inspección inicial del catálogo encontró 41 tablas con RLS sin políticas
y una cuenta administrativa propietaria con `BYPASSRLS`. Después se aplicaron
las migraciones y se creó una cuenta dedicada. **No conectes la API con la
cuenta administrativa ni asignes el rol DBA limitado a la API.**
La conexión ahora falla cerrada si el rol configurado es superusuario, tiene
`BYPASSRLS`, puede crear roles o bases, puede crear objetos en `public`, o es
propietario o miembro de roles propietarios de objetos de ese esquema. Esta
comprobación evita usar por error la identidad privilegiada actual; no concede
privilegios ni reemplaza la prueba de las políticas y operaciones con el rol
dedicado.

Se preparó `migrations/20261108_api_role_rls_postgresql.sql` para crear un rol
de grupo sin LOGIN. Concede lectura de las 43 tablas que usan los módulos
PostgreSQL, inserción/actualización solo en las tablas escritas por esos
handlers y EXECUTE en los cuatro procedimientos de compras y su helper de
auditoría `sp_registrar_log`; no concede DELETE, secuencias ni DDL. Las
políticas RLS permiten al rol dedicado todas
las filas de esas tablas: la autorización por rol/módulo se mantiene en la
API. El administrador creó una cuenta LOGIN no privilegiada con membresía
heredada. Las migraciones de compras, ventas, sesiones y rol de API se
aplicaron en Supabase; no se deben repetir sin revisar su estado.

La cuenta dedicada se conectó con TLS verificado y, en modo de solo lectura,
consultó las 43 tablas con RLS habilitado y comprobó EXECUTE en los cinco
procedimientos. En una copia local aislada del esquema actualizado, con
privilegios efectivos equivalentes y datos ficticios, pasaron los flujos de
compras y ventas, recepción, entrega, anulación, idempotencia y auditoría.
También se probó la matriz HTTP de ventas con roles simulados y se rechazaron
DELETE y CREATE. Pasaron 24 pruebas focalizadas. No se han ejecutado pruebas
de escritura en Supabase, ni se ha desplegado en Render; otros módulos y la
conciliación contable siguen pendientes.

Para ejecutar las pruebas de integración, utiliza exclusivamente una instancia
PostgreSQL local aislada con una base llamada `licoreria_api_test`.
Instala las dependencias de `requirements.txt` y `tests/requirements.txt`,
configura `LICORERIA_TEST_POSTGRES_DSN` para esa instancia y ejecuta
`python -m unittest discover -s tests -v` desde `API`. Las pruebas crean y
eliminan esquemas temporales; nunca las apuntes a Supabase ni a una base real.
La prueba de compatibilidad de consultas necesita una copia del esquema real
sin datos en `public`, con la migración de compras aplicada. Las pruebas de ventas también requieren
`pg_dump` en `PATH` y crean esquemas temporales. Sin esa variable,
las pruebas de integración se omiten.

## Estado y advertencia

El backend PostgreSQL comprueba en el servidor las rutas/métodos permitidos y
los roles activos, y rechaza las operaciones no migradas; esto no completa la
migración funcional. La suite local pasó 117 pruebas con la base aislada
`licoreria_api_test`, pero no se probaron escrituras contra Supabase. Antes de
operar con datos reales todavía se deben validar los permisos/RLS efectivos,
las cuentas y los flujos habilitados. La API no ofrece el asistente de creación
del primer administrador en PostgreSQL: debe existir previamente un usuario
administrador activo y sus roles deben estar configurados.

HeidiSQL seguirá siendo un cliente de administración y puede conectarse a una
base remota, pero no es el servidor de base de datos.

La base local inspeccionada es MariaDB 12.3.2: 41 tablas, 25 vistas,
27 procedimientos, 5 funciones y 130 disparadores. Una migración que copie
solo las tablas no es suficiente. Hay que probar los objetos y sus
`DEFINER` con los permisos del proveedor de destino.

## Referencia obsoleta: Layerbase/MariaDB

Las siguientes instrucciones correspondían a una alternativa que ya no es el
destino elegido. No crees una instancia en Layerbase ni sigas estos pasos para
desplegar la aplicación. La migración actual es a Supabase/PostgreSQL.

Los pasos de creación de cuenta, importación de datos y despliegue de esa
alternativa quedan retirados. La base local no se ha modificado por esta guía.

## Preparación para Render

El archivo `../render.yaml` define la API FastAPI y el frontend estático como
servicios de un Blueprint. La API usa `/readyz` como comprobación de salud:
verifica TLS, el rol PostgreSQL permitido y una consulta simple. En producción
la aplicación falla al iniciar si faltan el backend PostgreSQL, el secreto de
sesión, el certificado CA o `CORS_ORIGINS`. El Blueprint genera
`AUTH_TOKEN_SECRET` y solicita `DATABASE_URL` y `CORS_ORIGINS` en Render.

Para crear el Blueprint, configura en Render:

1. `DATABASE_URL` con la URL TLS de la cuenta dedicada de la API; nunca uses la
   cuenta administrativa ni el rol DBA limitado.
2. El archivo secreto `supabase-ca.crt` con la CA oficial del proveedor en la
   ruta `/etc/secrets/supabase-ca.crt`. No subas el `.env` al repositorio.
3. `CORS_ORIGINS` con el origen HTTPS exacto que Render asigne al frontend,
   sin ruta final ni comodines.
4. Confirma que la base ya tenga un administrador activo. El endpoint de
   configuración inicial sigue siendo exclusivo de MariaDB.

La URL de la API se enlaza automáticamente al frontend como host HTTPS. Si
`/readyz` no queda saludable, no habilites tráfico. Empieza con datos de prueba:
no se debe considerar este despliegue como validación de escrituras/RLS en
Supabase ni como migración completa. Las funciones no soportadas continúan
respondiendo 503.
