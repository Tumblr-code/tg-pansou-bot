#!/usr/bin/env python3
"""最小 smoke test：验证核心模块可被导入。

不要求真实 TG token，不启动 bot。
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# 仅提供最小必需环境变量，避免 Settings 初始化失败
os.environ.setdefault("TG_BOT_TOKEN", "SMOKE_TEST_TOKEN_PLACEHOLDER")
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

MODULES = [
    "config",
    "runtime_state",
    "message_utils",
    "search_options",
    "keyboards",
    "application_factory",
    "search_flow",
    "pansou_client",
    "user_settings",
    "bot",
]

for module_name in MODULES:
    importlib.import_module(module_name)
    print(f"import ok: {module_name}")

from pansou_client import pansou_client

sample = {
    "code": 0,
    "data": {
        "total": 3,
        "merged_by_type": {
            "ali": [{"link": "https://www.alipan.com/s/demo", "title": "ali item"}],
            "123pan": [{"url": "https://www.123pan.com/s/demo", "name": "123 item"}],
        },
    },
}

normalized = pansou_client._normalize_search_result(sample)
assert "aliyun" in normalized["merged_by_type"]
assert "123" in normalized["merged_by_type"]
assert normalized["merged_by_type"]["aliyun"][0]["url"] == "https://www.alipan.com/s/demo"

nested = {
    "results": [
        {
            "title": "nested title",
            "channel": "demo",
            "links": [
                {"type": "lanzouyun", "url": "https://example.com/file"},
            ],
        }
    ]
}
normalized_nested = pansou_client._normalize_search_result(nested)
assert normalized_nested["merged_by_type"]["lanzou"][0]["note"] == "nested title"
assert 'href="https://example.com/file"' in pansou_client.format_type_results(
    normalized_nested,
    "demo",
    "lanzou",
)
assert "蓝奏云: 1" in pansou_client.format_overview(normalized_nested, "demo")

from message_utils import ensure_telegram_text
from search_flow import _format_search_scope

long_html = "<b>" + ("x" * 5000) + "</b>"
safe_html = ensure_telegram_text(long_html, parse_mode="HTML")
assert len(safe_html) < 4096
assert "<b>" not in safe_html
scope = _format_search_scope(
    source_type="plugin",
    cloud_types=["quark", "aliyun"],
    plugins=["panta", "wanou", "quark4k", "susu"],
    channels=None,
    limit=5,
    force_refresh=True,
)
assert "仅插件" in scope
assert "等4个" in scope
assert "已刷新" in scope

print("Smoke test passed")
