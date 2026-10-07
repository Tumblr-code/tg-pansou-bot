from __future__ import annotations

import html
from html.parser import HTMLParser

import pytest

from media_views import (
    build_view_callback,
    candidate_keyboard,
    clamp_page,
    ensure_caption,
    overview_keyboard,
    parse_view_callback,
    render_candidates,
    render_overview,
    resource_keyboard,
)

KEY = "-1001234567890:7814937846:2147483647"


def buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def actions(markup, action):
    return [button for button in buttons(markup) if parse_view_callback(button.callback_data)[2] == action]


def types(count):
    return [{"text": f"盘{index} ({index + 1})", "type": f"drive{index}", "count": index + 1}
            for index in range(count)]


@pytest.mark.parametrize(("count", "expected_pages"), [(0, 1), (1, 1), (4, 1), (5, 2), (9, 3)])
def test_overview_has_four_categories_per_page_with_stable_sorted_indices(count, expected_pages):
    seen = []
    for page in range(1, expected_pages + 1):
        markup = overview_keyboard(KEY, 4, types(count), page=page)
        category_buttons = actions(markup, "type")
        assert len(category_buttons) <= 4
        category_rows = [row for row in markup.inline_keyboard
                         if parse_view_callback(row[0].callback_data)[2] == "type"]
        assert len(category_rows) <= 2
        assert all(len(row) <= 2 for row in category_rows)
        seen.extend(button.text for button in category_buttons)
        assert [parse_view_callback(button.callback_data)[3] for button in category_buttons] == [
            f"{index}.1" for index in range((page - 1) * 4, min(page * 4, count))
        ]
        if count:
            assert actions(markup, "noop")[0].text == f"{page}/{expected_pages}"
    assert seen == [f"盘{index} ({index + 1})" for index in reversed(range(count))]


def test_category_pages_clamp_and_equal_counts_keep_original_order():
    entries = [{"text": title, "type": title, "count": 1} for title in "abcde"]
    assert [button.text for button in actions(overview_keyboard(KEY, 0, entries, -9), "type")] == list("abcd")
    assert [button.text for button in actions(overview_keyboard(KEY, 0, entries, 99), "type")] == ["e"]


def test_clamp_page_supports_resource_page_size_and_empty_results():
    assert clamp_page(99, 21, page_size=10) == 3
    assert clamp_page(99, 0) == 1
    assert clamp_page(-1, 9) == 1


def test_all_controls_are_versioned_and_actions_preserve_search_identity():
    markup = overview_keyboard(KEY, 17, types(5), has_candidates=True, retry_title=True)
    assert {parse_view_callback(button.callback_data)[2] for button in buttons(markup)} == {
        "type", "noop", "cat", "retry", "cand", "refresh", "all",
    }
    for button in buttons(markup):
        key, revision, _, _ = parse_view_callback(button.callback_data)
        assert (key, revision) == (KEY, 17)
        assert len(button.callback_data.encode()) <= 64
    assert not any(term in button.text for button in buttons(markup)
                   for term in ("店铺助手", "频道", "群组"))


@pytest.mark.parametrize(("action", "arg"), [("back", ""), ("type", "12.34"), ("pick", "0"), ("cand", "2")])
def test_callback_round_trip(action, arg):
    data = build_view_callback(KEY, 987654, action, arg)
    assert parse_view_callback(data) == (KEY, 987654, action, arg)


@pytest.mark.parametrize("data", [
    "v:1:2:3:1:unknown", "v:1:2:3:-1:back", "v:0:2:3:1:back", "v:1:0:3:1:back",
    "v:1:2:3:1:type:1.2.3", "v:1:2:3:1:back:", "v:1:2:3:1:back:evil", "back:1:2:3",
    "v:1:2:3:1:type:" + "9" * 64, "v:1:2:3:1:type:1:2",
])
def test_callback_rejects_malformed_or_oversized_data(data):
    assert parse_view_callback(data) is None


def test_callback_builder_rejects_unusable_data():
    with pytest.raises(ValueError):
        build_view_callback(KEY, 0, "type", "9" * 64)


def movies(count=9):
    return [{"title": f"希望{index}", "year": str(2000 + index),
             "media_type": "movie" if index % 2 == 0 else "tv"} for index in range(count)]


def test_candidates_show_four_titles_and_indices_on_second_page():
    entries = movies()
    markup = candidate_keyboard(KEY, 2, entries, 2)
    assert [parse_view_callback(button.callback_data)[3] for button in actions(markup, "pick")] == ["4", "5", "6", "7"]
    assert actions(markup, "pick")[0].text == "5. 希望4 / 2004 / 电影"
    assert actions(markup, "pick")[1].text == "6. 希望5 / 2005 / 电视剧"
    assert len(actions(markup, "raw")) == 1
    text = render_candidates("希望", entries, 2)
    assert "希望4 / 2004 / 电影" in text
    assert "希望5 / 2005 / 电视剧" in text
    assert "希望0" not in text and "希望8" not in text
    assert "第 2/3 页" in text


def test_empty_candidates_keep_keyword_search_and_valid_page():
    markup = candidate_keyboard(KEY, 0, [], 100)
    assert [parse_view_callback(button.callback_data)[2] for button in buttons(markup)] == ["raw"]
    assert "未找到匹配" in render_candidates("软件", [], 100)
    assert "第 1/1 页" in render_candidates("软件", [], 100)


def test_resource_pages_return_to_overview_and_use_category_index():
    markup = resource_keyboard(KEY, 3, 8, page=2, total_pages=3)
    assert [parse_view_callback(button.callback_data)[3] for button in actions(markup, "type")] == ["8.1", "8.3"]
    assert actions(markup, "back")[0].text == "🔙 返回总览"
    assert len(actions(resource_keyboard(KEY, 3, None), "type")) == 0
    assert actions(resource_keyboard(KEY, 3, 0, page=99, total_pages=0), "noop")[0].text == "1/1"


class ParsedHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = ""
        self.stack = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        if tag == "a":
            self.links.append(dict(attrs)["href"])

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag

    def handle_data(self, data):
        self.text += data


def test_overview_caption_preserves_source_notice_and_escaped_synopsis_under_1024_utf16():
    movie = {"title": "🎬" * 300 + "<script>", "year": "2024", "media_type": "movie",
             "overview": "😀" * 300, "source_url": "https://www.themoviedb.org/movie/1?lang=zh&x=2"}
    text = render_overview("query", movie, 161)
    parsed = ParsedHTML()
    parsed.feed(text)
    assert not parsed.stack
    assert len(parsed.text.encode("utf-16-le")) // 2 <= 1024
    assert parsed.text.count("😀") == 239
    assert "共找到 161 条资源" in parsed.text
    assert "3 分钟后自动删除" in parsed.text
    assert parsed.links == [movie["source_url"]]
    assert "&amp;" in text


def test_overview_missing_synopsis_and_html_escape():
    movie = {"title": '<恶意&标题>', "year": "2020", "media_type": "tv", "overview": "  "}
    text = render_overview("ignored", movie, 0)
    assert "&lt;恶意&amp;标题&gt;" in text
    assert "暂无简介" in text
    assert "2020 · 电视剧" in text
    assert "共找到 <b>0</b> 条资源" in text
    movie["overview"] = '<b>剧情&"文字"</b>'
    assert html.escape(movie["overview"]) in render_overview("ignored", movie, 1)


def test_compact_fallback_contains_total_without_per_drive_statistics():
    text = render_overview("希望 <&>", None, 161)
    assert "希望 &lt;&amp;&gt;" in text
    assert "共找到 <b>161</b> 条资源" in text
    assert "暂无简介" not in text
    assert "网盘类型" in text
    assert "磁力链接:" not in text
    parsed = ParsedHTML()
    parsed.feed(render_overview("😀" * 5000, None, 0))
    assert len(parsed.text.encode("utf-16-le")) // 2 <= 1024


@pytest.mark.parametrize("source", ["javascript:alert(1)", "https://evil.example/movie/1", "https://[invalid"])
def test_source_link_rejects_non_tmdb_urls(source):
    assert "<a " not in render_overview("x", {"title": "x", "source_url": source}, 0)


def test_caption_limiter_preserves_anchor_on_long_visible_text():
    source = "https://www.themoviedb.org/movie/1"
    text = f'<b>错误提示</b>\n<a href="{source}">{"😀" * 700}</a>'
    result = ensure_caption(text)
    parsed = ParsedHTML()
    parsed.feed(result)
    assert not parsed.stack
    assert parsed.links == [source]
    assert len(parsed.text.encode("utf-16-le")) // 2 <= 1024
    assert parsed.text.endswith("…")
    short = '<a href="' + source + '">TMDB</a>'
    assert ensure_caption(short) == short
