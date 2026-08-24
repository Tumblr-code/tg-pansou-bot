from __future__ import annotations

from search_options import MAX_OPTION_ITEMS, parse_search_options, validate_keyword


def test_keyword_boundaries() -> None:
    assert validate_keyword("a", 128) == "搜索关键词至少需要2个字符"
    assert validate_keyword("ab", 128) is None
    assert validate_keyword("x" * 128, 128) is None
    assert validate_keyword("x" * 129, 128) == "搜索关键词不能超过128个字符"


def test_search_options_parse_supported_values() -> None:
    keyword, options, error = parse_search_options(
        '三体 --src plugin --types quark,aliyun --limit 5 --refresh'
    )

    assert error is None
    assert keyword == "三体"
    assert options == {
        "source_type": "plugin",
        "cloud_types": ["quark", "aliyun"],
        "limit": 5,
        "force_refresh": True,
    }


def test_search_options_reject_oversized_lists() -> None:
    items = ",".join(f"plugin{index}" for index in range(MAX_OPTION_ITEMS + 1))
    _, _, error = parse_search_options(f"三体 --plugins {items}")

    assert error == f"单次最多指定{MAX_OPTION_ITEMS}项"
