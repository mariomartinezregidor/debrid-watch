"""Formulario web: los secretos solo se reciben por HTTPS y nunca se registran."""

from __future__ import annotations

import html
import logging
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from crypto import KeyCipher
from services import AuthenticationError, ProviderError, SERVICE_CLASSES, SERVICE_LABELS

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


def _page(title: str, body: str, *, status: int = 200) -> HTMLResponse:
    content = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:34rem;margin:4rem auto;padding:0 1rem;color:#18212b}}
main{{border:1px solid #d9e0e7;border-radius:12px;padding:1.5rem}}label,input,button{{display:block;width:100%;box-sizing:border-box}}
input{{padding:.8rem;margin:.5rem 0 1rem}}button{{padding:.8rem;background:#146c43;color:white;border:0;border-radius:6px;font-weight:600}}
.hint{{color:#52606d;font-size:.92rem}}</style></head><body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>"""
    return HTMLResponse(content, status_code=status, headers={
        "Cache-Control": "no-store, max-age=0", "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
    })


def create_web_app() -> FastAPI:
    app = FastAPI(title="DebridWatch key form", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health", response_class=PlainTextResponse)
    async def health() -> str:
        return "ok"

    @app.get("/docs/{document}")
    async def documentation(document: str) -> Response:
        if document not in {"USER_GUIDE.md", "PRIVACY.md"}:
            return PlainTextResponse("No encontrado", status_code=404)
        path = ROOT / document
        if not path.is_file():
            return PlainTextResponse("Documento no disponible", status_code=404)
        return Response(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8",
                        headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})

    @app.get("/key/{token}", response_class=HTMLResponse)
    async def key_form(token: str, request: Request) -> Response:
        db = request.app.state.db
        import hashlib
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with aiosqlite.connect(db.path) as connection:
            row = await (await connection.execute(
                "SELECT service_name, expires_at FROM key_tokens WHERE token_hash=?", (digest,)
            )).fetchone()
        from database import dt_from_db, utcnow
        if not row or not dt_from_db(row[1]) or dt_from_db(row[1]) <= utcnow():
            return _page("Enlace caducado", "<p>Este enlace ya se usó o ha caducado. Vuelve al bot y solicita uno nuevo.</p>", status=410)
        service = SERVICE_LABELS.get(row[0])
        if not service:
            return _page("Enlace no válido", "<p>Solicita un enlace nuevo desde el bot.</p>", status=404)
        body = f"""<p>Introduce tu API Key de <strong>{html.escape(service)}</strong>. Se validará con el proveedor y se guardará cifrada.</p>
<form method="post" autocomplete="off"><label for="api_key">API Key</label>
<input id="api_key" name="api_key" type="password" required minlength="4" maxlength="4096" autocomplete="new-password" spellcheck="false">
<button type="submit">Validar y guardar</button></form>
<p class="hint">No envíes esta clave por Telegram. El enlace caduca a los 10 minutos y solo puede utilizarse una vez.</p>"""
        return _page(f"Configurar {service}", body)

    @app.post("/key/{token}", response_class=HTMLResponse)
    async def save_key(token: str, request: Request) -> Response:
        db = request.app.state.db
        import hashlib
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with aiosqlite.connect(db.path) as connection:
            row = await (await connection.execute(
                "SELECT service_name, expires_at FROM key_tokens WHERE token_hash=?", (digest,)
            )).fetchone()
        from database import dt_from_db, utcnow
        if not row or not dt_from_db(row[1]) or dt_from_db(row[1]) <= utcnow():
            return _page("Enlace caducado", "<p>Este enlace ya se usó o ha caducado. Solicita uno nuevo desde el bot.</p>", status=410)
        service_name = row[0]
        # FormData no se registra; no incluir excepciones/cuerpo en logs.
        try:
            form = await request.form()
            api_key = str(form.get("api_key", "")).strip()
        except Exception:
            return _page("Formulario no válido", "<p>No se pudo leer el formulario. Inténtalo de nuevo.</p>", status=400)
        if len(api_key) < 4 or len(api_key) > 4096 or "\x00" in api_key:
            return _page("Clave no válida", "<p>La clave está vacía o tiene un formato no válido. El enlace sigue disponible.</p>", status=400)
        try:
            expiration = await request.app.state.providers[service_name].get_expiration(api_key)
        except AuthenticationError:
            return _page("API Key rechazada", "<p>El servicio no aceptó la clave. Comprueba que sea correcta y prueba otra vez; el enlace sigue disponible.</p>", status=400)
        except ProviderError as exc:
            logger.warning("No se pudo validar una clave del formulario: servicio=%s tipo=%s", service_name, type(exc).__name__)
            return _page("No se pudo validar", "<p>El proveedor no respondió correctamente. Espera un momento e inténtalo otra vez.</p>", status=502)
        except Exception:
            logger.exception("Error inesperado validando clave del formulario: servicio=%s", service_name)
            return _page("Error temporal", "<p>No se pudo validar la clave. Inténtalo de nuevo.</p>", status=502)
        encrypted = request.app.state.cipher.encrypt(api_key)
        # Reducir referencias al secreto cuanto antes; no se incluye en respuestas ni logs.
        del api_key
        user_id = await db.save_key_from_token(token, service_name, encrypted, expiration)
        if user_id is None:
            return _page("Enlace caducado", "<p>El enlace se usó en otra solicitud o ha caducado. Solicita uno nuevo en el bot.</p>", status=410)
        try:
            await request.app.state.bot.send_message(
                user_id, f"✅ La API Key de {SERVICE_LABELS[service_name]} se validó y guardó de forma cifrada."
            )
        except Exception:
            logger.exception("No se pudo notificar al usuario tras guardar la clave: servicio=%s", service_name)
        return _page("Configuración completada", f"<p>Tu cuenta de {html.escape(SERVICE_LABELS[service_name])} se validó y guardó correctamente.</p><p>Ya puedes cerrar esta página y consultar <code>/caducidad</code> en Telegram.</p>")

    return app
