from __future__ import annotations

import asyncio
import html
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest
from telegram.error import BadRequest, TimedOut

import bot as bot_module
import media_search
from magnet_links import magnet_uri_digest, parse_magnet_start_payload
from media_views import build_view_callback
from runtime_state import LRUCache
from user_settings import UserSettings

CACHE_KEY = "-1001:2002:3003"
MAGNET_URI = (
    "magnet:?xt=urn:btih:" + "a" * 40
    + "&dn=完整磁力🙂&tr=https://tracker.example/announce?x=1&y=2"
)


def movie(*, title="希望", year="2020", poster=True, identity=123):
    return {
        "id": identity,
        "media_type": "movie",
        "title": title,
        "original_title": title,
        "year": year,
        "overview": "一部关于希望的电影。",
        "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg" if poster else None,
        "source_url": f"https://www.themoviedb.org/movie/{identity}",
    }


def resources(*, extra_types=0):
    merged = {"magnet": [{"url": MAGNET_URI, "note": "希望 2020"}]}
    for index in range(extra_types):
        merged[f"drive{index}"] = [
            {"url": f"https://example.test/{index}/{item}", "note": f"资源 {item}"}
            for item in range(index + 2)
        ]
    return {"total": sum(map(len, merged.values())), "merged_by_type": merged}


@pytest.fixture
def state(monkeypatch):
    cache = LRUCache(max_size=5, ttl=300)
    message = SimpleNamespace(message_id=3003, chat_id=-1001)
    replacement = SimpleNamespace(message_id=4004, chat_id=-1001)
    photo = SimpleNamespace(
        message_id=3003, chat_id=-1001, photo=[SimpleNamespace(file_id="cached-poster")]
    )
    telegram_bot = SimpleNamespace(
        username="DifferentSearch_bot",
        edit_message_text=AsyncMock(return_value=message),
        edit_message_media=AsyncMock(return_value=photo),
        edit_message_caption=AsyncMock(return_value=photo),
        send_message=AsyncMock(return_value=replacement),
        delete_message=AsyncMock(return_value=True),
        edit_message_reply_markup=AsyncMock(return_value=True),
    )
    search = AsyncMock(return_value=resources())
    metadata = AsyncMock(return_value=[movie()])
    schedule = Mock()
    monkeypatch.setattr(media_search, "search_cache", cache)
    monkeypatch.setattr(media_search.pansou_client, "search", search)
    monkeypatch.setattr(media_search.tmdb_client, "search", metadata)
    monkeypatch.setattr(media_search, "schedule_message_deletion", schedule)
    monkeypatch.setattr(media_search, "check_search_rate_limit", Mock(return_value=(True, 0)))
    monkeypatch.setattr(
        media_search.settings_manager, "get_settings",
        Mock(return_value=UserSettings(user_id=2002)),
    )
    return SimpleNamespace(
        cache=cache, bot=telegram_bot, search=search, metadata=metadata, schedule=schedule,
        options={"limit": 10, "source_type": "all", "cloud_types": None,
                 "plugins": None, "channels": None},
    )


async def start(state, keyword="希望"):
    await media_search.start_media_search(
        state.bot, keyword=keyword, user_id=2002, chat_id=-1001, message_id=3003,
        options=state.options,
    )
    assert state.cache.get(CACHE_KEY) is not None


def callback(state, action, arg="", *, revision=None, message_id=None):
    session = state.cache.get(CACHE_KEY)
    query = SimpleNamespace(
        data=build_view_callback(
            CACHE_KEY, session["view_revision"] if revision is None else revision, action, arg,
        ),
        message=SimpleNamespace(
            message_id=session["active_message_id"] if message_id is None else message_id,
            chat_id=-1001,
        ),
        answer=AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=2002),
        effective_chat=SimpleNamespace(id=-1001, type="supergroup"),
    )


async def click(state, action, arg=""):
    update = callback(state, action, arg)
    assert await media_search.handle_media_callback(update, SimpleNamespace(bot=state.bot))
    return update


def reset_bot(state):
    for value in vars(state.bot).values():
        if isinstance(value, AsyncMock):
            value.reset_mock()


def assert_no_telegram_mutation(state):
    for name in (
        "edit_message_text", "edit_message_media", "edit_message_caption", "send_message",
        "delete_message", "edit_message_reply_markup",
    ):
        getattr(state.bot, name).assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_movie_uses_year_and_replaces_initial_text_with_media(state):
    await start(state)

    session = state.cache.get(CACHE_KEY)
    assert state.search.await_args.kwargs["keyword"] == "希望 2020"
    assert session["selected_movie"]["id"] == 123
    assert session["active_message_id"] == 3003
    assert session["view_kind"] == "photo"
    assert session["view"] == "overview"
    state.bot.edit_message_media.assert_awaited_once()
    state.bot.send_message.assert_not_awaited()
    state.schedule.assert_any_call(-1001, 3003)


@pytest.mark.asyncio
async def test_ambiguous_movie_requires_selection_before_resource_search(state):
    state.metadata.return_value = [movie(), movie(year="2024", identity=124)]
    await start(state)

    assert state.cache.get(CACHE_KEY)["view"] == "candidates"
    state.search.assert_not_awaited()
    await click(state, "pick", "1")

    assert state.search.await_args.kwargs["keyword"] == "希望 2024"
    assert state.cache.get(CACHE_KEY)["selected_movie"]["id"] == 124


@pytest.mark.asyncio
async def test_candidate_raw_keyword_action_keeps_nonvideo_search(state):
    state.metadata.return_value = [movie(title="其他影片")]
    await start(state, keyword="软件说明书")

    state.search.assert_not_awaited()
    await click(state, "raw")

    assert state.search.await_args.kwargs["keyword"] == "软件说明书"
    assert state.cache.get(CACHE_KEY)["selected_movie"] is None
    assert state.cache.get(CACHE_KEY)["view_kind"] == "text"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["metadata", "poster", "year"])
async def test_missing_metadata_poster_or_year_has_usable_overview(state, missing):
    state.metadata.return_value = (
        [] if missing == "metadata" else [movie(poster=missing != "poster", year="" if missing == "year" else "2020")]
    )
    await start(state)

    session = state.cache.get(CACHE_KEY)
    assert session["view"] == "overview"
    assert state.search.await_args.kwargs["keyword"] == (
        "希望 2020" if missing == "poster" else "希望"
    )
    if missing != "year":
        assert session["view_kind"] == "text"
        state.bot.edit_message_text.assert_awaited()


@pytest.mark.asyncio
async def test_no_year_results_only_broadens_after_explicit_retry(state):
    state.search.side_effect = [
        {"total": 0, "merged_by_type": {}}, resources(),
    ]
    await start(state)

    state.search.assert_awaited_once()
    assert state.search.await_args.kwargs["keyword"] == "希望 2020"
    await click(state, "retry")

    assert state.search.await_count == 2
    assert state.search.await_args.kwargs["keyword"] == "希望"
    assert state.cache.get(CACHE_KEY)["selected_movie"]["id"] == 123


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_identity", ["user", "chat", "message", "revision"])
async def test_callbacks_reject_wrong_identity_or_stale_view(state, wrong_identity):
    await start(state)
    update = callback(state, "all")
    if wrong_identity == "user":
        update.effective_user.id = 9999
    elif wrong_identity == "chat":
        update.effective_chat.id = -9999
        update.callback_query.message.chat_id = -9999
    elif wrong_identity == "message":
        update.callback_query.message.message_id = 9999
    else:
        update.callback_query.data = build_view_callback(CACHE_KEY, 0, "all")
    reset_bot(state)

    assert await media_search.handle_media_callback(update, SimpleNamespace(bot=state.bot))

    assert_no_telegram_mutation(state)
    update.callback_query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_expired_cache_does_not_change_old_view(state):
    await start(state)
    update = callback(state, "all")
    state.cache._timestamps[CACHE_KEY] -= state.cache.ttl + 1
    reset_bot(state)

    await media_search.handle_media_callback(update, SimpleNamespace(bot=state.bot))

    assert_no_telegram_mutation(state)
    update.callback_query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_photo_to_text_send_failure_preserves_original_state(state):
    await start(state)
    previous = dict(state.cache.get(CACHE_KEY))
    reset_bot(state)
    state.bot.send_message.side_effect = TimedOut()

    await click(state, "all")

    session = state.cache.get(CACHE_KEY)
    assert session["active_message_id"] == previous["active_message_id"]
    assert session["view_revision"] == previous["view_revision"]
    assert session["view"] == "overview"
    assert session["view_kind"] == "photo"
    state.bot.delete_message.assert_not_awaited()
    state.bot.edit_message_reply_markup.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_old_photo_delete_deactivates_buttons_and_schedules_cleanup(state):
    await start(state)
    stale = callback(state, "all")
    reset_bot(state)
    state.schedule.reset_mock()
    state.bot.delete_message.side_effect = BadRequest("Message cannot be deleted")

    await click(state, "all")

    session = state.cache.get(CACHE_KEY)
    assert session["active_message_id"] == 4004
    assert session["view_kind"] == "text"
    state.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=-1001, message_id=3003, reply_markup=None,
    )
    assert any(call.args[:2] == (-1001, 3003) for call in state.schedule.call_args_list)
    reset_bot(state)
    await media_search.handle_media_callback(stale, SimpleNamespace(bot=state.bot))
    assert_no_telegram_mutation(state)


@pytest.mark.asyncio
async def test_concurrent_double_click_sends_one_replacement(state):
    await start(state)
    first = callback(state, "all")
    second = callback(state, "all")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_send(**kwargs):
        entered.set()
        await release.wait()
        return SimpleNamespace(message_id=4004, chat_id=-1001)

    state.bot.send_message.side_effect = delayed_send
    one = asyncio.create_task(media_search.handle_media_callback(first, SimpleNamespace(bot=state.bot)))
    await asyncio.wait_for(entered.wait(), 1)
    two = asyncio.create_task(media_search.handle_media_callback(second, SimpleNamespace(bot=state.bot)))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(one, two)

    state.bot.send_message.assert_awaited_once()
    state.bot.delete_message.assert_awaited_once()
    assert state.cache.get(CACHE_KEY)["active_message_id"] == 4004


@pytest.mark.asyncio
async def test_unavailable_poster_falls_back_to_text_without_extra_message(state):
    state.bot.edit_message_media.side_effect = BadRequest("Wrong file identifier/HTTP URL specified")
    await start(state)

    assert state.cache.get(CACHE_KEY)["view_kind"] == "text"
    state.bot.edit_message_text.assert_awaited()
    state.bot.send_message.assert_not_awaited()
    await click(state, "all")
    assert state.cache.get(CACHE_KEY)["view"] == "all"


@pytest.mark.asyncio
async def test_back_restores_drive_page_and_does_not_refetch_metadata(state):
    state.search.return_value = resources(extra_types=8)
    await start(state)
    await click(state, "cat", "2")
    assert state.cache.get(CACHE_KEY)["category_page"] == 2
    state.bot.send_message.assert_not_awaited()

    await click(state, "type", "0.1")
    assert state.cache.get(CACHE_KEY)["view"] == "type"
    await click(state, "back")

    session = state.cache.get(CACHE_KEY)
    assert session["view"] == "overview"
    assert session["view_kind"] == "photo"
    assert session["category_page"] == 2
    assert session["active_message_id"] == 4004
    state.bot.send_message.assert_awaited_once()
    state.metadata.assert_awaited_once()
    state.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_replacement_keeps_magnet_cache_key_and_exact_uri(state, monkeypatch):
    # Magnet is cache type index zero, but appears after four larger drive categories.
    state.search.return_value = resources(extra_types=4)
    await start(state)
    await click(state, "cat", "2")
    await click(state, "type", "4.1")
    text = state.bot.send_message.await_args.kwargs["text"]
    url = html.unescape(re.search(r'href="([^"]+)">获取磁力', text).group(1))
    payload = parse_qs(urlparse(url).query)["start"][0]
    key, type_index, item_index, digest = parse_magnet_start_payload(payload)

    assert key == CACHE_KEY
    assert type_index == 0
    assert state.cache.get(CACHE_KEY)["active_message_id"] == 4004
    assert digest == magnet_uri_digest(MAGNET_URI)
    monkeypatch.setattr(bot_module, "search_cache", state.cache)
    monkeypatch.setattr(bot_module, "auto_delete_message", Mock())
    assert bot_module._get_cached_magnet(key, type_index, item_index) == (MAGNET_URI, None)
    reply = SimpleNamespace(chat_id=2002, message_id=5005)
    message = SimpleNamespace(
        reply_text=AsyncMock(return_value=reply), reply_document=AsyncMock(return_value=reply),
    )
    update = SimpleNamespace(
        message=message, effective_user=SimpleNamespace(id=2002),
        effective_chat=SimpleNamespace(id=2002, type="private"),
        effective_message=message,
    )
    await bot_module.start_command(update, SimpleNamespace(args=[payload], bot=state.bot))

    assert html.escape(MAGNET_URI) in message.reply_text.await_args.args[0]
    message.reply_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_replacement_binding_commits_before_old_photo_deletion(state):
    await start(state)
    observed_bindings = []

    async def inspect_binding(**kwargs):
        session = state.cache.get(CACHE_KEY)
        observed_bindings.append((session["active_message_id"], session["view_kind"]))
        return True

    state.bot.delete_message.side_effect = inspect_binding
    await click(state, "all")
    assert observed_bindings == [(4004, "text")]
    state.bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=3003)


@pytest.mark.asyncio
async def test_failed_return_to_poster_retains_working_text_list(state):
    await start(state)
    await click(state, "all")
    before = dict(state.cache.get(CACHE_KEY))
    reset_bot(state)
    state.bot.edit_message_media.side_effect = TimedOut()

    await click(state, "back")

    session = state.cache.get(CACHE_KEY)
    assert session["active_message_id"] == before["active_message_id"]
    assert session["view_revision"] == before["view_revision"]
    assert session["view_kind"] == "text"
    assert session["view"] == "all"
    state.bot.send_message.assert_not_awaited()
    state.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_queued_callback_rechecks_expiration_after_obtaining_lock(state):
    await start(state)
    update = callback(state, "all")
    lock = state.cache.get(CACHE_KEY)["_lock"]
    await lock.acquire()
    reset_bot(state)
    task = asyncio.create_task(
        media_search.handle_media_callback(update, SimpleNamespace(bot=state.bot))
    )
    await asyncio.sleep(0)
    state.cache._timestamps[CACHE_KEY] -= state.cache.ttl + 1
    lock.release()
    await asyncio.wait_for(task, 1)

    assert_no_telegram_mutation(state)
    update.callback_query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_candidate_paging_edits_message_without_refetch_or_cache_extension(state):
    state.metadata.return_value = [movie(year=str(2000 + index), identity=index + 1) for index in range(9)]
    await start(state)
    timestamp = state.cache._timestamps[CACHE_KEY]
    reset_bot(state)

    await click(state, "cand", "2")
    await click(state, "cand", "3")

    assert state.cache.get(CACHE_KEY)["candidate_page"] == 3
    assert state.cache.get(CACHE_KEY)["active_message_id"] == 3003
    assert state.cache._timestamps[CACHE_KEY] == timestamp
    assert state.bot.edit_message_text.await_count == 2
    state.bot.send_message.assert_not_awaited()
    state.metadata.assert_awaited_once()
    state.search.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action,arg", [("pick", "999"), ("type", "999.1"), ("retry", "")])
async def test_invalid_action_indices_or_unoffered_retry_do_not_change_view(state, action, arg):
    await start(state)
    reset_bot(state)
    state.search.reset_mock()

    update = await click(state, action, arg)

    assert_no_telegram_mutation(state)
    state.search.assert_not_awaited()
    update.callback_query.answer.assert_awaited()


@pytest.mark.asyncio
async def test_type_pages_keep_user_result_limit_and_edit_same_list(state, monkeypatch):
    state.search.return_value = {
        "total": 5,
        "merged_by_type": {
            "quark": [
                {"url": f"https://pan.quark.cn/s/{index}", "note": f"条目 {index}"}
                for index in range(5)
            ]
        },
    }
    monkeypatch.setattr(
        media_search.settings_manager, "get_settings",
        Mock(return_value=UserSettings(user_id=2002, result_limit=2)),
    )
    await start(state)
    await click(state, "type", "0.1")
    first_page = state.bot.send_message.await_args.kwargs["text"]
    assert "条目 0" in first_page and "条目 1" in first_page
    assert "条目 2" not in first_page

    await click(state, "type", "0.2")
    second_page = state.bot.edit_message_text.await_args.kwargs["text"]
    assert "条目 2" in second_page and "条目 3" in second_page
    assert "条目 0" not in second_page and "条目 4" not in second_page
    assert state.cache.get(CACHE_KEY)["active_message_id"] == 4004
    state.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_poster_timeout_replaces_loading_with_usable_text_overview(state):
    state.bot.edit_message_media.side_effect = TimedOut()
    await start(state)

    session = state.cache.get(CACHE_KEY)
    assert session["active_message_id"] == 3003
    assert session["view_kind"] == "text"
    assert session["view"] == "overview"
    assert session["view_revision"] == 1
    assert session["results"]["total"] == 1
    state.bot.edit_message_media.assert_awaited_once()
    state.bot.edit_message_text.assert_awaited_once()
    state.bot.send_message.assert_not_awaited()
    await click(state, "all")
    assert state.cache.get(CACHE_KEY)["view"] == "all"
    assert "获取磁力" in state.bot.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_resource_refresh_renews_cache_only_after_successful_publish(state):
    await start(state)
    state.cache._timestamps[CACHE_KEY] -= 30
    original_timestamp = state.cache._timestamps[CACHE_KEY]
    original_session = state.cache.get(CACHE_KEY)
    original_revision = original_session["view_revision"]
    state.bot.edit_message_caption.side_effect = TimedOut()

    await click(state, "refresh")

    assert state.search.await_count == 2
    assert state.cache._timestamps[CACHE_KEY] == original_timestamp
    assert state.cache.get(CACHE_KEY)["view_revision"] == original_revision
    state.bot.edit_message_caption.side_effect = None
    await click(state, "refresh")

    renewed_timestamp = state.cache._timestamps[CACHE_KEY]
    assert renewed_timestamp > original_timestamp
    assert state.cache.get(CACHE_KEY) is original_session
    await click(state, "cat", "1")
    assert state.cache._timestamps[CACHE_KEY] == renewed_timestamp
