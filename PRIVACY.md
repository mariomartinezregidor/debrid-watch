# Privacidad y cifrado

DebridWatch está diseñado para mantener separadas las cuentas de cada usuario. Las credenciales se asocian al identificador numérico de Telegram que las configuró; las consultas y avisos usan solo esa asociación.

## Datos utilizados

En la base de datos se guardan el `telegram_user_id`, el nombre del servicio, la API Key **cifrada**, la fecha de caducidad cacheada, la fecha de la última comprobación, el último umbral notificado y las fechas de creación/actualización. Para el formulario se conserva temporalmente el hash de un token de un solo uso, el servicio/usuario asociado y su expiración; se elimina al usarlo y los caducados se limpian al generar nuevos enlaces. El token vence a los 10 minutos.

El bot no pide ni guarda tu nombre, correo electrónico, contraseña del proveedor, historial de chats ni contenido de tus descargas. Los logs técnicos no contienen API Keys ni tokens del formulario; pueden registrar el nombre de un servicio y el tipo de error para diagnosticar fallos. Telegram, por su parte, administra sus propios mensajes y metadatos de chat de acuerdo con sus políticas.

## Cifrado

Las claves se cifran en el servidor con Fernet de `cryptography` (AES-128-CBC para confidencialidad y HMAC-SHA256 para integridad). La clave maestra `FERNET_KEY` vive en la configuración privada del servidor y no se envía a Telegram ni al proveedor. Quien opere el bot debe protegerla y respaldarla: perderla hace irrecuperables las API Keys cifradas; filtrarla permite descifrarlas.

Cuando es necesario consultar un proveedor, el proceso descifra la API Key en memoria para realizar la petición y no la escribe en claro en disco ni en los logs. El proceso no puede garantizar un borrado físico inmediato de la memoria de Python, por lo que limita las referencias al secreto una vez usado.

## Por qué el formulario y no el chat

Los mensajes pueden quedar en el historial de Telegram. DebridWatch genera un enlace aleatorio, de un solo uso y con caducidad de 10 minutos para un formulario web. El navegador envía la clave directamente al servidor mediante HTTPS; la clave no se incluye en el chat de Telegram. El formulario valida la clave con el proveedor antes de cifrarla y guardarla.

El enlace de configuración también es sensible hasta su uso o expiración: no lo reenvíes ni lo compartas. El operador del servidor debe evitar registrar la ruta completa `/key/<token>` en el proxy.

## Quién puede ver los datos

El administrador del VPS tiene acceso técnico a la base de datos y, si dispone de `FERNET_KEY`, podría descifrar las claves. Debes confiar en el operador del bot. El cifrado protege principalmente frente a la exposición aislada de una copia de la base de datos; no protege frente a un servidor comprometido mientras la aplicación está funcionando.

## Eliminación y retención

Los datos de una integración se eliminan desde `/mis_servicios` → **Borrar**. Puedes pedir al administrador que borre los datos asociados a tu cuenta y revocar la API Key en el propio servicio. Los datos se conservan hasta que tú solicites su eliminación; los tokens de configuración son la excepción temporal descrita arriba.
