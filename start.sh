#!/bin/bash
# 仅启动 Bot（假设 pansou 已单独部署）

set -e

# 检查 .env
if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在，请从 .env.example 复制"
    cp .env.example .env
    echo "已创建 .env 文件，请编辑配置"
    exit 1
fi

# 检查 Token
if grep -q "TG_BOT_TOKEN=你的BotToken\|TG_BOT_TOKEN=$" .env; then
    echo "⚠️ 请先配置 TG_BOT_TOKEN"
    echo "编辑 .env 文件，设置你的 Bot Token"
    exit 1
fi

echo "🚀 启动 Telegram Bot..."

if [ -f "docker-compose.yml" ]; then
    if docker compose version &>/dev/null; then
        docker compose up -d
    else
        docker-compose up -d
    fi
else
    # 直接运行
    pip install -q -r requirements.txt 2>/dev/null || pip3 install -q -r requirements.txt
    python3 main.py
fi

echo "✅ Bot 已启动"
echo "查看日志: docker logs -f tg-pansou-bot"
