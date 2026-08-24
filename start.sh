#!/bin/bash
# Bot 启动脚本（前台运行，交由 systemd 或容器管理）

set -e

if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在，请从 .env.example 复制"
    cp .env.example .env
    echo "已创建 .env 文件，请编辑配置"
    exit 1
fi

if grep -q "TG_BOT_TOKEN=你的BotToken\|TG_BOT_TOKEN=$" .env; then
    echo "⚠️ 请先配置 TG_BOT_TOKEN"
    echo "编辑 .env 文件，设置你的 Bot Token"
    exit 1
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"
exec python3 main.py
