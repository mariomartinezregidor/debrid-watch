# Guía de usuario de DebridWatch

DebridWatch te ayuda a consultar cuándo caduca tu suscripción de Real-Debrid, TorBox o AllDebrid y te avisa cerca de la fecha para que puedas renovarla a tiempo.

## Empezar

1. Abre el bot y envía `/start`.
2. Elige **Configurar un servicio** y selecciona el proveedor.
3. Pulsa el botón que abre el **formulario seguro**. Escribe la API Key allí y envía el formulario.
4. El bot validará la clave con el proveedor y te confirmará si quedó guardada.

El bot nunca te pide que pegues la API Key en el chat. Los chats pueden conservarse en el historial de Telegram; el formulario protegido por HTTPS evita que la clave quede en esa conversación. El enlace es personal, de un solo uso y caduca a los 10 minutos. Si caduca, vuelve a pedir uno desde `/start`.

## Dónde conseguir tu API Key

- **Real-Debrid:** inicia sesión en el sitio oficial y consulta la sección de API/gestión de aplicaciones de tu cuenta.
- **TorBox:** inicia sesión en el sitio o aplicación oficial y busca la sección de API Keys en la configuración de tu cuenta.
- **AllDebrid:** inicia sesión en el sitio oficial y consulta la sección de API/gestión de claves de tu cuenta.

Usa únicamente las páginas oficiales. No compartas la clave con otras personas ni la envíes por el chat del bot.

## Consultar y administrar

- Envía `/caducidad` o pulsa **¿Cuándo caduca?** para consultar un servicio o usar **Ver todos**.
- La respuesta muestra la fecha y hora en formato `DD/MM/YYYY HH:mm` (UTC) y los días restantes.
- Usa `/mis_servicios` para ver los servicios configurados. Desde allí puedes **actualizar** una clave (se abre otro formulario seguro) o **borrarla**.

El bot realiza una comprobación automática diaria. Solo envía avisos a 7, 3 y 1 día, y un aviso cuando la suscripción caduca. No repite el mismo aviso cada día; una renovación permite avisos para el nuevo periodo. Si el proveedor no responde o limita las consultas, no recibirás avisos de esos errores.

## Si una clave deja de funcionar

Si recibes un aviso de clave inválida, abre `/mis_servicios`, pulsa **Actualizar** y pega la clave vigente en el formulario HTTPS. El bot no volverá a avisarte repetidamente por la misma credencial hasta que la actualices.

## Eliminar tus datos

En `/mis_servicios`, pulsa **Borrar** junto a cada servicio y confirma. Esto elimina la API Key cifrada y los datos de caducidad de ese servicio. Para solicitar el borrado de cualquier dato restante, contacta al administrador del bot. También puedes revocar la API Key desde el proveedor correspondiente.
