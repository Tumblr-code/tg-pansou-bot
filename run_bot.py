#!/usr/bin/env python3
"""Bot 启动脚本（带自动重启）"""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

print("🚀 启动 TG Pansou Bot...")
print("=" * 50)

while True:
    try:
        from bot import main
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 已停止")
        break
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        print(f"\n🔄 5秒后重启...")
        time.sleep(5)
