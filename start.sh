#!/bin/bash
# Bot 启动脚本 - 使用 PM2 管理

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

echo "🚀 启动 Telegram Bot (使用 PM2)..."

cd /root/tg-pansou-bot

if command -v pm2 &> /dev/null; then
    pm2 start main.py --name tg-pansou-bot
    pm2 save
    echo "✅ Bot 已启动 (PM2)"
    echo "查看日志: pm2 logs tg-pansou-bot"
else
    echo "⚠️ PM2 未安装，将直接运行..."
    python3 main.py
fi
