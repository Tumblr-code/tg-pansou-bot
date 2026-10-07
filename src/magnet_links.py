"""Compact Telegram deep links that resolve complete magnet URIs from search cache."""
from __future__ import annotations

import hashlib
import re

MAGNET_START_PREFIX = "magnet_"


def is_magnet_url(value: object) -> bool:
    return isinstance(value, str) and value.lower().startswith("magnet:")


def _base36(value: int) -> str:
    if value < 0:
        return "-" + _base36(-value)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    encoded = ""
    while value:
        value, digit = divmod(value, 36)
        encoded = digits[digit] + encoded
    return encoded or "0"


def magnet_uri_digest(uri: str) -> str:
    """Bind a link to the exact URI even if a refreshed search reuses its cache key."""
    return hashlib.sha256(uri.encode("utf-8")).hexdigest()[:12]


def _build_payload(cache_key: str, type_index: int, item_index: int, digest: str) -> str:
    if not re.fullmatch(r"-?[1-9][0-9]*:[1-9][0-9]*:[1-9][0-9]*", cache_key):
        raise ValueError("Invalid search cache key")
    if type_index < 0 or item_index < 0:
        raise ValueError("Invalid result index")
    coordinates = [*map(int, cache_key.split(":")), type_index, item_index]
    payload = MAGNET_START_PREFIX + "_".join(_base36(value) for value in coordinates)
    payload += "_" + digest
    if len(payload) > 64:
        raise ValueError("Magnet start payload exceeds Telegram's limit")
    return payload


def build_magnet_start_payload(
    cache_key: str, type_index: int, item_index: int, uri: str,
) -> str:
    """Encode cache coordinates and a URI fingerprint, never the magnet itself."""
    return _build_payload(cache_key, type_index, item_index, magnet_uri_digest(uri))


def parse_magnet_start_payload(
    payload: str,
) -> tuple[str | None, int | None, int | None, str | None]:
    pattern = r"magnet_-?[0-9a-z]+(?:_[0-9a-z]+){4}_[0-9a-f]{12}"
    if len(payload) > 64 or not re.fullmatch(pattern, payload):
        return None, None, None, None
    try:
        coordinates, digest = payload[len(MAGNET_START_PREFIX):].rsplit("_", 1)
        chat_id, user_id, message_id, type_index, item_index = (
            int(value, 36) for value in coordinates.split("_")
        )
        cache_key = f"{chat_id}:{user_id}:{message_id}"
        if _build_payload(cache_key, type_index, item_index, digest) != payload:
            return None, None, None, None
        return cache_key, type_index, item_index, digest
    except ValueError:
        return None, None, None, None


def build_magnet_deep_link(
    bot_username: str, cache_key: str, type_index: int, item_index: int, uri: str,
) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot_username):
        raise ValueError("Invalid bot username")
    payload = build_magnet_start_payload(cache_key, type_index, item_index, uri)
    # All payload characters are URL-safe; no raw URI is added to this URL.
    return f"https://t.me/{bot_username}?start={payload}"


def parse_magnet_callback(data: str) -> tuple[str | None, int | None, int | None]:
    if not data.startswith("magnet:"):
        return None, None, None
    try:
        cache_key, type_text, item_text = data[7:].rsplit(":", 2)
        type_index, item_index = int(type_text), int(item_text)
        if not cache_key or type_index < 0 or item_index < 0:
            return None, None, None
        return cache_key, type_index, item_index
    except ValueError:
        return None, None, None
