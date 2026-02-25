#!/usr/bin/env python3
"""
TG Pansou Bot - 网盘搜索 Telegram Bot
"""
import asyncio
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bot import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 已停止")
        sys.exit(0)
