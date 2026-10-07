"""Optional, bounded TMDB movie/TV metadata lookup."""

from __future__ import annotations

import asyncio
import copy
import re
import time
import unicodedata
from collections import OrderedDict
from typing import Any
from urllib.parse import urlsplit

import httpx
from structlog import get_logger

from config import settings

logger = get_logger()

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_TIMEOUT = 5.0
TMDB_CACHE_TTL = 3600.0
TMDB_CACHE_SIZE = 128
TMDB_CANDIDATE_LIMIT = 20


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    if normalized.startswith("《") and normalized.endswith("》"):
        normalized = normalized[1:-1].strip()
    return " ".join(normalized.split())


def unique_exact_match(keyword: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose only an unambiguous complete title, optionally qualified by year."""
    if any(candidate.get("search_complete") is False for candidate in candidates):
        return None
    normalized = _normalize_title(keyword)
    if not normalized:
        return None

    # Check the full title first: a title such as "Blade Runner 2049" must not
    # lose its number merely because it resembles a trailing year.
    exact = [candidate for candidate in candidates if normalized in {
        _normalize_title(str(candidate.get("title") or "")),
        _normalize_title(str(candidate.get("original_title") or "")),
    }]
    if exact:
        return exact[0] if len(exact) == 1 else None

    qualified = re.fullmatch(
        r"(.+?)(?:\s+((?:19|20)\d{2})|\s*\(((?:19|20)\d{2})\))", normalized
    )
    if qualified is None:
        return None
    title, plain_year, bracket_year = qualified.groups()
    year = plain_year or bracket_year
    title = _normalize_title(title)
    exact = [candidate for candidate in candidates if str(candidate.get("year") or "") == year
             and title in {
                 _normalize_title(str(candidate.get("title") or "")),
                 _normalize_title(str(candidate.get("original_title") or "")),
             }]
    return exact[0] if len(exact) == 1 else None


class TMDBClient:
    """Read-only metadata client. Credentials and query text never enter logs."""

    def __init__(
        self,
        token: str | None = None,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        cache_size: int = TMDB_CACHE_SIZE,
        cache_ttl: float = TMDB_CACHE_TTL,
    ) -> None:
        self._token = (settings.tmdb_read_access_token if token is None else token) or ""
        self._token = self._token.strip()
        self._api_key = (settings.tmdb_api_key if api_key is None else api_key) or ""
        self._api_key = self._api_key.strip()
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._cache_size = max(1, cache_size)
        self._cache_ttl = cache_ttl
        self._cache: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self._image_config: tuple[float, tuple[str, str]] | None = None
        self._config_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._token or self._api_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                base_url=TMDB_API_URL,
                headers=headers,
                timeout=httpx.Timeout(TMDB_TIMEOUT),
                transport=self._transport,
                proxy=(settings.https_proxy or settings.http_proxy or None)
                if self._transport is None else None,
                trust_env=False,
                follow_redirects=False,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )
        return self._client

    async def _request(self, path: str, **params: Any) -> dict[str, Any]:
        if not self._token and self._api_key:
            params["api_key"] = self._api_key
        # HTTPX phase timeouts alone do not bound a slow streaming response.
        async with asyncio.timeout(TMDB_TIMEOUT):
            response = await self._get_client().get(path, params=params)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("invalid TMDB response")
            return data

    async def _get_image_config(self) -> tuple[str, str] | None:
        async with self._config_lock:
            if self._image_config and self._image_config[0] > time.monotonic():
                return self._image_config[1]
            try:
                data = await self._request("/configuration")
                images = data.get("images") or {}
                base_url = images.get("secure_base_url")
                if not isinstance(base_url, str):
                    return None
                parsed = urlsplit(base_url)
                if (parsed.scheme != "https" or parsed.netloc != "image.tmdb.org"
                        or parsed.path != "/t/p/" or parsed.query or parsed.fragment):
                    return None
                sizes = images.get("poster_sizes") or []
                size = next((value for value in ("w500", "w342", "w780", "w185", "original")
                             if value in sizes), None)
                if size is None:
                    return None
                config = (base_url, size)
                self._image_config = (time.monotonic() + self._cache_ttl, config)
                return config
            except Exception as exc:
                logger.warning("tmdb_image_config_failed", error_type=type(exc).__name__)
                return None

    @staticmethod
    def _poster_url(path: Any, config: tuple[str, str] | None) -> str | None:
        if (config is None or not isinstance(path, str)
                or not re.fullmatch(r"/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)", path)):
            return None
        base_url, size = config
        return f"{base_url}{size}{path}"

    async def search(self, keyword: str) -> list[dict[str, Any]]:
        keyword = keyword.strip()
        if not self.enabled or not keyword:
            return []
        cache_key = _normalize_title(keyword)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            self._cache.move_to_end(cache_key)
            return copy.deepcopy(cached[1])
        self._cache.pop(cache_key, None)

        try:
            data = await self._request(
                "/search/multi", query=keyword, language="zh-CN", include_adult="false", page=1
            )
            raw_candidates = data.get("results")
            if not isinstance(raw_candidates, list):
                raise ValueError("invalid TMDB results")
            raw_candidates = [item for item in raw_candidates[:TMDB_CANDIDATE_LIMIT]
                              if isinstance(item, dict) and item.get("media_type") in {"movie", "tv"}]
            image_config = await self._get_image_config() if any(
                item.get("poster_path") for item in raw_candidates
            ) else None
            complete = data.get("total_pages") in (0, 1)
            candidates = []
            seen = set()
            for item in raw_candidates:
                media_type = item["media_type"]
                item_id = item.get("id")
                title = item.get("title" if media_type == "movie" else "name")
                if (not isinstance(item_id, int) or isinstance(item_id, bool) or item_id <= 0
                        or not isinstance(title, str) or not title.strip()
                        or (media_type, item_id) in seen):
                    continue
                seen.add((media_type, item_id))
                release_date = item.get("release_date" if media_type == "movie" else "first_air_date")
                year = release_date[:4] if isinstance(release_date, str) and re.match(
                    r"^\d{4}-\d{2}-\d{2}$", release_date
                ) else ""
                original_title = item.get("original_title" if media_type == "movie" else "original_name")
                overview = item.get("overview")
                candidates.append({
                    "id": item_id,
                    "media_type": media_type,
                    "title": title.strip(),
                    "original_title": original_title.strip() if isinstance(original_title, str) else "",
                    "year": year,
                    "overview": overview.strip() if isinstance(overview, str) else "",
                    "poster_url": self._poster_url(item.get("poster_path"), image_config),
                    "source_url": f"https://www.themoviedb.org/{media_type}/{item_id}",
                    "search_complete": complete,
                })
            self._cache[cache_key] = (time.monotonic() + self._cache_ttl, candidates)
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
            return copy.deepcopy(candidates)
        except Exception as exc:
            logger.warning("tmdb_search_failed", error_type=type(exc).__name__)
            return []

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        self._cache.clear()
        self._image_config = None


tmdb_client = TMDBClient()
