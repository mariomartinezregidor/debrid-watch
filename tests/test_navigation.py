"""Pruebas del contrato de navegación inline y su enrutador central."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler

from handlers import callbacks, queries, services_menu, start
from handlers.keyboards import (
    delete_confirmation_keyboard,
    form_waiting_keyboard,
    main_menu_keyboard,
    query_menu_keyboard,
    service_detail_keyboard,
    services_list_keyboard,
)


def callback_data(markup: InlineKeyboardMarkup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


class CallbackContractTests(unittest.TestCase):
    def test_routes_and_legacy_aliases(self):
        expected = {
            "menu:main": ("menu", "main"),
            "svc:torbox": ("svc", "detail"),
            "svc:torbox:add": ("svc", "add"),
            "query:all": ("query", "all"),
            "services:list": ("services", "list"),
            "form:check:torbox": ("form", "check"),
            "back:menu": ("back", "menu"),
            "nav:cancel": ("nav", "cancel"),
            "query_menu": ("query", "menu"),
            "manage_menu": ("services", "list"),
            "service:update:torbox": ("svc", "update"),
        }
        for data, screen_action in expected.items():
            with self.subTest(data=data):
                route = callbacks.parse_callback_data(data)
                self.assertEqual(screen_action, (route.screen, route.action))

    def test_invalid_callback_data_is_rejected(self):
        for data in (None, "", "svc:unknown", "svc:torbox:erase", "form:invalid:torbox", "nonsense"):
            with self.subTest(data=data), self.assertRaises(callbacks.InvalidCallback):
                callbacks.parse_callback_data(data)

    def test_inline_keyboards_and_destructive_confirmation(self):
        markups = [
            main_menu_keyboard("https://example.test"),
            service_detail_keyboard("torbox", configured=False),
            service_detail_keyboard("torbox", configured=True),
            query_menu_keyboard(["torbox", "real_debrid"]),
            services_list_keyboard(["torbox"]),
            delete_confirmation_keyboard("torbox"),
            form_waiting_keyboard("torbox", "https://example.test/key/sample"),
        ]
        for markup in markups:
            self.assertIsInstance(markup, InlineKeyboardMarkup)
            for data in callback_data(markup):
                self.assertLessEqual(len(data.encode("utf-8")), 64)
        destructive = [data for data in callback_data(delete_confirmation_keyboard("torbox"))
                       if data == "svc:torbox:delete"]
        self.assertEqual(["svc:torbox:delete"], destructive)
        self.assertIn("form:check:torbox", callback_data(form_waiting_keyboard("torbox", "https://example.test")))
        self.assertIn("form:resend:torbox", callback_data(form_waiting_keyboard("torbox", "https://example.test")))

    def test_only_one_callback_query_handler_is_registered(self):
        app = Application.builder().token("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi").build()
        start.register(app)
        services_menu.register(app)
        queries.register(app)
        callbacks.register(app)
        registered = [handler for handlers in app.handlers.values() for handler in handlers
                      if isinstance(handler, CallbackQueryHandler)]
        self.assertEqual(1, len(registered))


class InvalidCallbackHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_callback_answers_alert_and_edits_to_main(self):
        query = SimpleNamespace(
            data="old:unknown", answer=AsyncMock(), edit_message_text=AsyncMock(), from_user=None
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=SimpleNamespace(bot_data={
            "settings": SimpleNamespace(web_form_base_url="https://example.test")
        }))
        await callbacks.handle_callback(update, context)
        query.answer.assert_awaited_once_with("Esta opción ya no está disponible", show_alert=True)
        query.edit_message_text.assert_awaited_once()
        self.assertIsInstance(query.edit_message_text.await_args.kwargs["reply_markup"], InlineKeyboardMarkup)

    async def test_valid_callback_is_answered_and_edits_the_existing_screen(self):
        query = SimpleNamespace(
            data="menu:main", answer=AsyncMock(), edit_message_text=AsyncMock(), from_user=None
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=SimpleNamespace(bot_data={
            "settings": SimpleNamespace(web_form_base_url="https://example.test")
        }))
        await callbacks.handle_callback(update, context)
        query.answer.assert_awaited_once_with()
        query.edit_message_text.assert_awaited_once()
        self.assertIsInstance(query.edit_message_text.await_args.kwargs["reply_markup"], InlineKeyboardMarkup)


class CommandScreensTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_command_displays_inline_main_menu(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        context = SimpleNamespace(application=SimpleNamespace(bot_data={
            "settings": SimpleNamespace(web_form_base_url="https://example.test")
        }))
        await start.start(update, context)
        kwargs = message.reply_text.await_args.kwargs
        self.assertIsInstance(kwargs["reply_markup"], InlineKeyboardMarkup)
        self.assertEqual(
            {
                "svc:torbox", "svc:real_debrid", "svc:alldebrid", "svc:premiumize",
                "svc:debridlink", "svc:offcloud", "svc:putio", "query:menu", "services:list",
            },
            set(callback_data(kwargs["reply_markup"])),
        )

    async def test_commands_for_queries_and_services_include_inline_navigation(self):
        message_query = SimpleNamespace(reply_text=AsyncMock())
        update_query = SimpleNamespace(effective_user=SimpleNamespace(id=3), effective_message=message_query)
        message_services = SimpleNamespace(reply_text=AsyncMock())
        update_services = SimpleNamespace(effective_user=SimpleNamespace(id=3), effective_message=message_services)
        db = SimpleNamespace(list_services=AsyncMock(return_value=[]))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={"db": db}))
        await queries.caducidad(update_query, context)
        await services_menu.manage_command(update_services, context)
        for message in (message_query, message_services):
            self.assertIsInstance(message.reply_text.await_args.kwargs["reply_markup"], InlineKeyboardMarkup)


if __name__ == "__main__":
    unittest.main()
