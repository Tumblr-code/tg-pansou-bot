# TG Pansou Bot - 网盘搜索 Telegram Bot

一个基于 [pansou](https://github.com/fish2018/pansou) API 的 Telegram Bot，支持搜索各种网盘资源。

## 功能特性

- 🔍 **智能搜索**: 支持关键词搜索网盘资源
- 💬 **私聊支持**: 私聊直接发送关键词即可搜索
- 👥 **群组支持**: 群组中使用 `/search` 命令搜索
- 📁 **多网盘**: 支持百度、阿里、夸克、天翼、UC、115、PikPak 等
- 🔄 **快捷操作**: 支持刷新结果、筛选网盘类型
- ⚡ **快速响应**: 异步处理，快速返回结果

## 支持的网盘

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

## 快速开始

### 1. 获取 Telegram Bot Token

1. 在 Telegram 中找到 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot` 创建新 Bot
3. 按照提示设置 Bot 名称和用户名
4. 获取 Bot Token（格式：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）

### 2. 部署 Pansou API 服务

确保你有可用的 pansou API 服务：

```bash
# 使用 Docker 部署 pansou
docker run -d --name pansou -p 8888:8888 ghcr.io/fish2018/pansou:latest
```

### 3. 部署 Bot

#### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone <your-repo>
cd tg-pansou-bot

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 Bot Token 和 pansou API 地址

# 3. 启动服务
docker-compose up -d
```

#### 方式二：直接运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 3. 运行
python main.py
```

## 配置说明

编辑 `.env` 文件：

```env
# 必需配置
TG_BOT_TOKEN=your_bot_token_here
PANSOU_API_URL=http://localhost:8888

# 可选配置
PANSOU_API_TOKEN=          # 如果 pansou 启用了认证
HTTP_PROXY=                # HTTP 代理地址
HTTPS_PROXY=               # HTTPS 代理地址
DEFAULT_RESULT_LIMIT=10    # 默认返回结果数
MAX_RESULT_LIMIT=20        # 最大返回结果数
LOG_LEVEL=INFO             # 日志级别
```

## 使用方式

### 私聊使用

1. 在 Telegram 中搜索你的 Bot 用户名
2. 直接发送搜索关键词，如：`复仇者联盟`
3. Bot 会返回搜索结果

### 群组使用

1. 将 Bot 添加到群组
2. 使用命令搜索：
   - `/search 关键词`
   - `/search@YourBotName 关键词`

### 可用命令

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用，显示欢迎信息 |
| `/help` | 显示帮助信息 |
| `/search <关键词>` | 搜索网盘资源 |
| `/status` | 检查服务状态 |

## 示例

```
/search 复仇者联盟
/search 三体 有声书
/search Python教程
```

## 项目结构

```
tg-pansou-bot/
├── main.py              # 入口文件
├── requirements.txt     # Python 依赖
├── Dockerfile          # Docker 构建文件
├── docker-compose.yml  # Docker Compose 配置
├── .env.example        # 环境变量示例
├── README.md           # 说明文档
└── src/
    ├── bot.py          # Bot 主逻辑
    ├── pansou_client.py # Pansou API 客户端
    └── config.py       # 配置管理
```

## 注意事项

1. **资源合法性**: 搜索结果来自公开渠道，请自行判断资源的合法性和安全性
2. **提取码**: 部分链接可能需要提取码，结果中会显示
3. **时效性**: 网盘链接可能有时效性，过期链接无法访问
4. **速率限制**: 默认每分钟限制 10 次请求，可在配置中调整

## 常见问题

### Q: 搜索无结果？
A: 尝试更换关键词，或使用更简单的词语搜索

### Q: Bot 无响应？
A: 使用 `/status` 命令检查服务状态，确认 pansou API 是否正常

### Q: 如何设置代理？
A: 在 `.env` 文件中设置 `HTTP_PROXY` 和 `HTTPS_PROXY`

## 更新日志

### v1.0.0
- ✅ 基础搜索功能
- ✅ 私聊和群组支持
- ✅ 多网盘类型识别
- ✅ Docker 部署

## License

MIT License

## 致谢

- [pansou](https://github.com/fish2018/pansou) - 网盘搜索 API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot 库
