# TG Pansou Bot 部署教程

本文档详细介绍如何部署 TG Pansou Bot。

## 📋 部署要求

- Linux 服务器（推荐 Ubuntu 22.04+）
- Docker & Docker Compose
- 或 Python 3.11+
- 能访问 Telegram API 的网络

---

## 🐳 Docker 部署（推荐）

### 步骤 1：安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 安装 Docker Compose
apt-get install docker-compose-plugin

# 启动 Docker
systemctl enable docker
systemctl start docker
```

### 步骤 2：克隆项目

```bash
cd /root
git clone https://github.com/Tumblr-code/tg-pansou-bot.git
cd tg-pansou-bot
```

### 步骤 3：创建 Bot 并获取 Token

1. 打开 Telegram，搜索 @BotFather
2. 发送 `/newbot`
3. 输入 Bot 名称（如：网盘搜索助手）
4. 输入 Bot 用户名（必须以 bot 结尾，如：pansou_search_bot）
5. 复制获得的 Token（格式示例：`123456789:<telegram_bot_token>`）

### 步骤 4：配置环境变量

```bash
cp .env.example .env
nano .env
```

填入你的配置：

```env
TG_BOT_TOKEN=123456789:<telegram_bot_token>
PANSOU_API_URL=http://localhost:8888
DEFAULT_RESULT_LIMIT=10
MAX_RESULT_LIMIT=20
SEARCH_TIMEOUT=30
```

### 步骤 5：部署 pansou 服务

```bash
docker run -d \
  --name pansou \
  -p 8888:8888 \
  --restart unless-stopped \
  ghcr.io/fish2018/pansou:latest
```

### 步骤 6：启动 Bot

```bash
docker-compose up -d
```

### 步骤 7：验证部署

```bash
# 查看容器状态
docker ps

# 查看 Bot 日志
docker logs -f tg-pansou-bot
```

---

## 📦 本地部署

### 步骤 1：安装 Python 3.11

```bash
# Ubuntu/Debian
apt-get update
apt-get install python3.11 python3.11-venv python3-pip

# 或使用 pyenv
pyenv install 3.11.0
pyenv global 3.11.0
```

### 步骤 2：克隆项目

```bash
cd /root
git clone https://github.com/Tumblr-code/tg-pansou-bot.git
cd tg-pansou-bot
```

### 步骤 3：创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 步骤 4：安装依赖

```bash
pip install -r requirements.txt
```

### 步骤 5：配置环境变量

```bash
cp .env.example .env
nano .env
```

### 步骤 6：部署 pansou 服务

```bash
docker run -d \
  --name pansou \
  -p 8888:8888 \
  --restart unless-stopped \
  ghcr.io/fish2018/pansou:latest
```

### 步骤 7：运行 Bot

```bash
python main.py
```

---

## 🔧 高级配置

### 使用 Docker Compose 同时部署

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  pansou:
    image: ghcr.io/fish2018/pansou:latest
    container_name: pansou
    ports:
      - "8888:8888"
    restart: unless-stopped
    volumes:
      - ./pansou-cache:/app/cache
    environment:
      - CACHE_ENABLED=true
      - CACHE_MAX_SIZE=100MB
      
  tg-pansou-bot:
    build: .
    container_name: tg-pansou-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - PANSOU_API_URL=http://pansou:8888
      - PYTHONUNBUFFERED=1
    depends_on:
      - pansou
    network_mode: host  # 或使用自定义网络
```

启动：

```bash
docker-compose up -d
```

### 配置系统服务（systemd）

#### 方式一：Docker 部署（推荐）

创建服务文件：

```bash
cat > /etc/systemd/system/tg-pansou-bot.service << 'EOF'
[Unit]
Description=TG Pansou Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/tg-pansou-bot
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
```

启用服务：

```bash
systemctl enable tg-pansou-bot
systemctl start tg-pansou-bot
```

#### 方式二：Python 本地运行

如果需要使用 Python 直接运行（不使用 Docker），配置如下：

**1. 创建 Pansou Docker 服务**

```bash
cat > /etc/systemd/system/pansou-docker.service << 'EOF'
[Unit]
Description=Pansou Docker Container
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/docker start pansou
ExecStop=/usr/bin/docker stop pansou
Restart=no

[Install]
WantedBy=multi-user.target
EOF
```

**2. 创建 Bot 服务**

```bash
cat > /etc/systemd/system/tg-pansou-bot.service << 'EOF'
[Unit]
Description=TG Pansou Bot
After=network.target docker.service pansou-docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/root/tg-pansou-bot
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
ExecStart=/bin/bash -c 'source venv/bin/activate && python3 main.py'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

**3. 启用并启动服务**

```bash
systemctl daemon-reload
systemctl enable pansou-docker tg-pansou-bot
systemctl start pansou-docker tg-pansou-bot
```

**4. 查看状态**

```bash
systemctl status tg-pansou-bot pansou-docker
```

---

## 🔄 更新维护

### 更新 Bot

```bash
cd /root/tg-pansou-bot
git pull
docker-compose down
docker-compose up -d --build
```

### 查看日志

```bash
# 实时日志
docker logs -f tg-pansou-bot

# 最近 100 行
docker logs --tail 100 tg-pansou-bot
```

### 备份数据

```bash
# 备份配置
cp .env .env.backup

# 备份数据
tar -czvf tg-pansou-bot-backup-$(date +%Y%m%d).tar.gz \
  .env data/ docker-compose.yml
```

---

## ❓ 常见问题

### Q: Bot 启动后立即退出？

A: 检查日志，通常是 Token 配置错误或网络问题：

```bash
docker logs tg-pansou-bot
```

### Q: 搜索无结果？

A: 检查 pansou 服务是否正常：

```bash
curl http://localhost:8888/api/search \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"keyword":"test","limit":1}'
```

### Q: 群组中使用无效？

A: 确保：
1. Bot 已被添加到群组
2. Bot 有发送消息的权限
3. 使用 `/search 关键词` 命令

### Q: 网络超时？

A: 检查服务器网络连接，确保能访问：
- api.telegram.org
- localhost:8888 (pansou)

---

## 📞 获取帮助

- GitHub Issues: https://github.com/Tumblr-code/tg-pansou-bot/issues
- Telegram: @China_Nb_One
