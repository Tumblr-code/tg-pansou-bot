from __future__ import annotations

import html
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, quote, urlparse

import pytest
from telegram import InputFile
from telegram.constants import ParseMode

import bot
from magnet_links import (
    build_magnet_deep_link,
    build_magnet_start_payload,
    is_magnet_url,
    magnet_uri_digest,
    parse_magnet_callback,
    parse_magnet_start_payload,
)
from runtime_state import LRUCache

CACHE_KEY = "-1001:2002:3003"
MAGNET_PREFIX = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn="


def make_magnet(length: int) -> str:
    return MAGNET_PREFIX + "x" * (length - len(MAGNET_PREFIX))


def make_unicode_magnet(utf16_units: int) -> str:
    prefix = MAGNET_PREFIX + "图片🙂&tr=https://tracker.example/announce?x=1&y=2&padding="
    padding = utf16_units - len(prefix.encode("utf-16-le")) // 2
    return prefix + "x" * padding


def results_for(*urls: str) -> dict:
    return {
        "total": len(urls) + 1,
        "merged_by_type": {
            "quark": [{"url": "https://pan.quark.cn/s/example"}],
            "magnet": [{"url": url, "title": f"Result {i + 1}"} for i, url in enumerate(urls)],
        }
    }


def flatten(rows: list) -> list:
    return [button for row in rows for button in row]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (make_magnet(100), True),
        (make_magnet(100).replace("magnet:", "MAGNET:", 1), True),
        ("https://example.test/?url=magnet:?xt=urn:btih:abc", False),
        ("ed2k://example", False),
        ("", False),
        (None, False),
    ],
)
def test_is_magnet_url_checks_the_uri_scheme(value, expected: bool) -> None:
    assert is_magnet_url(value) is expected


@pytest.mark.parametrize("cache_key", [CACHE_KEY, "2002:2002:3003"])
def test_start_payload_round_trips_signed_cache_key_and_indices(cache_key: str) -> None:
    payload = build_magnet_start_payload(cache_key, 10, 4096, make_magnet(257))
    assert parse_magnet_start_payload(payload) == (cache_key, 10, 4096, magnet_uri_digest(make_magnet(257)))
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", payload)
    assert quote(payload, safe="") == payload


def test_deep_link_is_url_safe_and_fits_telegram_limit_for_large_ids() -> None:
    cache_key = f"-{2**52 - 1}:{2**52 - 1}:{2**31 - 1}"
    url = build_magnet_deep_link("DifferentSearch_bot", cache_key, 123, 1000000, make_magnet(257))
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "t.me"
    assert parsed.path == "/DifferentSearch_bot"
    payload = parse_qs(parsed.query)["start"][0]
    assert len(payload) <= 64
    assert parse_magnet_start_payload(payload) == (cache_key, 123, 1000000, magnet_uri_digest(make_magnet(257)))
    assert "magnet:" not in url


def test_payload_builder_refuses_values_that_would_exceed_64_characters() -> None:
    with pytest.raises(ValueError, match="limit"):
        build_magnet_start_payload(CACHE_KEY, 0, 10**100, make_magnet(257))


@pytest.mark.parametrize(
    "payload",
    [
        "magnet_bad", "magnet_0_1_1_0_0", "magnet_1_0_1_0_0", "magnet_1_1_0_0_0",
        "magnet_1_1_1_-1_0", "magnet_1_1_1_0_-1", "magnet_01_1_1_0_0",
        "magnet_1_1_1_0_0&x=1", "magnet_1_1_1_0_0%2F", "magnet_1_1_1_0_0/",
        "magnet_1_1_1_0_0_0", "magnet_-1_1_1_0_" + "z" * 64,
    ],
)
def test_start_payload_rejects_malformed_or_noncanonical_values(payload: str) -> None:
    assert parse_magnet_start_payload(payload) == (None, None, None, None)


def test_callback_parser_keeps_the_complete_signed_cache_key() -> None:
    assert parse_magnet_callback(f"magnet:{CACHE_KEY}:1:5") == (CACHE_KEY, 1, 5)


@pytest.mark.parametrize(
    "data",
    [
        "",
        f"type:{CACHE_KEY}:1:0",
        f"magnet:{CACHE_KEY}:x:0",
        f"magnet:{CACHE_KEY}:1:x",
        f"magnet:{CACHE_KEY}:-1:0",
        f"magnet:{CACHE_KEY}:1:-1",
        "magnet:incomplete",
    ],
)
def test_callback_parser_rejects_malformed_keys_and_indices(data: str) -> None:
    assert parse_magnet_callback(data) == (None, None, None)


@pytest.fixture
def callback_state(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    cache = LRUCache(max_size=5, ttl=300)
    sent = SimpleNamespace(chat_id=-1001, message_id=4004)
    message = SimpleNamespace(
        chat_id=-1001,
        message_id=3003,
        reply_text=AsyncMock(return_value=sent),
        reply_document=AsyncMock(return_value=sent),
    )
    query = SimpleNamespace(
        data=f"magnet:{CACHE_KEY}:1:0",
        message=message,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=2002),
        effective_chat=SimpleNamespace(id=-1001, type="supergroup"),
        effective_message=message,
    )
    auto_delete = Mock()
    monkeypatch.setattr(bot, "search_cache", cache)
    monkeypatch.setattr(bot, "auto_delete_message", auto_delete)
    monkeypatch.setattr(bot, "schedule_message_deletion", Mock())
    return SimpleNamespace(
        cache=cache,
        update=update,
        query=query,
        message=message,
        sent=sent,
        auto_delete=auto_delete,
        context=SimpleNamespace(bot=SimpleNamespace(username="DifferentSearch_bot")),
    )


def cache_result(state: SimpleNamespace, uri: str) -> None:
    state.cache.set(CACHE_KEY, {"keyword": "example", "results": results_for(uri)})


def assert_no_magnet_reply(state: SimpleNamespace) -> None:
    state.message.reply_text.assert_not_awaited()
    state.message.reply_document.assert_not_awaited()
    state.auto_delete.assert_not_called()
    state.query.answer.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("other_identity", ["user", "chat", "message"])
async def test_callback_rejects_other_search_owners(callback_state, other_identity: str) -> None:
    state = callback_state
    cache_result(state, make_magnet(257))
    if other_identity == "user":
        state.update.effective_user.id = 9999
    elif other_identity == "chat":
        state.update.effective_chat.id = -9999
        state.message.chat_id = -9999
    else:
        state.message.message_id = 9999

    await bot.handle_callback(state.update, state.context)

    assert_no_magnet_reply(state)


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_status", ["missing", "expired"])
async def test_callback_rejects_missing_or_expired_cache(callback_state, cache_status: str) -> None:
    state = callback_state
    if cache_status == "expired":
        cache_result(state, make_magnet(257))
        state.cache._timestamps[CACHE_KEY] -= state.cache.ttl + 1

    await bot.handle_callback(state.update, state.context)

    assert_no_magnet_reply(state)
    assert state.cache.get(CACHE_KEY) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        "magnet:-1001:2002:1:0",
        "magnet:extra:-1001:2002:3003:1:0",
        "magnet:chat:2002:3003:1:0",
        f"magnet:{CACHE_KEY}:1",
        f"magnet:{CACHE_KEY}:-1:0",
        f"magnet:{CACHE_KEY}:1:-1",
        f"magnet:{CACHE_KEY}:99:0",
        f"magnet:{CACHE_KEY}:1:99",
        f"magnet:{CACHE_KEY}:x:0",
        f"magnet:{CACHE_KEY}:1:x",
        f"magnet:{CACHE_KEY}:0:0",
    ],
)
async def test_callback_rejects_bad_indices_and_non_magnet_results(callback_state, data: str) -> None:
    state = callback_state
    cache_result(state, make_magnet(257))
    state.query.data = data

    await bot.handle_callback(state.update, state.context)

    assert_no_magnet_reply(state)


@pytest.mark.asyncio
@pytest.mark.parametrize("utf16_units", [256, 257, 3900])
async def test_callback_returns_complete_escaped_magnet_as_code(callback_state, utf16_units: int) -> None:
    state = callback_state
    uri = make_unicode_magnet(utf16_units)
    cache_result(state, uri)

    await bot.handle_callback(state.update, state.context)

    state.query.answer.assert_awaited()
    state.message.reply_text.assert_awaited_once()
    state.message.reply_document.assert_not_awaited()
    call = state.message.reply_text.await_args
    text = call.args[0] if call.args else call.kwargs["text"]
    assert call.kwargs["parse_mode"] == ParseMode.HTML
    code = re.search(r"<code>(.*?)</code>", text, re.DOTALL)
    assert code is not None
    assert html.unescape(code.group(1)) == uri
    assert "&amp;tr=" in code.group(1)
    assert len(uri.encode("utf-16-le")) // 2 == utf16_units
    state.auto_delete.assert_called_once_with(state.sent)


@pytest.mark.asyncio
async def test_html_expansion_over_4096_never_truncates_visible_magnet(
    callback_state, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = callback_state
    uri = MAGNET_PREFIX + "&dn=>" * 550
    assert len(uri.encode("utf-16-le")) // 2 <= 3900
    assert len(html.escape(uri)) > 4096
    cache_result(state, uri)
    truncator = Mock(side_effect=AssertionError("Full magnet delivery must bypass truncation"))
    monkeypatch.setattr(bot, "ensure_telegram_text", truncator)

    await bot.handle_callback(state.update, state.context)

    state.message.reply_text.assert_awaited_once()
    state.message.reply_document.assert_not_awaited()
    call = state.message.reply_text.await_args
    text = call.args[0] if call.args else call.kwargs["text"]
    assert call.kwargs["parse_mode"] == ParseMode.HTML
    code = re.search(r"<code>(.*?)</code>", text, re.DOTALL)
    assert code is not None
    assert html.unescape(code.group(1)) == uri
    truncator.assert_not_called()
    state.auto_delete.assert_called_once_with(state.sent)


@pytest.mark.asyncio
@pytest.mark.parametrize("utf16_units", [3901, 8000])
async def test_callback_returns_complete_utf8_file_above_text_limit(callback_state, utf16_units: int) -> None:
    state = callback_state
    uri = make_unicode_magnet(utf16_units)
    cache_result(state, uri)

    await bot.handle_callback(state.update, state.context)

    state.query.answer.assert_awaited()
    state.message.reply_text.assert_not_awaited()
    state.message.reply_document.assert_awaited_once()
    call = state.message.reply_document.await_args
    document = call.args[0] if call.args else call.kwargs["document"]
    assert isinstance(document, InputFile)
    assert document.filename.endswith(".txt")
    assert document.input_file_content == uri.encode("utf-8")
    assert len(uri.encode("utf-16-le")) // 2 == utf16_units
    state.auto_delete.assert_called_once_with(state.sent)


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["type", "all"])
async def test_result_callbacks_put_deep_links_in_body_without_magnet_buttons(
    callback_state, monkeypatch: pytest.MonkeyPatch, view: str,
) -> None:
    state = callback_state
    short_uri, long_uri = make_magnet(256), make_magnet(257)
    if view == "type":
        urls = ["https://example.test/download"] * 5 + [short_uri, long_uri]
        state.query.data = f"type:{CACHE_KEY}:magnet:2"
        first_index, long_index = 5, 6
    else:
        urls = [short_uri, long_uri, "https://example.test/download"]
        state.query.data = f"all:{CACHE_KEY}"
        first_index, long_index = 0, 1
    state.cache.set(CACHE_KEY, {"keyword": "example", "results": results_for(*urls)})
    monkeypatch.setattr(
        bot, "settings_manager",
        SimpleNamespace(get_settings=Mock(return_value=SimpleNamespace(result_limit=5))),
    )
    edit = AsyncMock()
    monkeypatch.setattr(bot, "_safe_edit_message", edit)

    await bot.handle_callback(state.update, state.context)

    edit.assert_awaited_once()
    markup = edit.await_args.kwargs["reply_markup"]
    actions = [
        button for button in flatten(markup.inline_keyboard)
        if button.copy_text is not None or (button.callback_data or "").startswith("magnet:")
    ]
    assert actions == []
    text = edit.await_args.args[1]
    hrefs = re.findall(r'<a href="([^"]+)">获取磁力</a>', text)
    assert len(hrefs) == 2
    coordinates = [
        parse_magnet_start_payload(parse_qs(urlparse(html.unescape(url)).query)["start"][0])
        for url in hrefs
    ]
    assert coordinates == [
        (CACHE_KEY, 1, first_index, magnet_uri_digest(short_uri)),
        (CACHE_KEY, 1, long_index, magnet_uri_digest(long_uri)),
    ]
    assert all(url.startswith("https://t.me/DifferentSearch_bot?start=") for url in hrefs)
    assert short_uri not in text and long_uri not in text
    assert "下方" not in text
    assert any(button.text == "🔙 返回分类" for button in flatten(markup.inline_keyboard))
    bot.schedule_message_deletion.assert_called_once_with(-1001, 3003)


@pytest.fixture
def start_state(callback_state, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = callback_state
    state.context.args = [build_magnet_start_payload(CACHE_KEY, 1, 0, make_magnet(257))]
    state.update.effective_chat = SimpleNamespace(id=2002, type="private")
    state.update.message = state.message
    state.message.chat_id = 2002
    state.message.message_id = 4004
    state.error_reply = AsyncMock()
    monkeypatch.setattr(bot, "reply_with_auto_delete", state.error_reply)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("uri_length", [256, 257, 3900, 3901, 8000])
async def test_start_from_group_search_delivers_complete_uri_only_in_owner_private_chat(
    start_state, uri_length: int,
) -> None:
    state = start_state
    uri = make_unicode_magnet(uri_length)
    cache_result(state, uri)
    state.context.args = [build_magnet_start_payload(CACHE_KEY, 1, 0, uri)]

    await bot.start_command(state.update, state.context)

    state.error_reply.assert_not_awaited()
    if uri_length <= 3900:
        state.message.reply_text.assert_awaited_once()
        state.message.reply_document.assert_not_awaited()
        text = state.message.reply_text.await_args.args[0]
        code = re.search(r"<code>(.*?)</code>", text, re.DOTALL)
        assert html.unescape(code.group(1)) == uri
        assert "3 分钟" in text
    else:
        state.message.reply_text.assert_not_awaited()
        state.message.reply_document.assert_awaited_once()
        document = state.message.reply_document.await_args.kwargs["document"]
        assert document.input_file_content == uri.encode("utf-8")
    state.auto_delete.assert_called_once_with(state.sent)


@pytest.mark.asyncio
async def test_start_preserves_html_expansion_without_truncating(start_state, monkeypatch) -> None:
    state = start_state
    uri = MAGNET_PREFIX + "&dn=>" * 550
    assert len(html.escape(uri)) > 4096
    cache_result(state, uri)
    state.context.args = [build_magnet_start_payload(CACHE_KEY, 1, 0, uri)]
    monkeypatch.setattr(bot, "ensure_telegram_text", Mock(side_effect=AssertionError("truncated")))

    await bot.start_command(state.update, state.context)

    text = state.message.reply_text.await_args.args[0]
    assert html.unescape(re.search(r"<code>(.*?)</code>", text, re.DOTALL).group(1)) == uri


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["other_user", "other_chat", "original_group", "other_group"])
async def test_start_does_not_reveal_magnet_to_wrong_user_or_group(start_state, case: str) -> None:
    state = start_state
    cache_result(state, make_magnet(257))
    if case == "other_user":
        state.update.effective_user.id = 9999
        state.update.effective_chat.id = 9999
    elif case == "other_chat":
        state.update.effective_chat.id = 9999
    else:
        state.update.effective_chat.id = -1001 if case == "original_group" else -9999
        state.update.effective_chat.type = "supergroup"

    await bot.start_command(state.update, state.context)

    state.error_reply.assert_awaited_once()
    state.message.reply_text.assert_not_awaited()
    state.message.reply_document.assert_not_awaited()
    state.auto_delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["expired", "missing", "type_index", "item_index", "http"])
async def test_start_checks_cache_ttl_and_result_indices(start_state, case: str) -> None:
    state = start_state
    if case != "missing":
        cache_result(state, make_magnet(257))
    if case == "expired":
        state.cache._timestamps[CACHE_KEY] -= state.cache.ttl + 1
    elif case in {"type_index", "item_index", "http"}:
        indices = {"type_index": (99, 0), "item_index": (1, 99), "http": (0, 0)}
        state.context.args = [build_magnet_start_payload(CACHE_KEY, *indices[case], make_magnet(257))]

    await bot.start_command(state.update, state.context)

    state.error_reply.assert_awaited_once()
    state.message.reply_text.assert_not_awaited()
    state.message.reply_document.assert_not_awaited()
    state.auto_delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [["magnet_bad"], ["magnet_1_1_1_0_0", "extra"], ["magnet_1_1_1_0_0%26x=1"]],
)
async def test_start_rejects_bad_payload_without_falling_through_to_welcome(start_state, args) -> None:
    state = start_state
    state.context.args = args

    await bot.start_command(state.update, state.context)

    state.error_reply.assert_awaited_once()
    assert "参数错误" in state.error_reply.await_args.args[1]
    state.message.reply_text.assert_not_awaited()
    state.message.reply_document.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [[], ["ordinary_referral"]])
async def test_normal_start_welcome_is_unchanged(start_state, args) -> None:
    state = start_state
    state.context.args = args
    state.update.effective_user.first_name = "测试"

    await bot.start_command(state.update, state.context)

    state.error_reply.assert_awaited_once()
    assert "网盘搜索机器人" in state.error_reply.await_args.args[1]
    state.message.reply_document.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["refreshed_uri", "tampered_digest"])
async def test_start_rejects_stale_or_tampered_uri_fingerprint(start_state, case: str) -> None:
    state = start_state
    original_uri = make_magnet(257)
    cache_result(state, original_uri)
    state.context.args = [build_magnet_start_payload(CACHE_KEY, 1, 0, original_uri)]
    if case == "refreshed_uri":
        # Refresh overwrites the same chat/user/message cache entry with different results.
        cache_result(state, original_uri + "&tr=https://different.example/announce")
    else:
        prefix, digest = state.context.args[0].rsplit("_", 1)
        replacement = "0" if digest[0] != "0" else "1"
        state.context.args = [prefix + "_" + replacement + digest[1:]]

    await bot.start_command(state.update, state.context)

    state.error_reply.assert_awaited_once()
    assert "搜索结果已更新" in state.error_reply.await_args.args[1]
    state.message.reply_text.assert_not_awaited()
    state.message.reply_document.assert_not_awaited()
    state.auto_delete.assert_not_called()
