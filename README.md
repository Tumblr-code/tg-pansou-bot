# TG Pansou Bot 🤖

[![Version](https://img.shields.io/badge/Version-2.0.0-blue.svg)](https://github.com/Tumblr-code/tg-pansou-bot/releases)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)
[![PM2](https://img.shields.io/badge/PM2-managed-blue.svg)](https://pm2.keymetrics.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

基于 [pansou](https://github.com/fish2018/pansou) API 的 Telegram 网盘资源搜索 Bot。

## ✨ 功能特性

- 🔍 **智能搜索** - 支持关键词搜索网盘资源
- 💬 **私聊/群组** - 私聊直接发关键词，群组用命令搜索
- 📁 **多网盘支持** - 百度、阿里、夸克、天翼、UC、115、PikPak、磁力等
- 🔄 **分类查看** - 搜索结果按网盘类型分类显示
- ⚡ **快速响应** - 异步处理，优化超时配置
- 🎯 **PM2 管理** - 使用 PM2 管理进程，稳定运行

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

### 环境要求

- Python 3.11+
- PM2 (推荐)
- pansou API 服务

### 1. 克隆项目

```bash
git clone https://github.com/Tumblr-code/tg-pansou-bot.git
cd tg-pansou-bot
```

### 2. 配置环境变量

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

# 管理员ID（可选，逗号分隔）
ADMIN_IDS=your_admin_id
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动 Bot（推荐使用 PM2）

```bash
# 使用 PM2 启动
pm2 start main.py --name tg-pansou-bot

# 保存 PM2 进程列表，开机自动启动
pm2 save

# 查看日志
pm2 logs tg-pansou-bot
```

或使用启动脚本：

```bash
./start.sh
```

## 📖 使用方法

### 私聊使用

1. 在 Telegram 搜索你的 Bot
2. 发送 `/start` 开始
3. 直接发送搜索关键词，如：`复仇者联盟`
4. 点击网盘类型按钮查看详细结果

### 群组使用

1. 将 Bot 添加到群组
2. 使用 `/search 关键词` 搜索

### 可用命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `/start` | 开始使用 | 所有人 |
| `/help` | 帮助信息 | 所有人 |
| `/search <关键词>` | 搜索资源 | 所有人 |
| `/status` | 服务状态 | 管理员 |
| `/settings` | 管理设置 | 管理员 |
| `/filter` | 搜索过滤 | 管理员 |

## ⚙️ PM2 管理命令

```bash
# 查看状态
pm2 list

# 查看日志
pm2 logs tg-pansou-bot

# 重启
pm2 restart tg-pansou-bot

# 停止
pm2 stop tg-pansou-bot

# 删除
pm2 delete tg-pansou-bot
```

## 🔧 部署 Pansou API

```bash
# 使用 Docker 部署 pansou
docker run -d -p 8888:8888 --name pansou ghcr.io/fish2018/pansou:latest
```

## �️ 技术栈

- **Python 3.11+** - 编程语言
- **python-telegram-bot 22.x** - Telegram Bot 框架
- **httpx** - 异步 HTTP 客户端
- **pydantic** - 数据验证
- **PM2** - 进程管理
- **Docker** - 容器化部署（可选）

## 📁 项目结构

```
tg-pansou-bot/
├── main.py              # 程序入口
├── start.sh             # 启动脚本
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 构建文件
├── docker-compose.yml   # Docker Compose 配置
├── .env.example         # 环境变量示例
├── .gitignore           # Git 忽略文件
├── README.md            # 项目说明
├── CHANGELOG.md         # 更新日志
├── DEPLOY.md            # 部署文档
├── data/                # 数据目录
└── src/                 # 源代码
    ├── bot.py           # Bot 主逻辑
    ├── config.py        # 配置管理
    ├── pansou_client.py # Pansou API 客户端
    ├── user_settings.py # 用户设置
    └── bot_config.py    # Bot 优化配置
```

## � 故障排查

### Bot 无响应

```bash
# 查看日志
pm2 logs tg-pansou-bot

# 检查状态
pm2 list

# 重启
pm2 restart tg-pansou-bot
```

### 检查项

1. 确认 `.env` 中 Token 正确
2. 确认 pansou 服务运行正常：`curl http://localhost:8888/api/health`
3. 检查网络连接

## 📄 许可证

MIT License

## 🙏 致谢

- [pansou](https://github.com/fish2018/pansou) - 网盘搜索 API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot 框架

---

**维护者**: [Tumblr-code](https://github.com/Tumblr-code)
