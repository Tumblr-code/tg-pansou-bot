"""Pure renderers and versioned keyboards for one active search view."""
from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from message_utils import _HTMLTextLimiter, _strip_html_tags, _utf16_length

PAGE_SIZE = 4
CAPTION_LIMIT = 1024
_ACTIONS = {"cat", "pick", "cand", "raw", "retry", "refresh", "all", "back", "type", "noop"}
_NOTICE = "<i>⏰ 此消息将在 3 分钟后自动删除</i>"


def clamp_page(page: int, total_items: int, page_size: int = PAGE_SIZE) -> int:
    """Return a valid one-based page, including page one for empty results."""
    total_pages = max(1, (max(0, total_items) + page_size - 1) // page_size)
    return min(max(1, page), total_pages)


def _page_range(page: int, count: int) -> tuple[int, int]:
    return clamp_page(page, count), max(1, (max(0, count) + PAGE_SIZE - 1) // PAGE_SIZE)


def sorted_type_buttons(type_buttons: list[dict]) -> list[dict]:
    """Keep equal-count types in their existing order so callback indices stay stable."""
    return sorted(type_buttons, key=lambda button: -int(button.get("count", 0)))


def build_view_callback(cache_key: str, revision: int, action: str, arg: str = "") -> str:
    """Encode stable search identity separately from its changing active message."""
    data = f"v:{cache_key}:{revision}:{action}" + (f":{arg}" if arg else "")
    if parse_view_callback(data) is None:
        raise ValueError("Invalid or oversized view callback")
    return data


def parse_view_callback(data: str) -> tuple[str, int, str, str] | None:
    if not isinstance(data, str) or len(data.encode("utf-8")) > 64:
        return None
    parts = data.split(":")
    if len(parts) not in {6, 7} or parts[0] != "v":
        return None
    _, chat_id, user_id, message_id, revision, action, *args = parts
    if not re.fullmatch(r"-?[0-9]+", chat_id):
        return None
    if any(not re.fullmatch(r"[0-9]+", value) for value in (user_id, message_id, revision)):
        return None
    if int(chat_id) == 0 or int(user_id) <= 0 or int(message_id) <= 0:
        return None
    if action not in _ACTIONS:
        return None
    arg = args[0] if args else ""
    if args and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", arg):
        return None
    return ":".join(parts[1:4]), int(revision), action, arg


def _clip_text(value: object, limit: int) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _visible_length(text: str) -> int:
    return _utf16_length(html.unescape(_strip_html_tags(text)))


def ensure_caption(text: str) -> str:
    """Fit Telegram's parsed caption limit without flattening links or breaking tags."""
    if _visible_length(text) <= CAPTION_LIMIT:
        return text
    limiter = _HTMLTextLimiter(CAPTION_LIMIT - 1)
    limiter.feed(text)
    limiter.close()
    return limiter.result() + "…"


def _fit_caption(body: str, footer: str) -> str:
    suffix = f"\n\n{footer}" if footer else ""
    limit = CAPTION_LIMIT - _visible_length(suffix)
    if _visible_length(body) > limit:
        limiter = _HTMLTextLimiter(max(0, limit - 1))
        limiter.feed(body)
        limiter.close()
        body = limiter.result() + "…"
    return body + suffix


def _movie_label(movie: dict) -> tuple[str, str, str]:
    title = _clip_text(movie.get("title") or "未命名影片", 160)
    year = _clip_text(movie.get("year") or "年份未知", 16)
    media_type = {"movie": "电影", "tv": "电视剧"}.get(movie.get("media_type"), "影视")
    return title, year, media_type


def _source_link(movie: dict) -> str:
    source_url = str(movie.get("source_url") or "")
    try:
        parsed = urlsplit(source_url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.themoviedb.org", "themoviedb.org"}:
            return ""
    except ValueError:
        return ""
    return f'资料来源：<a href="{html.escape(source_url, quote=True)}">TMDB</a>'


def render_overview(keyword: str, movie: dict | None, total: int) -> str:
    """Render a compact overview that also fits a Telegram photo caption."""
    count = max(0, int(total))
    if movie is None:
        body = (
            f"🔎 搜索结果：<b>{html.escape(_clip_text(keyword, 240))}</b>\n"
            f"📊 共找到 <b>{count}</b> 条资源"
        )
        if count:
            body += "\n\n请选择网盘类型查看资源。"
        return _fit_caption(body, _NOTICE)

    title, year, media_type = _movie_label(movie)
    synopsis = _clip_text(movie.get("overview") or "暂无简介", 240) or "暂无简介"
    body = (
        f"🎬 <b>{html.escape(title)}</b>\n"
        f"{html.escape(year)} · {media_type}\n\n"
        f"{html.escape(synopsis)}\n\n"
        f"📊 共找到 <b>{count}</b> 条资源"
    )
    source = _source_link(movie)
    footer = f"{source}\n\n{_NOTICE}" if source else _NOTICE
    return _fit_caption(body, footer)


def render_candidates(keyword: str, candidates: list[dict], page: int) -> str:
    page, total_pages = _page_range(page, len(candidates))
    start = (page - 1) * PAGE_SIZE
    lines = [f"🎬 请选择影片：<b>{html.escape(_clip_text(keyword, 120))}</b>"]
    for index, movie in enumerate(candidates[start:start + PAGE_SIZE], start):
        title, year, media_type = _movie_label(movie)
        lines.append(f"{index + 1}. {html.escape(title)} / {html.escape(year)} / {media_type}")
    if not candidates:
        lines.append("未找到匹配的电影或电视剧。")
    lines.append(f"第 {page}/{total_pages} 页")
    lines.append("软件、文档等内容可直接按关键词查资源。")
    return "\n\n".join(lines) + f"\n\n{_NOTICE}"


def _button(label: str, key: str, revision: int, action: str, arg: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=build_view_callback(key, revision, action, arg))


def _page_row(key: str, revision: int, action: str, page: int, total_pages: int,
              prefix: str = "") -> list[InlineKeyboardButton]:
    row = []
    if page > 1:
        row.append(_button("⬅️ 上一页", key, revision, action, f"{prefix}{page - 1}"))
    row.append(_button(f"{page}/{total_pages}", key, revision, "noop"))
    if page < total_pages:
        row.append(_button("下一页 ➡️", key, revision, action, f"{prefix}{page + 1}"))
    return row


def overview_keyboard(cache_key: str, revision: int, type_buttons: list[dict], page: int = 1,
                      has_candidates: bool = False, retry_title: bool = False) -> InlineKeyboardMarkup:
    ordered = sorted_type_buttons(type_buttons)
    page, total_pages = _page_range(page, len(ordered))
    start = (page - 1) * PAGE_SIZE
    choices = [
        _button(button["text"], cache_key, revision, "type", f"{index}.1")
        for index, button in enumerate(ordered[start:start + PAGE_SIZE], start)
    ]
    rows = [choices[index:index + 2] for index in range(0, len(choices), 2)]
    if ordered:
        rows.append(_page_row(cache_key, revision, "cat", page, total_pages))
    if retry_title:
        rows.append([_button("仅按片名重试", cache_key, revision, "retry")])
    actions = []
    if has_candidates:
        actions.append(_button("重选影片", cache_key, revision, "cand", "1"))
    actions.extend([
        _button("🔄 重新搜索", cache_key, revision, "refresh"),
        _button("📊 显示全部", cache_key, revision, "all"),
    ])
    rows.append(actions)
    return InlineKeyboardMarkup(rows)


def candidate_keyboard(cache_key: str, revision: int, candidates: list[dict],
                       page: int = 1) -> InlineKeyboardMarkup:
    page, total_pages = _page_range(page, len(candidates))
    start = (page - 1) * PAGE_SIZE
    rows = []
    for index, movie in enumerate(candidates[start:start + PAGE_SIZE], start):
        title, year, media_type = _movie_label(movie)
        label = f"{index + 1}. {_clip_text(title, 50)} / {year} / {media_type}"
        rows.append([_button(label, cache_key, revision, "pick", str(index))])
    if candidates:
        rows.append(_page_row(cache_key, revision, "cand", page, total_pages))
    rows.append([_button("直接按关键词查资源", cache_key, revision, "raw")])
    return InlineKeyboardMarkup(rows)


def resource_keyboard(cache_key: str, revision: int, cloud_index: int | None, page: int = 1,
                      total_pages: int = 1) -> InlineKeyboardMarkup:
    total_pages = max(1, total_pages)
    page = min(max(1, page), total_pages)
    rows = []
    if cloud_index is not None:
        rows.append(_page_row(cache_key, revision, "type", page, total_pages, f"{cloud_index}."))
    rows.append([
        _button("🔙 返回总览", cache_key, revision, "back"),
        _button("🔄 重新搜索", cache_key, revision, "refresh"),
    ])
    return InlineKeyboardMarkup(rows)
