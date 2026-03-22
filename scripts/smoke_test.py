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
    "wecom_service",
    "bot",
]

for module_name in MODULES:
    importlib.import_module(module_name)
    print(f"import ok: {module_name}")

print("Smoke test passed")
