#!/usr/bin/env python3
"""
TG Pansou Bot HTTP API 入口
"""
import sys
from pathlib import Path

from aiohttp import web

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import settings
from http_api import create_app


if __name__ == "__main__":
    if settings.require_http_api_token and not settings.http_api_token:
        raise SystemExit(
            "HTTP API 已启用安全模式：请先配置 HTTP_API_TOKEN，"
            "或显式设置 REQUIRE_HTTP_API_TOKEN=false 后再启动。"
        )

    web.run_app(
        create_app(),
        host=settings.http_api_host,
        port=settings.http_api_port,
    )
