"""Punto de entrada de DebridWatch: bot Telegram y formulario web."""

from __future__ import annotations

import asyncio
import logging
import signal
from logging.handlers import RotatingFileHandler

import uvicorn
from telegram.ext import Application

from config import load_settings
from crypto import KeyCipher
from database import Database
from handlers import callbacks, queries, services_menu, start
from scheduler_jobs import configure_scheduler
from services import SERVICE_CLASSES
from web_form.app import create_web_app


def configure_logging(level: str) -> None:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    rotating = RotatingFileHandler("debrid-watch.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    rotating.setFormatter(formatter)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(rotating)
    # No registrar el path de los enlaces one-shot que contiene el token.
    logging.getLogger("uvicorn.access").disabled = True
    # HTTPX puede incluir en el log la URL de la Bot API, cuyo path contiene
    # TELEGRAM_BOT_TOKEN. Mantener esos loggers en WARNING evita ese riesgo.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def run() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("debridwatch")
    db = Database(settings.database_path)
    await db.initialize()
    cipher = KeyCipher(settings.fernet_key)
    providers = {name: service_class() for name, service_class in SERVICE_CLASSES.items()}
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data.update({"settings": settings, "db": db, "cipher": cipher, "providers": providers})
    start.register(application)
    services_menu.register(application)
    queries.register(application)
    callbacks.register(application)
    configure_scheduler(application, settings.scheduler_hour_utc)

    web_app = create_web_app()
    web_app.state.db = db
    web_app.state.cipher = cipher
    web_app.state.providers = providers
    web_app.state.bot = application.bot
    server = uvicorn.Server(uvicorn.Config(
        # Solo el proxy local termina TLS; no exponer el formulario en HTTP público.
        web_app, host="127.0.0.1", port=settings.web_form_port, log_level=settings.log_level.lower(),
        access_log=False, server_header=False,
    ))
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    initialized = False
    try:
        await application.initialize()
        initialized = True
        await application.start()
        if application.updater is None:
            raise RuntimeError("No se pudo inicializar el polling de Telegram")
        await application.updater.start_polling(drop_pending_updates=False)
        web_task = asyncio.create_task(server.serve(), name="debridwatch-web")
        stop_task = asyncio.create_task(stop_event.wait(), name="debridwatch-stop")
        logger.info("DebridWatch iniciado; formulario en puerto %s", settings.web_form_port)
        try:
            done, _ = await asyncio.wait([stop_task, web_task], return_when=asyncio.FIRST_COMPLETED)
            if web_task in done and not server.should_exit:
                exception = web_task.exception()
                if exception:
                    raise exception
                raise RuntimeError("El servidor web se detuvo inesperadamente")
            server.should_exit = True
            await asyncio.gather(web_task, return_exceptions=True)
        finally:
            if not stop_task.done():
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)
    finally:
        try:
            if application.updater and application.updater.running:
                await application.updater.stop()
            if application.running:
                await application.stop()
            if initialized:
                await application.shutdown()
        finally:
            await asyncio.gather(*(provider.close() for provider in providers.values()), return_exceptions=True)
            logger.info("DebridWatch detenido")


if __name__ == "__main__":
    # TODO: pagos y multi-idioma quedan fuera del alcance de esta versión.
    asyncio.run(run())
