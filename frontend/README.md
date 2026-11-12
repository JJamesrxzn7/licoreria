# Documentos comerciales en PDF

En Ventas, abra el detalle de una factura y seleccione **Descargar PDF**. En
Órdenes de compra, Recepciones y Entregas, la descarga está en el historial.
El PDF se genera en el navegador con los datos cargados de la aplicación,
incluye el estado y, si existe, el detalle. Las cantidades de recepciones y
entregas sin confirmar se indican como tales; no incluyen cambios aún no
guardados en el formulario. Los documentos no son comprobantes electrónicos
ni tienen autorización SRI. No se inventan datos del emisor o tributarios.

Para verificar la generación: `npm run test:pdf` (Node.js 22.6 o posterior,
con soporte de eliminación de tipos TypeScript) y `npm run build`.

## Acceso por módulos

El menú usa los permisos de lectura por módulo devueltos en el inicio de
sesión. Esta restricción de la interfaz no garantiza la autorización de la
API: todavía falta aplicar y verificar las reglas de crear, aprobar y anular
en todos los endpoints. No debe exponerse la API a usuarios no confiables
hasta completar esa protección.
