"""Telegram message helpers with safe truncation and retry handling."""
from __future__ import annotations

import asyncio
import html
import re
from typing import Optional

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from structlog import get_logger

from runtime_state import auto_delete_message

logger = get_logger()

MAX_TELEGRAM_TEXT = 4096
SAFE_TEXT_LIMIT = 3900


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]*>", "", text)


def ensure_telegram_text(text: str, parse_mode: Optional[str] = None) -> str:
    """Return text that fits Telegram limits without leaving broken HTML."""
    if len(text) <= MAX_TELEGRAM_TEXT:
        return text

    suffix = "\n\n...（内容过长已截断）"
    limit = SAFE_TEXT_LIMIT - len(suffix)
    if parse_mode == ParseMode.HTML:
        plain = html.unescape(_strip_html_tags(text))
        return html.escape(plain[:limit].rstrip()) + suffix
    return text[:limit].rstrip() + suffix


def add_auto_delete_notice(text: str, parse_mode: Optional[str] = None) -> str:
    if parse_mode == ParseMode.HTML:
        return f"{text}\n\n<i>⏰ 此消息将在 3 分钟后自动删除</i>"
    if parse_mode == ParseMode.MARKDOWN:
        return f"{text}\n\n_⏰ 此消息将在 3 分钟后自动删除_"
    return f"{text}\n\n⏰ 此消息将在 3 分钟后自动删除"


async def safe_edit_message(edit_message, text: str, **kwargs):
    parse_mode = kwargs.get("parse_mode")
    safe_text = ensure_telegram_text(text, parse_mode=parse_mode)

    for attempt in range(2):
        try:
            try:
                return await edit_message(text=safe_text, **kwargs)
            except TypeError:
                return await edit_message(safe_text, **kwargs)
        except BadRequest as exc:
            if "Message is not modified" in str(exc):
                logger.debug("ignored_message_not_modified")
                return None
            raise
        except RetryAfter as exc:
            retry_after = int(getattr(exc, "retry_after", 1) or 1)
            logger.warning("telegram_retry_after", retry_after=retry_after)
            if attempt == 0:
                await asyncio.sleep(min(retry_after, 5))
                continue
            return None
        except (TimedOut, NetworkError) as exc:
            logger.warning("telegram_edit_transient_error", error=str(exc))
            return None
    return None


async def reply_with_auto_delete(
    update: Update,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    **kwargs,
) -> Message:
    text_with_notice = ensure_telegram_text(
        add_auto_delete_notice(text, parse_mode),
        parse_mode=parse_mode,
    )

    message = await update.message.reply_text(
        text_with_notice,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        **kwargs,
    )
    auto_delete_message(message)
    return message
