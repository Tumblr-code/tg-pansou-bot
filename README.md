# TG Pansou Bot 🤖

[![Version](https://img.shields.io/badge/Version-1.0.0-blue.svg)](https://github.com/Tumblr-code/tg-pansou-bot/releases)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-supported-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个基于 [pansou](https://github.com/fish2018/pansou) API 的 Telegram Bot，支持搜索各种网盘资源。

## ✨ 功能特性

- 🔍 **智能搜索**: 支持关键词搜索网盘资源
- 💬 **私聊支持**: 私聊直接发送关键词即可搜索
- 👥 **群组支持**: 群组中使用 `/search` 命令搜索
- 📁 **多网盘**: 支持百度、阿里、夸克、天翼、UC、115、PikPak 等
- 🔄 **快捷操作**: 支持刷新结果、筛选网盘类型
- ⚡ **快速响应**: 异步处理，快速返回结果
- 🐳 **Docker 部署**: 一键 Docker 部署，简单方便

## 📋 支持的网盘

| 网盘 | 类型标识 |
|------|----------|
| 百度网盘 | baidu |
| 阿里云盘 | aliyun |
| 夸克网盘 | quark |
| 天翼云盘 | tianyi |
| UC网盘 | uc |
| 移动云盘 | mobile |
| 115网盘 | 115 |
| PikPak | pikpak |
| 迅雷网盘 | xunlei |
| 123网盘 | 123 |
| 磁力链接 | magnet |
| 电驴链接 | ed2k |

## 🚀 快速开始

### 方法一：Docker 部署（推荐）

#### 1. 克隆项目

```bash
git clone https://github.com/Tumblr-code/tg-pansou-bot.git
cd tg-pansou-bot
```

#### 2. 配置环境变量

```bash
cp .env.example .env
nano .env
```

编辑 `.env` 文件：

```env
# Telegram Bot Token（从 @BotFather 获取）
TG_BOT_TOKEN=your_bot_token_here

# Pansou API 地址
PANSOU_API_URL=http://localhost:8888

# Pansou API 认证 Token（可选）
PANSOU_API_TOKEN=

# 搜索配置
DEFAULT_RESULT_LIMIT=10
MAX_RESULT_LIMIT=20
SEARCH_TIMEOUT=30
```

#### 3. 启动服务

```bash
docker-compose up -d
```

### 方法二：本地部署

#### 1. 克隆项目

```bash
git clone https://github.com/Tumblr-code/tg-pansou-bot.git
cd tg-pansou-bot
```

#### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 配置环境变量

```bash
cp .env.example .env
nano .env
```

#### 5. 运行 Bot

```bash
python main.py
```

## 🔧 配置说明

### 获取 Telegram Bot Token

1. 在 Telegram 中搜索 @BotFather
2. 发送 `/newbot` 创建新 Bot
3. 按提示设置 Bot 名称和用户名
4. 复制获得的 Token 到 `.env` 文件

### Pansou API 部署

本 Bot 依赖 pansou 服务，需要先部署 pansou：

```bash
docker run -d -p 8888:8888 --name pansou ghcr.io/fish2018/pansou:latest
```

或者使用 docker-compose：

```yaml
version: '3.8'
services:
  pansou:
    image: ghcr.io/fish2018/pansou:latest
    container_name: pansou
    ports:
      - "8888:8888"
    restart: unless-stopped
```

### 网络配置

如果使用 Docker Compose 同时部署 pansou 和 bot：

```yaml
version: '3.8'
services:
  pansou:
    image: ghcr.io/fish2018/pansou:latest
    container_name: pansou
    ports:
      - "8888:8888"
    restart: unless-stopped
    
  tg-pansou-bot:
    build: .
    container_name: tg-pansou-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - PANSOU_API_URL=http://pansou:8888
    depends_on:
      - pansou
```

## 📖 使用教程

### 私聊使用

1. 在 Telegram 中搜索你的 Bot 用户名
2. 点击 "Start" 或发送 `/start`
3. 直接发送要搜索的关键词，如：`复仇者联盟`
4. Bot 会返回搜索结果，点击链接即可查看

### 群组使用

1. 将 Bot 添加到群组
2. 授予 Bot 发送消息的权限
3. 使用 `/search 关键词` 命令搜索，如：`/search 复仇者联盟`

### 可用命令

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用 |
| `/help` | 显示帮助信息 |
| `/search <关键词>` | 搜索资源（群组中必须使用） |

## 🐳 Docker 管理

### 查看日志

```bash
docker logs -f tg-pansou-bot
```

### 重启服务

```bash
docker-compose restart
```

### 停止服务

```bash
docker-compose down
```

### 更新镜像

```bash
docker-compose pull
docker-compose up -d
```

## 🔍 故障排查

### Bot 无响应

1. 检查日志：`docker logs tg-pansou-bot`
2. 确认 Token 正确
3. 检查网络连接
4. 确认 pansou 服务正常运行

### 搜索结果为空

1. 检查 pansou API 是否可访问
2. 确认搜索关键词有效
3. 查看 pansou 服务日志

### 网络超时

1. 检查服务器网络连接
2. 确认没有防火墙阻挡
3. 尝试重启服务

## 📁 项目结构

```
tg-pansou-bot/
├── main.py              # 主程序入口
├── run_bot.py           # Bot 运行脚本
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 构建文件
├── docker-compose.yml   # Docker Compose 配置
├── .env.example         # 环境变量示例
├── .gitignore           # Git 忽略文件
├── start.sh             # 启动脚本
├── README.md            # 项目说明
├── data/                # 数据目录
└── src/                 # 源代码目录
    └── bot/
        ├── __init__.py
        ├── handlers.py    # 消息处理器
        └── utils.py       # 工具函数
```

## 🛠️ 技术栈

- **Python 3.11**: 主要编程语言
- **python-telegram-bot**: Telegram Bot 框架
- **httpx**: 异步 HTTP 客户端
- **pydantic**: 数据验证
- **Docker**: 容器化部署

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目基于 MIT 许可证开源。

## 🙏 致谢

- [pansou](https://github.com/fish2018/pansou) - 网盘搜索 API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot 框架

---

**维护者**: [Tumblr-code](https://github.com/Tumblr-code)
