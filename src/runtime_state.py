"""Runtime state for search cache, rate limits, and auto-delete scheduling."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from contextlib import suppress
from typing import Any

from telegram import Message
from telegram.ext import Application

from config import settings


class LRUCache:
    """TTL-based LRU cache used for per-message search results."""

    def __init__(self, max_size: int = 100, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._timestamps: dict[str, float] = {}

    def get(self, key: str):
        if key not in self._cache:
            return None
        if time.monotonic() - self._timestamps.get(key, 0) > self.ttl:
            self._remove(key)
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value):
        if key in self._cache:
            self._remove(key)
        elif len(self._cache) >= self.max_size:
            oldest_key, _ = self._cache.popitem(last=False)
            self._timestamps.pop(oldest_key, None)
        self._cache[key] = value
        self._timestamps[key] = time.monotonic()

    def _remove(self, key: str):
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def clear_expired(self):
        now = time.monotonic()
        expired = [key for key, ts in self._timestamps.items() if now - ts > self.ttl]
        for key in expired:
            self._remove(key)

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        self._timestamps.clear()
        return count


class SearchRateLimiter:
    """Sliding-window rate limiter keyed by Telegram user id."""

    def __init__(self, limit: int, window_seconds: int = 60, max_users: int = 2048):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_users = max_users
        self._records: OrderedDict[int, deque[float]] = OrderedDict()

    def check(self, user_id: int) -> tuple[bool, int]:
        now = time.monotonic()
        records = self._records.get(user_id)
        if records is None:
            records = deque()
            self._records[user_id] = records
        else:
            self._records.move_to_end(user_id)

        cutoff = now - self.window_seconds
        while records and records[0] <= cutoff:
            records.popleft()

        if len(records) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (now - records[0])) + 1)
            return False, retry_after

        records.append(now)
        while len(self._records) > self.max_users:
            self._records.popitem(last=False)
        return True, 0

    def clear(self) -> int:
        count = len(self._records)
        self._records.clear()
        return count


search_cache = LRUCache(max_size=50, ttl=300)
search_rate_limiter = SearchRateLimiter(limit=settings.rate_limit_per_minute)

AUTO_DELETE_DELAY = 180
_bot_application: Application | None = None
_deletion_tasks: dict[tuple[int, int], float] = {}
_cleanup_task: asyncio.Task | None = None


def set_bot_application(application: Application | None) -> None:
    global _bot_application
    _bot_application = application


async def _cleanup_worker():
    global _cleanup_task
    try:
        while _deletion_tasks:
            await asyncio.sleep(5)
            now = asyncio.get_running_loop().time()
            to_delete = [
                (chat_id, msg_id)
                for (chat_id, msg_id), delete_time in _deletion_tasks.items()
                if now >= delete_time
            ]

            for chat_id, message_id in to_delete:
                try:
                    if _bot_application:
                        await _bot_application.bot.delete_message(
                            chat_id=chat_id,
                            message_id=message_id,
                        )
                except Exception:
                    pass
                finally:
                    _deletion_tasks.pop((chat_id, message_id), None)
    finally:
        _cleanup_task = None


def _ensure_cleanup_worker():
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_worker())


def auto_delete_message(message: Message, delay: int = AUTO_DELETE_DELAY):
    schedule_message_deletion(message.chat_id, message.message_id, delay=delay)


def schedule_message_deletion(chat_id: int, message_id: int, delay: int = AUTO_DELETE_DELAY):
    _deletion_tasks[(chat_id, message_id)] = asyncio.get_running_loop().time() + delay
    _ensure_cleanup_worker()


async def shutdown_runtime_state() -> None:
    """Cancel background work and release Telegram application references."""
    global _bot_application, _cleanup_task
    task = _cleanup_task
    _cleanup_task = None
    if task and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    _deletion_tasks.clear()
    _bot_application = None


def check_search_rate_limit(user_id: int) -> tuple[bool, int]:
    return search_rate_limiter.check(user_id)


def build_search_cache_key(chat_id: int, user_id: int, message_id: int) -> str:
    return f"{chat_id}:{user_id}:{message_id}"
