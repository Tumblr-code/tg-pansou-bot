"""Parsing and validation helpers for search/source options."""
from __future__ import annotations

import html
import shlex
from typing import Any, Optional

from pansou_client import pansou_client

MAX_LIST_MESSAGE_LENGTH = 3300
MAX_OPTION_ITEMS = 32
MAX_OPTION_ITEM_LENGTH = 64


def parse_csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def validate_keyword(keyword: str, max_length: int) -> Optional[str]:
    length = len(keyword.strip())
    if length < 2:
        return "搜索关键词至少需要2个字符"
    if length > max_length:
        return f"搜索关键词不能超过{max_length}个字符"
    return None


def _bounded_csv_values(raw: str) -> tuple[list[str], Optional[str]]:
    values = parse_csv_values(raw)
    if len(values) > MAX_OPTION_ITEMS:
        return [], f"单次最多指定{MAX_OPTION_ITEMS}项"
    if any(len(value) > MAX_OPTION_ITEM_LENGTH for value in values):
        return [], f"单项名称不能超过{MAX_OPTION_ITEM_LENGTH}个字符"
    return values, None


def format_compact_list(values: list[str], *, limit: int = MAX_LIST_MESSAGE_LENGTH) -> str:
    if not values:
        return "无"

    lines: list[str] = []
    current_length = 0
    for value in values:
        item = f"<code>{html.escape(str(value))}</code>"
        extra = len(item) + (2 if lines else 0)
        if current_length + extra > limit:
            remaining = len(values) - len(lines)
            lines.append(f"... 还有 {remaining} 个")
            break
        lines.append(item)
        current_length += extra
    return ", ".join(lines)


def get_list_arg(args: list[str], start_index: int = 1) -> str:
    return " ".join(args[start_index:]).strip()


async def get_pansou_lists(force_refresh: bool = False) -> tuple[list[str], list[str]]:
    info = await pansou_client.get_service_info(force_refresh=force_refresh)
    plugins = sorted(str(item) for item in info.get("plugins", []) if str(item).strip())
    channels = sorted(str(item) for item in info.get("channels", []) if str(item).strip())
    return plugins, channels


def validate_values(values: list[str], available: list[str]) -> tuple[list[str], list[str]]:
    if not available:
        return list(dict.fromkeys(values)), []

    available_set = set(available)
    valid = [value for value in values if value in available_set]
    invalid = [value for value in values if value not in available_set]
    return list(dict.fromkeys(valid)), list(dict.fromkeys(invalid))


def parse_search_options(raw_text: str) -> tuple[str, dict[str, Any], Optional[str]]:
    try:
        tokens = shlex.split(raw_text)
    except ValueError as exc:
        return "", {}, f"参数格式错误：{exc}"

    keyword_parts: list[str] = []
    options: dict[str, Any] = {}
    index = 0

    def next_value() -> Optional[str]:
        nonlocal index
        if index + 1 >= len(tokens):
            return None
        index += 1
        return tokens[index]

    while index < len(tokens):
        token = tokens[index]
        key = token
        value: Optional[str] = None

        if token.startswith("--") and "=" in token:
            key, value = token.split("=", 1)

        if key in ("--refresh", "-r"):
            options["force_refresh"] = True
        elif key in ("--src", "--source"):
            value = value if value is not None else next_value()
            if value not in ("all", "tg", "plugin"):
                return "", {}, "搜索来源只能是 all、tg 或 plugin"
            options["source_type"] = value
        elif key in ("--types", "--cloud-types"):
            value = value if value is not None else next_value()
            if not value:
                return "", {}, "缺少网盘类型参数"
            if value.lower() in ("all", "全部"):
                options["cloud_types"] = []
            else:
                parsed, error = _bounded_csv_values(value)
                if error:
                    return "", {}, error
                options["cloud_types"] = parsed
        elif key == "--plugins":
            value = value if value is not None else next_value()
            if not value:
                return "", {}, "缺少插件参数"
            if value.lower() in ("all", "全部"):
                options["plugins"] = []
            else:
                parsed, error = _bounded_csv_values(value)
                if error:
                    return "", {}, error
                options["plugins"] = parsed
        elif key == "--channels":
            value = value if value is not None else next_value()
            if not value:
                return "", {}, "缺少频道参数"
            if value.lower() in ("all", "全部"):
                options["channels"] = []
            else:
                parsed, error = _bounded_csv_values(value)
                if error:
                    return "", {}, error
                options["channels"] = parsed
        elif key == "--limit":
            value = value if value is not None else next_value()
            try:
                options["limit"] = int(value or "")
            except ValueError:
                return "", {}, "limit 必须是数字"
        elif token.startswith("-"):
            return "", {}, f"未知参数：{token}"
        else:
            keyword_parts.append(token)
        index += 1

    return " ".join(keyword_parts).strip(), options, None
