#!/usr/bin/env python3
"""
TG Pansou Bot - 网盘搜索 Telegram Bot
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bot import run

if __name__ == "__main__":
    run()
