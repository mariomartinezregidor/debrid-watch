# DebridWatch

Bot multiusuario de Telegram para consultar y vigilar la caducidad de cuentas de Real-Debrid, TorBox y AllDebrid. Cada credencial pertenece exclusivamente al `telegram_user_id` que la configuró; se valida antes de guardarse y se cifra con Fernet.

## Requisitos

- VPS Linux con Python 3.11 o superior, acceso saliente a Telegram y a los tres proveedores.
- Dominio apuntado al VPS y HTTPS válido para el formulario web. **No recojas API Keys a través de HTTP público.**
- Una cuenta/bot creado con [@BotFather](https://t.me/BotFather).

## 1. Crear el bot y preparar secretos

En Telegram, habla con `@BotFather`, ejecuta `/newbot`, usa el nombre **DebridWatch** y el handle disponible `@DebridWatchBot`. BotFather entrega un token para la Bot API.

El token **no se pone en el código**, no se copia en este README y **nunca se sube al repositorio**. Se guarda únicamente en `.env` en el VPS. Lo mismo aplica a `FERNET_KEY`.

```bash
git clone <URL_DEL_REPOSITORIO> debrid-watch
cd debrid-watch
cp .env.example .env
chmod 600 .env
```

Genera una clave Fernet nueva:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Guárdala en un gestor de contraseñas y en una copia de seguridad protegida. **Si se pierde, las API Keys cifradas de la base de datos serán irrecuperables; si se filtra, todas podrán descifrarse.** No generes una clave nueva en una instalación existente sin migrar/re-cifrar las credenciales.

Edita `.env` en el VPS, sustituyendo los valores de ejemplo:

```dotenv
TELEGRAM_BOT_TOKEN=PEGA_AQUI_EL_TOKEN_ENTREGADO_POR_BOTFATHER
FERNET_KEY=PEGA_AQUI_LA_CLAVE_FERNET_GENERADA
WEB_FORM_BASE_URL=https://expired.debrid.watch
WEB_FORM_PORT=8085
SCHEDULER_HOUR_UTC=8
LOG_LEVEL=INFO
DATABASE_PATH=/opt/debrid-watch/debrid_watch.sqlite3
```

`WEB_FORM_BASE_URL` es la URL HTTPS pública que abrirá el usuario. `WEB_FORM_PORT` es el puerto local al que se enlaza FastAPI, normalmente detrás del proxy. El job diario se ejecuta a la hora UTC indicada (0–23). `DATABASE_PATH` puede ser relativo o absoluto. `.env` y las bases SQLite están excluidos por `.gitignore`.

## 2. Instalar y probar localmente

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Con `WEB_FORM_BASE_URL` en HTTPS el enlace generado ya apunta a ese dominio; por eso la prueba integral del formulario requiere un proxy y un certificado válidos. Para pruebas aisladas se permite `http://localhost:8085`, pero nunca expongas esa configuración en Internet. La raíz no ofrece un formulario genérico (responde 404): abre desde Telegram el enlace privado `/key/<token>` generado para tu cuenta.

Las pruebas automatizadas se ejecutan con `python -m unittest discover -s tests -v`.

## 3. HTTPS para el formulario (obligatorio)

El proceso escucha únicamente en `127.0.0.1:WEB_FORM_PORT`; publícalo solo a través de Caddy o Nginx. Configura el DNS A/AAAA del dominio y permite 80/443 en el firewall. No abras el puerto del formulario en el firewall.

### Caddy (opción sencilla)

Instala Caddy y añade a `/etc/caddy/Caddyfile`:

```caddy
expired.debrid.watch {
    reverse_proxy 127.0.0.1:8085
}
```

Caddy obtiene y renueva el certificado automáticamente. Valida y recarga con `sudo caddy validate --config /etc/caddy/Caddyfile` y `sudo systemctl reload caddy`.

### Nginx + Certbot

Instala Nginx/Certbot. Crea un virtual host con proxy a `127.0.0.1:8085`, por ejemplo:

```nginx
server {
    listen 80;
    server_name expired.debrid.watch;
    location / {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 16k;
        # Los enlaces /key/<token> son secretos de un solo uso: no registrar su URI.
        access_log off;
    }
}
```

Después de validar/recargar Nginx, ejecuta `sudo certbot --nginx -d expired.debrid.watch` y comprueba la renovación automática. Ajusta `WEB_FORM_BASE_URL` a `https://expired.debrid.watch`. No habilites registros de acceso que capturen la ruta completa `/key/<token>`: el token permite abrir temporalmente el formulario.

## 4. Despliegue con systemd

El repositorio incluye `debrid-watch.service`. Revisa y ajusta `User`, `Group` y `WorkingDirectory` según la ubicación de tu VPS; este ejemplo espera `/opt/debrid-watch` y el usuario/grupo `debridwatch`.

```bash
sudo useradd --system --home /opt/debrid-watch --shell /usr/sbin/nologin debridwatch
sudo mkdir -p /opt/debrid-watch
sudo chown -R debridwatch:debridwatch /opt/debrid-watch
# Clona el repositorio allí (o copia el checkout ya preparado).
sudo -u debridwatch git clone <URL_DEL_REPOSITORIO> /opt/debrid-watch
sudo -u debridwatch cp /opt/debrid-watch/.env.example /opt/debrid-watch/.env
# Edita .env con los valores reales y protege el archivo.
sudo chown debridwatch:debridwatch /opt/debrid-watch/.env
sudo chmod 600 /opt/debrid-watch/.env
cd /opt/debrid-watch
sudo -u debridwatch python3.11 -m venv .venv
sudo -u debridwatch .venv/bin/pip install -r requirements.txt
sudo cp debrid-watch.service /etc/systemd/system/debrid-watch.service
sudo systemctl daemon-reload
sudo systemctl enable --now debrid-watch
sudo systemctl status debrid-watch
sudo journalctl -u debrid-watch -f
```

El servicio escribe logs rotativos en `debrid-watch.log` y también en el journal. Nunca registra API Keys ni tokens del formulario; desactiva también el access log del proxy para las rutas del formulario.

## 5. Verificación

```bash
sudo systemctl is-active debrid-watch
sudo journalctl -u debrid-watch --since today
# La raíz del dominio debe responder 404; prueba el formulario con un enlace /key/<token> del bot.
curl -i https://expired.debrid.watch/
```

Envía `/start` al bot, selecciona un servicio y comprueba que el botón abre el formulario bajo HTTPS. Tras una clave válida, el bot confirma el alta. Una clave inválida se rechaza sin guardarse y el formulario permite reintentar mientras el enlace siga vigente. También puedes abrir los documentos desde los botones informativos de `/start`.

## 6. Copias de seguridad y actualización

Detén brevemente el servicio o usa la API de backup de SQLite para asegurar una copia consistente. Para instalaciones pequeñas:

```bash
sudo systemctl stop debrid-watch
sudo cp /opt/debrid-watch/debrid_watch.sqlite3 /ruta/segura/debrid_watch-$(date +%F).sqlite3
sudo systemctl start debrid-watch
```

Guarda aparte una copia cifrada de `FERNET_KEY` (idealmente en gestor de secretos/contraseñas). Protege y cifra ambas copias; una base sin su clave no sirve para recuperar credenciales. Prueba periódicamente la restauración. No guardes la copia de `.env` en el repo.

Para actualizar:

```bash
cd /opt/debrid-watch
sudo -u debridwatch git pull --ff-only
sudo -u debridwatch .venv/bin/pip install -r requirements.txt
sudo systemctl restart debrid-watch
sudo journalctl -u debrid-watch -f
```

## Documentación para usuarios

- [Guía del usuario](USER_GUIDE.md)
- [Privacidad y cifrado](PRIVACY.md)

Pagos y multi-idioma quedan fuera del alcance actual.
