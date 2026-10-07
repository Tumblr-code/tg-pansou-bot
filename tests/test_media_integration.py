from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import bot
import search_flow
from logger import redact_sensitive_data
from runtime_state import LRUCache


@pytest.mark.asyncio
async def test_search_command_loading_message_binds_media_session(monkeypatch):
    initial = SimpleNamespace(message_id=42, message_thread_id=16)
    message = SimpleNamespace(reply_text=AsyncMock(return_value=initial))
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=12),
                             effective_chat=SimpleNamespace(id=-1001))
    context = SimpleNamespace(bot=object())
    start = AsyncMock()
    monkeypatch.setattr(search_flow, 'check_search_rate_limit', Mock(return_value=(True, 0)))
    monkeypatch.setattr(search_flow, 'start_media_search', start)
    await search_flow.perform_search(update, context, '希望', limit=7)
    message.reply_text.assert_awaited_once()
    assert start.await_args.args == (context.bot,)
    assert start.await_args.kwargs['message_id'] == 42
    assert start.await_args.kwargs['message_thread_id'] == 16
    assert start.await_args.kwargs['options']['limit'] == 7


def test_legacy_callbacks_cannot_bypass_versioned_search(monkeypatch):
    cache = LRUCache()
    cache.set('-1001:12:42', {'view_revision': 1})
    monkeypatch.setattr(bot, 'search_cache', cache)
    assert not bot._is_cache_owner('-1001:12:42', -1001, 12, 42)
    assert bot._is_cache_owner('-1001:12:43', -1001, 12, 43)


def test_tmdb_api_key_query_is_redacted_from_logs():
    value = {'event': 'GET https://api.themoviedb.org/3/search/multi?api_key=private-test-value&query=hello'}
    redacted = redact_sensitive_data(None, None, value)
    assert 'private-test-value' not in redacted['event']
    assert 'api_key=[REDACTED]&query=hello' in redacted['event']
