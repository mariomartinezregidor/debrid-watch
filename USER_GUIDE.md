# Guía de usuario de DebridWatch

DebridWatch te ayuda a consultar cuándo caduca tu suscripción y te avisa cerca de la fecha para que puedas renovarla a tiempo. Admite Real-Debrid, TorBox, AllDebrid, Premiumize, Debrid-Link, Offcloud y put.io.

## Empezar

1. Abre el bot y envía `/start`. Verás botones para TorBox, Real-Debrid, AllDebrid, Premiumize, Debrid-Link, Offcloud, put.io, consultar caducidades y gestionar tus servicios.
2. Pulsa el servicio. Si todavía no está configurado, elige **➕ Añadir API Key**.
3. En la pantalla de espera, pulsa **🔗 Abrir formulario seguro**. Escribe la API Key allí y pulsa Guardar.
4. Vuelve a Telegram y pulsa **🔄 Ya la he guardado**. Si hace falta, **🔗 Reenviar enlace** genera un enlace nuevo; el anterior deja de servir.

Las pantallas se navegan con botones: **🔙 Volver** regresa a la pantalla anterior y **🏠 Menú principal** vuelve al inicio. **❌ Cancelar** abandona el flujo actual. Los comandos `/start`, `/caducidad` y `/mis_servicios` también muestran sus opciones con botones.

El bot nunca te pide que pegues la API Key en el chat. Los chats pueden conservarse en el historial de Telegram; el formulario protegido por HTTPS evita que la clave quede en esa conversación. El enlace es personal, de un solo uso y caduca a los 10 minutos. Si caduca, vuelve a pedir uno desde `/start`.

## Dónde conseguir tu API Key

- **Real-Debrid:** inicia sesión en el sitio oficial y consulta la sección de API/gestión de aplicaciones de tu cuenta.
- **TorBox:** inicia sesión en el sitio o aplicación oficial y busca la sección de API Keys en la configuración de tu cuenta.
- **AllDebrid:** inicia sesión en el sitio oficial y consulta la sección de API/gestión de claves de tu cuenta.
- **Premiumize:** inicia sesión y busca la API Key en la sección de cuenta del sitio oficial.
- **Debrid-Link:** genera una Private API Key desde la gestión de claves/API de tu cuenta oficial.
- **Offcloud:** consulta la API Key en los ajustes de tu cuenta oficial de Offcloud.
- **put.io:** crea o copia un access token desde la configuración de API/aplicaciones de tu cuenta oficial.

Usa únicamente las páginas oficiales. No compartas la clave con otras personas ni la envíes por el chat del bot.

## Consultar y administrar

- Envía `/caducidad` o pulsa **📅 ¿Cuándo caduca?**. Elige un servicio configurado o **📋 Ver todos**.
- La respuesta muestra la fecha y hora en formato `DD/MM/YYYY HH:mm` (UTC) y los días restantes.
- Envía `/mis_servicios` o pulsa **⚙️ Mis servicios**. Elige un servicio para abrir su detalle.
- En el detalle puedes consultar su caducidad, **🔄 Actualizar API Key** o **🗑️ Eliminar API Key**. El borrado siempre pide confirmación con **✅ Sí, eliminar**; **❌ Cancelar** vuelve al detalle sin borrar nada.

El bot realiza una comprobación automática diaria. Solo envía avisos a 7, 3 y 1 día, y un aviso cuando la suscripción caduca. No repite el mismo aviso cada día; una renovación permite avisos para el nuevo periodo. Si el proveedor no responde o limita las consultas, no recibirás avisos de esos errores.

## Si una clave deja de funcionar

Si recibes un aviso de clave inválida, abre `/mis_servicios`, entra al servicio, pulsa **🔄 Actualizar API Key** y pega la clave vigente en el formulario HTTPS. No la envíes por Telegram.

## Eliminar tus datos

Entra en **⚙️ Mis servicios**, elige el servicio, pulsa **🗑️ Eliminar API Key** y confirma con **✅ Sí, eliminar**. Dejarás de recibir avisos de ese servicio. Para solicitar el borrado de cualquier dato restante, contacta al administrador del bot. También puedes revocar la API Key desde el proveedor correspondiente.
