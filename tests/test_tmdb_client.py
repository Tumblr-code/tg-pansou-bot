from __future__ import annotations

import httpx
import pytest

import tmdb_client as client_module
from tmdb_client import TMDBClient, unique_exact_match


def movie(item_id=1, title="希望", year="2020", **fields):
    return {
        "id": item_id, "media_type": "movie", "title": title,
        "original_title": "Hope", "release_date": f"{year}-01-01",
        "overview": "影片简介", "poster_path": "/poster.jpg", **fields,
    }


def payload(*items, total_pages=1):
    return {"results": list(items), "total_pages": total_pages}


def configuration():
    return {"images": {
        "secure_base_url": "https://image.tmdb.org/t/p/",
        "poster_sizes": ["w185", "w342", "w500", "original"],
    }}


@pytest.mark.asyncio
async def test_search_bearer_chinese_movies_tv_and_official_poster_configuration():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer unit-test-read-token"
        assert request.extensions["timeout"] == {
            "connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0,
        }
        if request.url.path == "/3/configuration":
            return httpx.Response(200, json=configuration())
        assert request.url.path == "/3/search/multi"
        assert dict(request.url.params) == {
            "query": "希望", "language": "zh-CN", "include_adult": "false", "page": "1",
        }
        return httpx.Response(200, json=payload(
            movie(),
            {"id": 2, "media_type": "person", "name": "希望"},
            {"id": 3, "media_type": "tv", "name": "希望", "original_name": "Hope TV",
             "first_air_date": "2023-02-03", "overview": None, "poster_path": None},
            movie(),  # Duplicate media IDs must not create a false ambiguity.
        ))

    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    result = await client.search("希望")
    assert len(result) == 2
    assert result[0] == {
        "id": 1, "media_type": "movie", "title": "希望", "original_title": "Hope",
        "year": "2020", "overview": "影片简介",
        "poster_url": "https://image.tmdb.org/t/p/w500/poster.jpg",
        "source_url": "https://www.themoviedb.org/movie/1", "search_complete": True,
    }
    assert result[1]["year"] == "2023"
    assert result[1]["overview"] == ""
    assert result[1]["poster_url"] is None
    assert result[1]["source_url"] == "https://www.themoviedb.org/tv/3"
    assert len(requests) == 2
    await client.close()


@pytest.mark.asyncio
async def test_without_token_or_keyword_does_not_send_requests():
    def handler(request):
        pytest.fail("disabled metadata must not make HTTP requests")

    client = TMDBClient("  ", api_key="", transport=httpx.MockTransport(handler))
    assert not client.enabled
    assert await client.search("希望") == []
    enabled = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    assert await enabled.search("  ") == []
    await client.close()
    await enabled.close()


@pytest.mark.asyncio
async def test_v3_api_key_authenticates_search_and_configuration_without_bearer():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api.themoviedb.org"
        assert request.url.params["api_key"] == "unit-test-v3-api-key"
        assert "Authorization" not in request.headers
        if request.url.path == "/3/configuration":
            return httpx.Response(200, json=configuration())
        return httpx.Response(200, json=payload(movie()))

    client = TMDBClient("", api_key="unit-test-v3-api-key", transport=httpx.MockTransport(handler))
    assert client.enabled
    results = await client.search("希望")
    assert results[0]["poster_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert len(requests) == 2
    await client.close()


@pytest.mark.asyncio
async def test_bearer_has_priority_when_both_credentials_are_configured():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer unit-test-read-token"
        assert "api_key" not in request.url.params
        return httpx.Response(200, json=payload(movie(poster_path=None)))

    client = TMDBClient(
        "unit-test-read-token", api_key="unit-test-v3-api-key", transport=httpx.MockTransport(handler),
    )
    assert await client.search("希望")
    await client.close()


@pytest.mark.asyncio
async def test_api_key_is_not_forwarded_to_redirect_destinations():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://untrusted.test/steal"})

    client = TMDBClient("", api_key="unit-test-v3-api-key", transport=httpx.MockTransport(handler))
    assert await client.search("希望") == []
    assert len(requests) == 1
    assert requests[0].url.host == "api.themoviedb.org"
    await client.close()


@pytest.mark.asyncio
async def test_api_key_config_is_loaded_from_settings(monkeypatch):
    monkeypatch.setattr(client_module.settings, "tmdb_read_access_token", None)
    monkeypatch.setattr(client_module.settings, "tmdb_api_key", "unit-test-config-key")

    def handler(request):
        assert request.url.params["api_key"] == "unit-test-config-key"
        return httpx.Response(200, json=payload())

    client = TMDBClient(transport=httpx.MockTransport(handler))
    assert client.enabled
    assert await client.search("文档") == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "unauthorized", "invalid_json"])
async def test_search_failure_falls_back_without_logging_token_query_or_error_message(monkeypatch, failure):
    logged = []

    class FakeLogger:
        def warning(self, event, **fields):
            logged.append((event, fields))

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("must-not-log-this-token-or-query")
        if failure == "unauthorized":
            return httpx.Response(401, json={"status_message": "must-not-log-this-token-or-query"})
        return httpx.Response(200, content="invalid-json-with-secret")

    monkeypatch.setattr(client_module, "logger", FakeLogger())
    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    assert await client.search("private-keyword") == []
    assert len(logged) == 1
    assert logged[0][0] == "tmdb_search_failed"
    assert set(logged[0][1]) == {"error_type"}
    assert "must-not-log" not in repr(logged)
    assert client._cache == {}
    await client.close()


@pytest.mark.asyncio
async def test_actual_wall_timeout_falls_back(monkeypatch):
    import asyncio

    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=payload(movie()))

    monkeypatch.setattr(client_module, "TMDB_TIMEOUT", 0.01)
    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    assert await client.search("希望") == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("config_status, config", [
    (503, {}),
    (200, {"images": {"secure_base_url": "https://untrusted.test/t/p/", "poster_sizes": ["w500"]}}),
    (200, {"images": {"secure_base_url": "https://image.tmdb.org/t/p/", "poster_sizes": []}}),
])
async def test_unavailable_or_invalid_image_configuration_keeps_metadata(config_status, config):
    def handler(request):
        if request.url.path.endswith("/configuration"):
            return httpx.Response(config_status, json=config)
        return httpx.Response(200, json=payload(movie()))

    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    result = await client.search("希望")
    assert result[0]["title"] == "希望"
    assert result[0]["overview"] == "影片简介"
    assert result[0]["poster_url"] is None
    await client.close()


@pytest.mark.asyncio
async def test_no_poster_skips_configuration_and_empty_search_is_cached():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        assert request.url.path == "/3/search/multi"
        if request.url.params["query"] == "文档":
            return httpx.Response(200, json=payload())
        return httpx.Response(200, json=payload(movie(poster_path=None, release_date="")))

    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    result = await client.search("希望")
    assert result[0]["poster_url"] is None
    assert result[0]["year"] == ""
    assert await client.search("文档") == []
    assert await client.search("文档") == []
    assert len(requests) == 2
    await client.close()


@pytest.mark.asyncio
async def test_cache_is_bounded_lru_expires_after_one_hour_and_returns_isolated_records(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: now[0])
    queries = []
    configurations = []

    def handler(request):
        if request.url.path.endswith("/configuration"):
            configurations.append(True)
            return httpx.Response(200, json=configuration())
        queries.append(request.url.params["query"])
        return httpx.Response(200, json=payload(movie()))

    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler), cache_size=2)
    first = await client.search("Hope")
    first[0]["poster_url"] = "mutated-by-active-view"
    assert (await client.search(" hope "))[0]["poster_url"].startswith("https://image.tmdb.org/")
    await client.search("二")
    await client.search("Hope")  # Keep Hope as most recently used.
    await client.search("三")
    assert len(client._cache) == 2
    assert queries == ["Hope", "二", "三"]
    await client.search("二")  # Was evicted by the third distinct query.
    assert queries == ["Hope", "二", "三", "二"]
    assert len(configurations) == 1
    now[0] += 3601
    await client.search("三")
    assert queries[-1] == "三"
    assert len(queries) == 5
    assert len(configurations) == 2
    await client.close()
    assert client._cache == {}


@pytest.mark.asyncio
async def test_only_first_twenty_candidates_are_cached_and_partial_search_prevents_autochoice():
    def handler(request):
        return httpx.Response(200, json=payload(
            *(movie(index + 1, "希望" if index == 0 else f"其他{index}", poster_path=None)
              for index in range(30)), total_pages=2,
        ))

    client = TMDBClient("unit-test-read-token", transport=httpx.MockTransport(handler))
    candidates = await client.search("希望")
    assert len(candidates) == 20
    assert all(candidate["search_complete"] is False for candidate in candidates)
    assert unique_exact_match("希望", candidates) is None
    await client.close()


def test_unique_exact_match_handles_names_years_and_rejects_ambiguity():
    original = {"id": 1, "title": "希望", "original_title": "Hope", "year": "2020"}
    remake = {"id": 2, "title": "希望", "original_title": "Hope", "year": "2013"}
    assert unique_exact_match(" 《希望》 ", [original]) is original
    assert unique_exact_match("ＨＯＰＥ", [original]) is original
    assert unique_exact_match("希望", [original, remake]) is None
    assert unique_exact_match("希望 2020", [original, remake]) is original
    assert unique_exact_match("希望（2013）", [original, remake]) is remake
    assert unique_exact_match("希望 2020)", [original]) is None
    assert unique_exact_match("希望 2021", [original, remake]) is None
    assert unique_exact_match("希望的故事", [original]) is None
    assert unique_exact_match("", [original]) is None
    assert unique_exact_match("希望", [{**original, "search_complete": False}]) is None
    assert unique_exact_match("希望 2020", [original, {**original, "id": 3}]) is None


def test_numeric_title_is_not_misread_as_release_year():
    candidate = {"title": "银翼杀手2049", "original_title": "Blade Runner 2049", "year": "2017"}
    assert unique_exact_match("Blade Runner 2049", [candidate]) is candidate


@pytest.mark.parametrize("path", ["https://untrusted.test/a.jpg", "//untrusted.test/a.jpg", "/../a.jpg", "/a.jpg?x=1"])
def test_image_path_cannot_change_official_host_or_insert_query(path):
    assert TMDBClient._poster_url(path, ("https://image.tmdb.org/t/p/", "w500")) is None
