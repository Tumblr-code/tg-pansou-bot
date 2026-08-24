"""Search execution flow shared by commands and callback refreshes."""
from __future__ import annotations

import html
import time
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from structlog import get_logger

from config import settings
from keyboards import create_type_keyboard
from message_utils import add_auto_delete_notice, reply_with_auto_delete
from message_utils import safe_edit_message as _safe_edit_message
from pansou_client import pansou_client
from runtime_state import (
    build_search_cache_key as _build_search_cache_key,
    check_search_rate_limit,
    schedule_message_deletion,
    search_cache,
)
from user_settings import settings_manager

logger = get_logger()


def _compact_names(values: Optional[list], *, limit: int = 3) -> str:
    if not values:
        return "全部"
    names = [str(value) for value in values if str(value).strip()]
    if len(names) <= limit:
        return "、".join(names)
    return "、".join(names[:limit]) + f" 等{len(names)}个"


def _format_search_scope(
    *,
    source_type: Optional[str],
    cloud_types: Optional[list],
    plugins: Optional[list],
    channels: Optional[list],
    limit: int,
    force_refresh: bool,
) -> str:
    source_names = {"all": "全部来源", "tg": "仅频道", "plugin": "仅插件"}
    parts = [
        f"来源: {source_names.get(source_type or 'all', source_type or '全部来源')}",
        f"网盘: {_compact_names(cloud_types)}",
        f"每类: {limit}",
    ]
    if plugins:
        parts.append(f"插件: {_compact_names(plugins)}")
    if channels:
        parts.append(f"频道: {_compact_names(channels)}")
    if force_refresh:
        parts.append("已刷新")
    return " · ".join(parts)


async def _run_search_flow(
    *,
    keyword: str,
    user_id: int,
    chat_id: int,
    edit_message,
    message_id: int,
    limit: Optional[int] = None,
    cloud_types: Optional[list] = None,
    source_type: Optional[str] = None,
    plugins: Optional[list] = None,
    channels: Optional[list] = None,
    force_refresh: bool = False,
    show_loading: bool = True,
) -> None:
    user_settings = settings_manager.get_settings(user_id)

    if limit is None:
        limit = user_settings.result_limit
    limit = max(1, min(limit, settings.max_result_limit))

    if cloud_types is None:
        cloud_types = user_settings.cloud_types

    if source_type is None:
        source_type = user_settings.source_type

    filter_config = user_settings.get_filter_config()
    safe_keyword = html.escape(keyword)
    effective_channels = channels if channels is not None else (user_settings.channels if user_settings.channels else None)
    effective_plugins = plugins if plugins is not None else (user_settings.plugins if user_settings.plugins else None)
    scope_text = _format_search_scope(
        source_type=source_type,
        cloud_types=cloud_types,
        plugins=effective_plugins,
        channels=effective_channels,
        limit=limit,
        force_refresh=force_refresh,
    )

    if show_loading:
        await _safe_edit_message(
            edit_message,
            f"🔍 正在搜索：<b>{safe_keyword}</b>...\n<code>{html.escape(scope_text)}</code>",
            parse_mode=ParseMode.HTML,
        )
    schedule_message_deletion(chat_id, message_id)

    try:
        results = await pansou_client.search(
            keyword=keyword,
            channels=effective_channels,
            plugins=effective_plugins,
            cloud_types=cloud_types,
            source_type=source_type,
            filter_config=filter_config,
            limit=limit,
            force_refresh=force_refresh,
        )

        if "error" in results:
            safe_error = html.escape(str(results["error"]))
            error_text = add_auto_delete_notice(f"❌ {safe_error}", ParseMode.HTML)
            await _safe_edit_message(edit_message, error_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, message_id)
            return

        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)

        if not merged_by_type or total == 0:
            empty_text = add_auto_delete_notice(f"🔍 未找到与「{safe_keyword}」相关的资源", ParseMode.HTML)
            await _safe_edit_message(edit_message, empty_text, parse_mode=ParseMode.HTML)
            schedule_message_deletion(chat_id, message_id)
            return

        cache_key = _build_search_cache_key(chat_id, user_id, message_id)
        search_cache.set(cache_key, {
            "keyword": keyword,
            "results": results,
            "timestamp": time.time(),
            "options": {
                "limit": limit,
                "cloud_types": cloud_types,
                "source_type": source_type,
                "plugins": plugins,
                "channels": channels,
            },
        })

        overview_text = pansou_client.format_overview(results, keyword)
        overview_text = f"{overview_text}\n\n<code>{html.escape(scope_text)}</code>"
        overview_text = add_auto_delete_notice(overview_text, ParseMode.HTML)
        type_buttons = pansou_client.get_type_buttons(results)
        keyboard = create_type_keyboard(type_buttons, cache_key)

        await _safe_edit_message(
            edit_message,
            overview_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        schedule_message_deletion(chat_id, message_id)

        logger.info(
            "search_completed",
            keyword=keyword,
            user_id=user_id,
            total=total,
            types=list(merged_by_type.keys()),
        )
    except Exception as e:
        logger.error("search_error", error=str(e), keyword=keyword)
        safe_error = html.escape(str(e))
        error_text = add_auto_delete_notice(
            f"❌ 搜索出错：{safe_error}\n\n请稍后重试或使用 /status 检查服务状态",
            ParseMode.HTML,
        )
        await _safe_edit_message(edit_message, error_text, parse_mode=ParseMode.HTML)
        schedule_message_deletion(chat_id, message_id)


async def perform_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    keyword: str,
    limit: Optional[int] = None,
    cloud_types: Optional[list] = None,
    source_type: Optional[str] = None,
    plugins: Optional[list] = None,
    channels: Optional[list] = None,
    force_refresh: bool = False,
) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    allowed, retry_after = check_search_rate_limit(user_id)
    if not allowed:
        await reply_with_auto_delete(update, f"⏳ 搜索太频繁了，请在 {retry_after} 秒后再试")
        return

    search_message = await update.message.reply_text(
        f"🔍 正在搜索：<b>{html.escape(keyword)}</b>...",
        parse_mode=ParseMode.HTML,
    )

    async def _edit_message(text: str, **kwargs):
        return await search_message.edit_text(text, **kwargs)

    await _run_search_flow(
        keyword=keyword,
        user_id=user_id,
        chat_id=chat_id,
        edit_message=_edit_message,
        message_id=search_message.message_id,
        limit=limit,
        cloud_types=cloud_types,
        source_type=source_type,
        plugins=plugins,
        channels=channels,
        force_refresh=force_refresh,
        show_loading=False,
    )


async def perform_search_from_callback(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    keyword: str,
    user_id: int,
    chat_id: int,
    limit: Optional[int] = None,
    cloud_types: Optional[list] = None,
    source_type: Optional[str] = None,
    plugins: Optional[list] = None,
    channels: Optional[list] = None,
    force_refresh: bool = True,
) -> None:
    async def _edit_message(text: str, **kwargs):
        return await query.edit_message_text(text, **kwargs)

    await _run_search_flow(
        keyword=keyword,
        user_id=user_id,
        chat_id=chat_id,
        edit_message=_edit_message,
        message_id=query.message.message_id,
        limit=limit,
        cloud_types=cloud_types,
        source_type=source_type,
        plugins=plugins,
        channels=channels,
        force_refresh=force_refresh,
        show_loading=True,
    )
