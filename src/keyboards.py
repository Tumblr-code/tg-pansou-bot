"""Inline keyboard builders and callback-data parsers."""
from __future__ import annotations

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

AD_LINKS = (
    ("🤖 公益机器人 @China_nb_plus_bot", "https://t.me/China_nb_plus_bot"),
    ("📢 频道 @China_nb_plus", "https://t.me/China_nb_plus"),
    ("💬 交流群 @ChIna_NB_i", "https://t.me/ChIna_NB_i"),
)


def create_ad_button_rows() -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton(AD_LINKS[0][0], url=AD_LINKS[0][1])],
        [
            InlineKeyboardButton(AD_LINKS[1][0], url=AD_LINKS[1][1]),
            InlineKeyboardButton(AD_LINKS[2][0], url=AD_LINKS[2][1]),
        ],
    ]


def create_type_keyboard(type_buttons: list, cache_key: str, page: int = 1) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for btn in type_buttons:
        row.append(
            InlineKeyboardButton(
                btn["text"],
                callback_data=f"type:{cache_key}:{btn['type']}:{page}",
            )
        )

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔄 重新搜索", callback_data=f"refresh:{cache_key}"),
        InlineKeyboardButton("📊 显示全部", callback_data=f"all:{cache_key}"),
    ])
    buttons.extend(create_ad_button_rows())
    return InlineKeyboardMarkup(buttons)


def parse_cache_key_from_action(data: str, prefix: str) -> Optional[str]:
    if not data.startswith(prefix):
        return None
    cache_key = data[len(prefix):]
    return cache_key or None


def parse_type_callback(data: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    if not data.startswith("type:"):
        return None, None, None

    body = data[5:]
    try:
        cache_key, cloud_type, page = body.rsplit(":", 2)
        return cache_key, cloud_type, int(page)
    except ValueError:
        return None, None, None


def is_cache_owner(
    cache_key: str,
    chat_id: int,
    user_id: int,
    message_id: Optional[int] = None,
) -> bool:
    try:
        parts = cache_key.split(":")
        if len(parts) == 3:
            cached_chat_id, cached_user_id, cached_message_id = parts
            if message_id is None:
                return False
            return (
                int(cached_chat_id) == chat_id
                and int(cached_user_id) == user_id
                and int(cached_message_id) == message_id
            )

        if len(parts) == 2:
            cached_chat_id, cached_user_id = parts
            return int(cached_chat_id) == chat_id and int(cached_user_id) == user_id
    except (TypeError, ValueError):
        pass
    return False


def create_pagination_keyboard(
    cache_key: str,
    cloud_type: str,
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                "⬅️ 上一页",
                callback_data=f"type:{cache_key}:{cloud_type}:{current_page - 1}",
            )
        )

    nav_buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))

    if current_page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                "下一页 ➡️",
                callback_data=f"type:{cache_key}:{cloud_type}:{current_page + 1}",
            )
        )

    buttons = [
        nav_buttons,
        [
            InlineKeyboardButton("🔙 返回分类", callback_data=f"back:{cache_key}"),
            InlineKeyboardButton("🔄 重新搜索", callback_data=f"refresh:{cache_key}"),
        ],
    ]
    buttons.extend(create_ad_button_rows())
    return InlineKeyboardMarkup(buttons)


def create_all_results_keyboard(cache_key: str) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton("🔙 返回分类", callback_data=f"back:{cache_key}"),
        InlineKeyboardButton("🔄 重新搜索", callback_data=f"refresh:{cache_key}"),
    ]]
    buttons.extend(create_ad_button_rows())
    return InlineKeyboardMarkup(buttons)
