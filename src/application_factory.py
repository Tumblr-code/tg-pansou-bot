"""Application construction and handler registration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot_config import create_optimized_request
from config import settings


@dataclass(frozen=True)
class BotHandlerSet:
    start: Callable
    help: Callable
    types: Callable
    sources: Callable
    plugins: Callable
    channels: Callable
    settings: Callable
    filter: Callable
    reset: Callable
    status: Callable
    refresh: Callable
    search: Callable
    callback: Callable
    private_message: Callable
    error: Callable


def create_application(
    handlers: BotHandlerSet,
    post_init: Callable[[Application], Awaitable[None]],
    post_shutdown: Callable[[Application], Awaitable[None]],
) -> Application:
    application = (
        Application.builder()
        .token(settings.tg_bot_token)
        .request(create_optimized_request())
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(32)
        .build()
    )

    for name, handler in (
        ("start", handlers.start),
        ("help", handlers.help),
        ("types", handlers.types),
        ("sources", handlers.sources),
        ("plugins", handlers.plugins),
        ("channels", handlers.channels),
        ("settings", handlers.settings),
        ("filter", handlers.filter),
        ("reset", handlers.reset),
        ("status", handlers.status),
        ("refresh", handlers.refresh),
        ("search", handlers.search),
    ):
        application.add_handler(CommandHandler(name, handler))

    application.add_handler(
        CommandHandler(
            "s",
            handlers.search,
            filters=filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP,
        )
    )
    application.add_handler(CallbackQueryHandler(handlers.callback))
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            handlers.private_message,
        )
    )
    application.add_error_handler(handlers.error)
    return application
