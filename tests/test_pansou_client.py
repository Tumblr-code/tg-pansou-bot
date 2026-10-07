from __future__ import annotations

import asyncio

import httpx
import pytest

import pansou_client as client_module
from config import settings
from pansou_client import PansouClient


def fresh_client() -> PansouClient:
    PansouClient._instance = None
    client = PansouClient()
    client.clear_runtime_cache()
    client._inflight_searches.clear()
    client._client = None
    return client


@pytest.mark.asyncio
async def test_httpx_uses_phase_specific_timeouts(monkeypatch) -> None:
    captured = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr(client_module.httpx, "AsyncClient", FakeAsyncClient)
    client = fresh_client()

    await client._get_client()

    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 5
    assert timeout.pool == 5
    assert timeout.write == 10
    assert timeout.read == settings.search_timeout
    await client.close()


@pytest.mark.asyncio
async def test_duplicate_search_is_shared_and_waiter_cancellation_is_isolated(monkeypatch) -> None:
    client = fresh_client()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_execute(**kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"total": 1, "merged_by_type": {"quark": [{"url": "https://example.test"}]}}

    monkeypatch.setattr(client, "_execute_search_with_capacity", fake_execute)
    first = asyncio.create_task(client.search("三体"))
    await started.wait()
    second = asyncio.create_task(client.search("三体"))
    await asyncio.sleep(0)

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()

    assert (await second)["total"] == 1
    assert (await client.search("三体"))["total"] == 1
    assert calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_search_queue_returns_busy_after_timeout(monkeypatch) -> None:
    client = fresh_client()
    client._search_semaphore = asyncio.Semaphore(1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_request(**kwargs):
        started.set()
        await release.wait()
        return {"total": 0, "merged_by_type": {}}

    monkeypatch.setattr(client, "_execute_search_request", fake_request)
    monkeypatch.setattr(settings, "search_queue_timeout", 0.01)

    first = asyncio.create_task(client.search("第一条", force_refresh=True))
    await started.wait()
    busy = await client.search("第二条", force_refresh=True)

    assert busy["error_code"] == "SEARCH_BUSY"
    release.set()
    await first
    await client.close()


@pytest.mark.asyncio
async def test_client_rejects_keyword_boundaries_before_network() -> None:
    client = fresh_client()

    assert (await client.search("a"))["error_code"] == "INVALID_KEYWORD"
    assert (await client.search("x" * (settings.max_keyword_length + 1)))["error_code"] == "INVALID_KEYWORD"
    await client.close()


@pytest.mark.parametrize("view", ["type", "all"])
def test_long_magnets_use_result_actions_without_destroying_http_links(view) -> None:
    from message_utils import ensure_telegram_text

    client = fresh_client()
    magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&tr=https://tracker.test/" + "x" * 900
    links = [{"url": magnet, "note": f"资源 {index}"} for index in range(5)]
    links.append({"url": "https://example.test/file?a=1&b=2", "note": "网页资源"})
    results = {"total": len(links), "merged_by_type": {"magnet": links}}

    if view == "type":
        text = client.format_type_results(
            results, "测试", "magnet", per_page=6,
            cache_key="-1001:2002:3003", bot_username="ExampleSearch_bot",
        )
    else:
        text = client.format_results(
            results, "测试", per_type_limit=6,
            cache_key="-1001:2002:3003", bot_username="ExampleSearch_bot",
        )
    text = ensure_telegram_text(text, parse_mode="HTML")

    assert 'href="magnet:' not in text
    assert text.count('>获取磁力</a>') == 5
    assert text.count('href="https://t.me/ExampleSearch_bot?start=') == 5
    assert "复制到下载器" in text
    assert 'href="https://example.test/file?a=1&amp;b=2"' in text
    assert "内容过长已截断" not in text
