from __future__ import annotations

import html
from html.parser import HTMLParser

from message_utils import MAX_TELEGRAM_TEXT, ensure_telegram_text


class ParsedMessage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs)["href"])

    def handle_endtag(self, tag):
        assert self.tags.pop() == tag

    def handle_data(self, data):
        self.text.append(data)


def test_long_html_with_short_visible_text_keeps_every_magnet_link() -> None:
    text = "\n".join(
        f'{i}. {"标题" * 46}\n<a href="https://t.me/pansoubotvip_bot?start='
        f'magnet_-rr_1jm_2bf_0_{i}_0123456789abcdef">获取磁力</a>\n📌 来源: Synthetic catalog'
        for i in range(20)
    )
    assert len(text) > MAX_TELEGRAM_TEXT
    rendered = ensure_telegram_text(text, parse_mode="HTML")
    parsed = ParsedMessage()
    parsed.feed(rendered)

    assert rendered == text
    assert len(parsed.links) == 20
    assert not parsed.tags
    assert len("".join(parsed.text).encode("utf-16-le")) // 2 <= MAX_TELEGRAM_TEXT


def test_real_html_truncation_preserves_links_and_balanced_formatting() -> None:
    url = "https://t.me/pansoubotvip_bot?start=magnet_example"
    text = (
        f'<b>搜索结果</b>\n<a href="{url}">获取磁力</a>\n'
        f'<blockquote><i>{html.escape("字🙂&<>" * 1200)}</i></blockquote>'
    )
    rendered = ensure_telegram_text(text, parse_mode="HTML")
    parsed = ParsedMessage()
    parsed.feed(rendered)

    assert parsed.links == [url]
    assert not parsed.tags
    assert "内容过长已截断" in rendered
    assert "字🙂&<>" in "".join(parsed.text)
    assert len("".join(parsed.text).encode("utf-16-le")) // 2 <= MAX_TELEGRAM_TEXT


def test_plain_emoji_text_respects_telegram_units_without_splitting_emoji() -> None:
    rendered = ensure_telegram_text("🙂" * 3000)

    assert len(rendered.encode("utf-16-le")) // 2 <= MAX_TELEGRAM_TEXT
    assert "�" not in rendered
    assert "内容过长已截断" in rendered


def test_exact_visible_limit_does_not_truncate_html() -> None:
    text = "<code>" + "🙂" * (MAX_TELEGRAM_TEXT // 2) + "</code>"

    assert ensure_telegram_text(text, parse_mode="HTML") == text
