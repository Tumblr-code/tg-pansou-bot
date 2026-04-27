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
os.environ.setdefault("HTTP_API_TOKEN", "smoke-test-token")
os.environ.setdefault("REQUIRE_HTTP_API_TOKEN", "true")

MODULES = [
    "config",
    "pansou_client",
    "user_settings",
    "http_api",
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

print("Smoke test passed")
