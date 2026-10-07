"""Versioned, single-active-message film and resource search views."""
from __future__ import annotations

import asyncio
import time

from structlog import get_logger
from telegram import InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError

from config import settings
from media_views import (
    candidate_keyboard,
    clamp_page,
    ensure_caption,
    overview_keyboard,
    parse_view_callback,
    render_candidates,
    render_overview,
    resource_keyboard,
    sorted_type_buttons,
)
from message_utils import add_auto_delete_notice, ensure_telegram_text
from pansou_client import pansou_client
from runtime_state import (
    build_search_cache_key,
    check_search_rate_limit,
    schedule_message_deletion,
    search_cache,
)
from tmdb_client import tmdb_client, unique_exact_match
from user_settings import settings_manager

logger = get_logger()


def _resource_query(state):
    movie = state.get("selected_movie")
    if movie:
        return " ".join(filter(None, [movie["title"], "" if state.get("title_only") else movie.get("year")]))
    return state["keyword"]


async def _search_resources(state, *, force_refresh=False):
    user_settings = settings_manager.get_settings(state["user_id"])
    state["resource_keyword"] = _resource_query(state)
    state["results"] = await pansou_client.search(
        keyword=state["resource_keyword"],
        filter_config=user_settings.get_filter_config(),
        force_refresh=force_refresh,
        **state["options"],
    )
    state["category_page"] = 1
    state["view"] = "overview"


def _view_content(key, state):
    revision = state["view_revision"]
    if state["view"] == "candidates":
        return (
            render_candidates(state["keyword"], state["candidates"], state["candidate_page"]),
            candidate_keyboard(key, revision, state["candidates"], state["candidate_page"]),
            None,
        )
    results = state["results"]
    if state["view"] == "overview":
        movie = state.get("selected_movie")
        text = render_overview(state["resource_keyword"], movie, results.get("total", 0))
        if results.get("error"):
            # Never echo transport errors/URLs supplied by an upstream service.
            text = "❌ 资源搜索暂时不可用，请点重新搜索重试。\n\n" + text
        retry = bool(movie and movie.get("year") and not state.get("title_only") and not results.get("total") and not results.get("error"))
        if retry:
            text = "未找到该片名与年份的资源，可仅按片名重试。\n\n" + text
        keyboard = overview_keyboard(
            key, revision, pansou_client.get_type_buttons(results), state["category_page"],
            has_candidates=bool(state["candidates"]), retry_title=retry,
        )
        poster = None if state.get("poster_failed") else (state.get("poster_file_id") or (movie or {}).get("poster_url"))
        return ensure_caption(text), keyboard, poster
    per_page = max(1, min(settings_manager.get_settings(state["user_id"]).result_limit, settings.max_result_limit))
    if state["view"] == "all":
        text = pansou_client.format_results(
            results, state["resource_keyword"], per_type_limit=per_page,
            cache_key=key, bot_username=state["bot_username"],
        )
        keyboard = resource_keyboard(key, revision, None)
    else:
        cloud_index = state["cloud_index"]
        cloud_type = sorted_type_buttons(pansou_client.get_type_buttons(results))[cloud_index]["type"]
        total_pages = max(1, (len(results["merged_by_type"][cloud_type]) + per_page - 1) // per_page)
        page = max(1, min(state["resource_page"], total_pages))
        text = pansou_client.format_type_results(
            results, state["resource_keyword"], cloud_type, page, per_page,
            cache_key=key, bot_username=state["bot_username"],
        )
        keyboard = resource_keyboard(key, revision, cloud_index, page, total_pages)
    return ensure_telegram_text(add_auto_delete_notice(text, ParseMode.HTML), ParseMode.HTML), keyboard, None


async def _retire_message(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.warning("media_old_message_delete_failed", error_type=type(exc).__name__)
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception as clear_exc:
            logger.warning("media_old_keyboard_clear_failed", error_type=type(clear_exc).__name__)
        schedule_message_deletion(chat_id, message_id, delay=5)


async def _publish(bot, key, current, next_state):
    """Commit state only after Telegram accepts the new view; caller holds its lock."""
    next_state["view_revision"] = current["view_revision"] + 1
    text, keyboard, poster = _view_content(key, next_state)
    chat_id, old_id = current["chat_id"], current["active_message_id"]
    next_state["active_message_id"] = old_id
    was_photo = current["view_kind"] == "photo"
    try:
        if poster:
            try:
                if was_photo and current.get("displayed_poster") == poster:
                    message = await bot.edit_message_caption(
                        chat_id=chat_id, message_id=old_id, caption=text,
                        parse_mode=ParseMode.HTML, reply_markup=keyboard,
                    )
                else:
                    message = await bot.edit_message_media(
                        chat_id=chat_id, message_id=old_id,
                        media=InputMediaPhoto(poster, caption=text, parse_mode=ParseMode.HTML),
                        reply_markup=keyboard,
                    )
                next_state["view_kind"] = "photo"
                next_state["displayed_poster"] = poster
                if getattr(message, "photo", None):
                    next_state["poster_file_id"] = message.photo[-1].file_id
                    next_state["displayed_poster"] = next_state["poster_file_id"]
            except BadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    next_state["view_kind"] = "photo"
                else:
                    logger.warning("media_poster_unavailable", error_type=type(exc).__name__)
                    next_state["poster_failed"] = True
                    poster = None
            except NetworkError:
                # On the first view, try replacing the loading text with usable
                # results. A later failed switch leaves the last accepted view.
                if current["view_revision"] != 0 or was_photo:
                    raise
                poster = None
        if not poster:
            if was_photo:
                message = await bot.send_message(
                    chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                    reply_markup=keyboard, disable_web_page_preview=True,
                    message_thread_id=current.get("message_thread_id"),
                )
                next_state["active_message_id"] = message.message_id
            else:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=old_id, text=text,
                        parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True,
                    )
                except BadRequest as exc:
                    if "message is not modified" not in str(exc).lower():
                        raise
            next_state["view_kind"] = "text"
            next_state["displayed_poster"] = None
    except Exception as exc:
        logger.warning("media_view_publish_failed", error_type=type(exc).__name__)
        return False
    # Keep the original dict (and its lock) alive for queued callbacks.
    current.update(next_state)
    schedule_message_deletion(chat_id, current["active_message_id"])
    if old_id != current["active_message_id"]:
        await _retire_message(bot, chat_id, old_id)
    return True


async def start_media_search(bot, *, keyword, user_id, chat_id, message_id, options, force_refresh=False, message_thread_id=None):
    user_settings = settings_manager.get_settings(user_id)
    effective_options = {
        "limit": max(1, min(options.get("limit") or user_settings.result_limit, settings.max_result_limit)),
        "cloud_types": options.get("cloud_types") if options.get("cloud_types") is not None else user_settings.cloud_types,
        "source_type": options.get("source_type") or user_settings.source_type,
        "plugins": options.get("plugins") if options.get("plugins") is not None else (user_settings.plugins or None),
        "channels": options.get("channels") if options.get("channels") is not None else (user_settings.channels or None),
    }
    key = build_search_cache_key(chat_id, user_id, message_id)
    state = {
        "keyword": keyword, "resource_keyword": keyword, "user_id": user_id, "chat_id": chat_id,
        "active_message_id": message_id, "message_thread_id": message_thread_id, "view_revision": 0, "view_kind": "text", "view": "overview",
        "category_page": 1, "candidate_page": 1, "selected_movie": None, "candidates": [],
        "results": {}, "options": effective_options, "timestamp": time.time(),
        "bot_username": bot.username, "_lock": asyncio.Lock(),
    }
    search_cache.set(key, state)
    schedule_message_deletion(chat_id, message_id)
    async with state["_lock"]:
        next_state = dict(state)
        try:
            next_state["candidates"] = await tmdb_client.search(keyword)
            next_state["selected_movie"] = unique_exact_match(keyword, next_state["candidates"])
            if next_state["candidates"] and not next_state["selected_movie"]:
                next_state["view"] = "candidates"
            else:
                await _search_resources(next_state, force_refresh=force_refresh)
        except Exception as exc:
            logger.warning("media_search_failed", error_type=type(exc).__name__)
            next_state["results"] = {"error": "unavailable"}
        if search_cache.get(key) is state:
            if await _publish(bot, key, state, next_state):
                if search_cache.get(key) is state:
                    search_cache.set(key, state)


def _valid_owner(state, key, update, revision):
    try:
        chat, user, _ = map(int, key.split(":"))
        return (
            chat == update.effective_chat.id == state["chat_id"]
            and user == update.effective_user.id == state["user_id"]
            and update.callback_query.message is not None
            and update.callback_query.message.message_id == state["active_message_id"]
            and revision == state["view_revision"]
        )
    except (ValueError, TypeError, AttributeError):
        return False


async def handle_media_callback(update, context):
    query = update.callback_query
    if not query.data or not query.data.startswith("v:"):
        return False
    parsed = parse_view_callback(query.data)
    if not parsed:
        await query.answer("❌ 参数错误", show_alert=True)
        return True
    key, revision, action, arg = parsed
    state = search_cache.get(key)
    if not state:
        await query.answer("⚠️ 搜索结果已过期，请重新搜索", show_alert=True)
        return True
    if not _valid_owner(state, key, update, revision):
        await query.answer("⚠️ 仅搜索本人可操作当前页面，请使用最新消息", show_alert=True)
        return True
    async with state["_lock"]:
        if search_cache.get(key) is not state or not _valid_owner(state, key, update, revision):
            await query.answer("⚠️ 页面已更新或过期，请使用最新消息", show_alert=True)
            return True
        if action == "noop":
            await query.answer()
            return True
        if action in {"pick", "raw", "retry", "refresh"}:
            allowed, retry_after = check_search_rate_limit(state["user_id"])
            if not allowed:
                await query.answer(f"⏳ 请在 {retry_after} 秒后再试", show_alert=True)
                return True
        next_state = dict(state)
        try:
            if action in {"cat", "back"}:
                next_state["view"] = "overview"
                if action == "cat":
                    next_state["category_page"] = clamp_page(int(arg), len(pansou_client.get_type_buttons(state["results"])))
            elif action == "cand":
                next_state["view"] = "candidates"
                next_state["candidate_page"] = clamp_page(int(arg), len(state["candidates"]))
            elif action == "pick":
                index = int(arg)
                if index < 0 or index >= len(state["candidates"]):
                    raise ValueError("candidate")
                next_state.update(selected_movie=state["candidates"][index], title_only=False, poster_file_id=None, poster_failed=False)
            elif action == "raw":
                next_state.update(selected_movie=None, title_only=False, poster_file_id=None, poster_failed=False)
            elif action == "retry":
                if not state.get("selected_movie") or not state["selected_movie"].get("year") or state.get("title_only") or state["results"].get("total") or state["results"].get("error"):
                    raise ValueError("retry")
                next_state["title_only"] = True
            elif action == "refresh":
                pass
            elif action == "all":
                next_state["view"] = "all"
            elif action == "type":
                index, page = map(int, arg.split("."))
                types = sorted_type_buttons(pansou_client.get_type_buttons(state["results"]))
                if index < 0 or index >= len(types):
                    raise ValueError("cloud")
                next_state.update(view="type", cloud_index=index, resource_page=max(1, page))
            else:
                raise ValueError("action")
        except (ValueError, TypeError):
            await query.answer("❌ 参数错误", show_alert=True)
            return True
        await query.answer()
        try:
            if action in {"pick", "raw", "retry", "refresh"}:
                await _search_resources(next_state, force_refresh=action == "refresh")
            # A long API wait may outlive this search; do not resurrect its cache.
            if search_cache.get(key) is not state:
                return True
            if await _publish(context.bot, key, state, next_state):
                if action in {"pick", "raw", "retry", "refresh"} and search_cache.get(key) is state:
                    search_cache.set(key, state)
        except Exception as exc:
            logger.warning("media_callback_failed", error_type=type(exc).__name__)
        return True
