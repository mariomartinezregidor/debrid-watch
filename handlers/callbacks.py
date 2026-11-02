"""Enrutador único de callbacks inline.

Contrato de ``callback_data`` (forma general ``pantalla:acción[:parámetro]``):

* ``menu:main`` — menú principal.
* ``svc:<servicio>[:acción[:origen]]`` — detalle, alta, actualización o borrado.
* ``query:<servicio|all|menu>[:origen]`` — consultas manuales.
* ``services:list`` — lista de integraciones del usuario.
* ``form:<check|resend>:<servicio>[:origen]`` — espera del formulario seguro.
* ``back:<pantalla>[:parámetros]`` y ``nav:cancel`` — navegación.

Servicios válidos: ``torbox``, ``real_debrid`` y ``alldebrid``. También se
aceptan los callback_data emitidos por versiones anteriores del bot.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from handlers import keyboards, screens
from handlers.queries import _query_one
from services import SERVICE_LABELS

logger = logging.getLogger(__name__)
_SERVICES = frozenset(SERVICE_LABELS)


class InvalidCallback(ValueError):
    """Callback inexistente o con datos fuera del contrato documentado."""


@dataclass(frozen=True, slots=True)
class CallbackRoute:
    screen: str
    action: str
    params: tuple[str, ...] = ()


def _legacy_data(data: str) -> str:
    """Traduce callbacks emitidos por botones que aún pueden estar en chats."""
    if data == "query_menu":
        return "query:menu"
    if data == "manage_menu":
        return "services:list"
    if data == "setup_menu":
        return "menu:main"
    parts = data.split(":")
    if len(parts) == 2 and parts[0] == "setup" and parts[1] in _SERVICES:
        return f"svc:{parts[1]}:add"
    if len(parts) == 3 and parts[0] == "service" and parts[2] in _SERVICES:
        if parts[1] == "update":
            return f"svc:{parts[2]}:update"
        if parts[1] == "delete":
            return f"svc:{parts[2]}:delete_confirm"
    # Este botón antiguo solo aparecía después de una confirmación explícita.
    if len(parts) == 2 and parts[0] == "delete_confirm" and parts[1] in _SERVICES:
        return f"svc:{parts[1]}:delete"
    return data


def parse_callback_data(data: str | None) -> CallbackRoute:
    """Valida y divide callback_data antes de que el router responda al callback."""
    if not data:
        raise InvalidCallback("callback_data vacío")
    parts = _legacy_data(data).split(":")
    screen = parts[0]

    if screen == "menu" and parts == ["menu", "main"]:
        return CallbackRoute("menu", "main")
    if screen == "services" and parts == ["services", "list"]:
        return CallbackRoute("services", "list")
    if screen == "nav" and parts == ["nav", "cancel"]:
        return CallbackRoute("nav", "cancel")

    if screen == "svc":
        if len(parts) < 2 or parts[1] not in _SERVICES:
            raise InvalidCallback("servicio desconocido")
        service = parts[1]
        if len(parts) == 2:
            return CallbackRoute("svc", "detail", (service, "menu"))
        if len(parts) == 3 and parts[2] == "from_services":
            return CallbackRoute("svc", "detail", (service, "services"))
        if len(parts) in {3, 4} and parts[2] in {"add", "update", "delete_confirm", "delete"}:
            origin = "menu"
            if len(parts) == 4:
                if parts[3] != "from_services":
                    raise InvalidCallback("origen desconocido")
                origin = "services"
            return CallbackRoute("svc", parts[2], (service, origin))
        raise InvalidCallback("acción de servicio desconocida")

    if screen == "query":
        if parts == ["query", "menu"]:
            return CallbackRoute("query", "menu")
        if parts == ["query", "all"]:
            return CallbackRoute("query", "all")
        if len(parts) in {2, 3} and parts[1] in _SERVICES:
            origin = parts[2] if len(parts) == 3 else "from_menu"
            if origin not in {"from_menu", "from_svc", "from_svc_services"}:
                raise InvalidCallback("origen de consulta desconocido")
            return CallbackRoute("query", "one", (parts[1], origin))
        raise InvalidCallback("consulta desconocida")

    if screen == "form":
        if len(parts) not in {3, 4} or parts[1] not in {"check", "resend"} or parts[2] not in _SERVICES:
            raise InvalidCallback("acción del formulario desconocida")
        origin = parts[3] if len(parts) == 4 else "menu"
        if origin not in {"menu", "from_services"}:
            raise InvalidCallback("origen del formulario desconocido")
        return CallbackRoute("form", parts[1], (parts[2], origin))

    if screen == "back":
        if parts == ["back", "menu"]:
            return CallbackRoute("back", "menu")
        if parts in (["back", "query", "menu"], ["back", "services", "list"]):
            return CallbackRoute("back", parts[1], (parts[2],))
        if len(parts) in {3, 4} and parts[1] == "svc" and parts[2] in _SERVICES:
            origin = parts[3] if len(parts) == 4 else "menu"
            if origin not in {"menu", "from_services"}:
                raise InvalidCallback("origen de retorno desconocido")
            return CallbackRoute("back", "svc", (parts[2], origin))
        raise InvalidCallback("destino de retorno desconocido")

    raise InvalidCallback("pantalla desconocida")


async def _show_main(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    base_url = context.application.bot_data["settings"].web_form_base_url
    await query.edit_message_text(
        screens.main_menu_text(), reply_markup=keyboards.main_menu_keyboard(base_url)
    )


async def _show_service(query, context: ContextTypes.DEFAULT_TYPE,
                        service_name: str, origin: str = "menu") -> None:
    item = await context.application.bot_data["db"].get_service(query.from_user.id, service_name)
    configured = item is not None
    back_data = "back:services:list" if origin == "services" else "back:menu"
    await query.edit_message_text(
        screens.service_detail_text(service_name, configured, item["expiration_date"] if item else None),
        reply_markup=keyboards.service_detail_keyboard(service_name, configured, back_data, origin),
    )


async def _show_services(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = await context.application.bot_data["db"].list_services(query.from_user.id)
    names = [item["service_name"] for item in services]
    await query.edit_message_text(
        screens.services_list_text(services), reply_markup=keyboards.services_list_keyboard(names)
    )


async def _show_query_menu(query, context: ContextTypes.DEFAULT_TYPE,
                           back_data: str = "back:menu") -> None:
    services = await context.application.bot_data["db"].list_services(query.from_user.id)
    names = [item["service_name"] for item in services]
    await query.edit_message_text(
        screens.query_menu_text(names), reply_markup=keyboards.query_menu_keyboard(names, back_data)
    )


async def _show_form_wait(query, context: ContextTypes.DEFAULT_TYPE,
                          service_name: str, origin: str) -> None:
    db = context.application.bot_data["db"]
    settings = context.application.bot_data["settings"]
    token, _expires = await db.issue_token(query.from_user.id, service_name)
    form_url = f"{settings.web_form_base_url}/key/{token}"
    back_data = f"back:svc:{service_name}:from_services" if origin == "services" else f"back:svc:{service_name}"
    await query.edit_message_text(
        screens.form_waiting_text(service_name),
        reply_markup=keyboards.form_waiting_keyboard(service_name, form_url, back_data, origin),
    )


async def _dispatch(route: CallbackRoute, query, context: ContextTypes.DEFAULT_TYPE) -> None:
    if route.screen == "menu" or (route.screen == "back" and route.action == "menu"):
        await _show_main(query, context)
        return
    if route.screen == "nav" and route.action == "cancel":
        await _show_main(query, context)
        return
    if route.screen == "services" or (route.screen == "back" and route.action == "services"):
        await _show_services(query, context)
        return
    if route.screen == "back" and route.action == "query":
        await _show_query_menu(query, context)
        return
    if route.screen == "back" and route.action == "svc":
        service_name, origin = route.params
        await _show_service(query, context, service_name,
                            "services" if origin == "from_services" else "menu")
        return
    if route.screen == "svc":
        service_name, origin = route.params
        if route.action == "detail":
            await _show_service(query, context, service_name, origin)
        elif route.action in {"add", "update"}:
            await _show_form_wait(query, context, service_name, origin)
        elif route.action == "delete_confirm":
            item = await context.application.bot_data["db"].get_service(query.from_user.id, service_name)
            if item is None:
                await _show_service(query, context, service_name, origin)
                return
            await query.edit_message_text(
                screens.delete_confirmation_text(service_name),
                reply_markup=keyboards.delete_confirmation_keyboard(service_name, origin),
            )
        elif route.action == "delete":
            await context.application.bot_data["db"].delete_service(query.from_user.id, service_name)
            await _show_service(query, context, service_name, origin)
        return
    if route.screen == "query":
        if route.action == "menu":
            await _show_query_menu(query, context)
            return
        user_id = query.from_user.id
        if route.action == "one":
            service_name, origin = route.params
            if origin == "from_svc_services":
                back_data = f"back:svc:{service_name}:from_services"
            elif origin == "from_svc":
                back_data = f"back:svc:{service_name}"
            else:
                back_data = "back:query:menu"
            result_markup = keyboards.query_result_keyboard(back_data)
            await query.edit_message_text("Consultando el servicio…", reply_markup=result_markup)
            result = await _query_one(user_id, service_name, context)
            await query.edit_message_text(screens.query_result_text(result), reply_markup=result_markup)
            return
        if route.action == "all":
            services = await context.application.bot_data["db"].list_services(user_id)
            if not services:
                await _show_query_menu(query, context)
                return
            result_markup = keyboards.query_result_keyboard()
            await query.edit_message_text("Consultando tus servicios…", reply_markup=result_markup)
            results = await asyncio.gather(*[
                _query_one(user_id, item["service_name"], context, table_row=True)
                for item in services
            ])
            await query.edit_message_text(screens.query_all_text(results), reply_markup=result_markup)
            return
    if route.screen == "form":
        service_name, origin = route.params
        if route.action == "resend":
            await _show_form_wait(query, context, service_name,
                                  "services" if origin == "from_services" else "menu")
            return
        if route.action == "check":
            item = await context.application.bot_data["db"].get_service(query.from_user.id, service_name)
            if item:
                await _show_service(query, context, service_name,
                                    "services" if origin == "from_services" else "menu")
            else:
                markup = query.message.reply_markup if query.message else None
                await query.edit_message_text(
                    screens.form_saved_text(service_name, False), reply_markup=markup
                )
            return
    raise InvalidCallback("acción no implementada")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde todos los callbacks y edita la pantalla en el mismo mensaje."""
    query = update.callback_query
    if query is None:
        return
    try:
        route = parse_callback_data(query.data)
    except InvalidCallback:
        await query.answer("Esta opción ya no está disponible", show_alert=True)
        try:
            await _show_main(query, context)
        except Exception:
            logger.exception("No se pudo reeditar el menú tras un callback inválido")
        return

    await query.answer()
    try:
        await _dispatch(route, query, context)
    except Exception:
        logger.exception("Error al procesar callback: pantalla=%s acción=%s", route.screen, route.action)
        try:
            await _show_main(query, context)
        except Exception:
            logger.exception("No se pudo mostrar el menú tras un error de callback")


def register(application) -> None:
    """Registra el único CallbackQueryHandler de la aplicación."""
    application.add_handler(CallbackQueryHandler(handle_callback))
