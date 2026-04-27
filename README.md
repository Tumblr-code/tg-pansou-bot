# TG Pansou Bot 🤖

[![Version](https://img.shields.io/badge/Version-2.4.0-blue.svg)](https://github.com/Tumblr-code/tg-pansou-bot/releases)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/)
[![PM2](https://img.shields.io/badge/PM2-managed-blue.svg)](https://pm2.keymetrics.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

基于 [pansou](https://github.com/fish2018/pansou) API 的 Telegram 网盘资源搜索 Bot。

## ✨ 功能特性

- 🔍 **智能搜索** - 支持关键词搜索网盘资源
- 💬 **私聊/群组** - 私聊直接发关键词，群组用命令搜索
- 📁 **多网盘支持** - 百度、阿里、夸克、光鸭、天翼、UC、115、PikPak、微云、蓝奏、坚果云、磁力等
- 🔄 **分类查看** - 搜索结果按网盘类型分类显示
- 🧭 **来源控制** - 支持按 Pansou 插件、Telegram 频道和网盘类型精确筛选
- ⚡ **快速响应** - 异步处理，优化超时配置
- 🚦 **稳定保护** - 热门查询缓存、并发合并、频率限制
- ♻️ **运维命令** - 支持运行时刷新与在线更新
- 🌐 **HTTP API** - 可通过本地 API 复用搜索能力，便于接 webhook、站点页面或其他机器人
- 🎯 **PM2 管理** - 使用 PM2 管理进程，稳定运行

## 📋 支持的网盘

| 网盘 | 类型标识 |
|------|----------|
| 百度网盘 | baidu |
| 阿里云盘 | aliyun |
| 夸克网盘 | quark |
| 光鸭云盘 | guangya |
| 天翼云盘 | tianyi |
| UC网盘 | uc |
| 移动云盘 | mobile |
| 115网盘 | 115 |
| PikPak | pikpak |
| 迅雷网盘 | xunlei |
| 123网盘 | 123 |
| 腾讯微云 | weiyun |
| 蓝奏云 | lanzou |
| 坚果云 | jianguoyun |
| 磁力链接 | magnet |
| 电驴链接 | ed2k |
| 其他 | others |

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

# 管理员ID（建议配置，逗号分隔）
ADMIN_IDS=your_admin_id

# HTTP API（可选）
HTTP_API_HOST=127.0.0.1
HTTP_API_PORT=8090
HTTP_API_TOKEN=replace_with_random_secret
REQUIRE_HTTP_API_TOKEN=true
```

`ADMIN_IDS` 必须填写你自己的 Telegram 数字 ID，否则所有管理员命令都不会生效，包括：

- `/status`
- `/settings`
- `/filter`
- `/types`
- `/sources`
- `/plugins`
- `/channels`
- `/refresh`
- `/reset`
- `/update`

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

### 5. 启动 HTTP API（可选）

如果你需要给 Webhook、站点页面或其他机器人复用搜索能力，可以单独启动 HTTP API：

```bash
python api_main.py
```

推荐只监听 `127.0.0.1`，再由 Nginx、Cloudflare Tunnel 或其他网关转发。

默认情况下，`api_main.py` 启动时必须存在 `HTTP_API_TOKEN`；只有在你显式设置 `REQUIRE_HTTP_API_TOKEN=false` 时，才会允许无令牌访问（不推荐）。

## 📖 使用方法

### 私聊使用

1. 在 Telegram 搜索你的 Bot
2. 发送 `/start` 开始
3. 直接发送搜索关键词，如：`复仇者联盟`
4. 点击网盘类型按钮查看详细结果

### 群组使用

1. 将 Bot 添加到群组
2. 使用 `/search 关键词` 或 `/s 关键词` 搜索

### 高级搜索

`/search` 支持在一次查询里临时指定来源、网盘类型、插件、频道、结果数量和刷新缓存：

```text
/search 三体 --src all --types quark,aliyun --plugins panta,wanou --channels tgsearchers4 --limit 10 --refresh
```

参数说明：

| 参数 | 说明 |
|------|------|
| `--src all|tg|plugin` | 指定搜索全部来源、Telegram 频道或插件来源 |
| `--types quark,aliyun` | 指定网盘类型，传 `all` 恢复全部 |
| `--plugins panta,wanou` | 指定插件来源，传 `all` 恢复全部 |
| `--channels tgsearchers4` | 指定频道来源，传 `all` 恢复全部 |
| `--limit 10` | 指定每类结果展示数量 |
| `--refresh` | 跳过本地短缓存，强制刷新上游结果 |

### 可用命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `/start` | 开始使用 | 所有人 |
| `/help` | 帮助信息 | 所有人 |
| `/search <关键词>` | 搜索资源 | 所有人 |
| `/s <关键词>` | 群组内搜索资源 | 所有人 |
| `/status` | 服务状态 | 管理员 |
| `/sources` | 查看 Pansou 来源概况 | 管理员 |
| `/plugins` | 查看当前启用插件 | 管理员 |
| `/channels` | 查看当前启用频道 | 管理员 |
| `/refresh` | 刷新运行时缓存与服务状态 | 管理员 |
| `/update` | 拉取最新代码并重启 | 管理员 |
| `/settings` | 管理设置 | 管理员 |
| `/filter` | 搜索过滤 | 管理员 |
| `/reset` | 重置搜索设置 | 管理员 |

### 管理维护命令

- `/status`：检查 Bot 和 Pansou API 是否正常
- `/sources`：查看 Pansou API 当前插件和频道数量
- `/plugins`：查看当前启用插件，并给出 `/settings plugins ...` 示例
- `/channels`：查看当前启用频道，并给出 `/settings channels ...` 示例
- `/refresh`：清理运行时缓存、限流记录和设置缓存，并重新探测 Pansou API
- `/update`：从 GitHub 拉取当前分支最新代码；如果 `requirements.txt` 有变化，会自动安装依赖并重启机器人

### 设置命令示例

```text
/settings source all
/settings source plugin
/settings types quark,aliyun
/settings types all
/settings plugins panta,wanou
/settings plugins all
/settings channels tgsearchers4
/settings channels all
/settings limit 15
```

默认情况下，Bot 不再主动传固定 `cloud_types` 白名单给上游，避免 Pansou 新增网盘类型后被 Bot 侧过滤。

### `/update` 使用说明

`/update` 适合部署后在线更新，执行前会自动做这些检查：

- 当前目录必须是 Git 仓库
- 当前分支必须可识别并且能访问 `origin/<branch>`
- 本地不能有未提交修改，否则会终止更新，避免覆盖改动

更新成功后，Bot 会自动重启并加载最新代码。

## 🌐 HTTP API

HTTP API 适合提供给本机网关、站点页面或其他 webhook 服务调用。

### 可用接口

| 路径 | 方法 | 说明 |
|------|------|------|
| `/healthz` | `GET` | 检查 HTTP API 和上游 pansou 是否可用 |
| `/api/pansou/search` | `GET` / `POST` | 调用搜索能力并返回结构化 JSON |

### 鉴权方式

默认情况下，HTTP API 会强制校验 `HTTP_API_TOKEN`。请求时需要携带以下任一请求头；只有在你显式设置 `REQUIRE_HTTP_API_TOKEN=false` 时，才会关闭这层鉴权：

```http
Authorization: Bearer your_token
```

或：

```http
X-API-Token: your_token
```

### 请求示例

```bash
curl -H "Authorization: Bearer your_token" \
  "http://127.0.0.1:8090/api/pansou/search?kw=三体&limit=5"
```

```bash
curl -X POST "http://127.0.0.1:8090/api/pansou/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{
    "keyword": "三体",
    "limit": 5,
    "cloud_types": ["quark", "aliyun"]
  }'
```

### 返回结构

接口会返回：

- `summary`：按网盘类型汇总的结果数
- `items`：扁平化后的资源列表，包含 `note`、`url`、`password`、`source`
- `total`：总结果数

这样可以直接给站点页面、Webhook 消息模板或其他机器人二次封装。

## 🔌 Pansou API 适配说明

Bot 会兼容 Pansou API 的多种返回结构：

- `merged_by_type`
- `results`
- `items`
- `results[].links`

同时会归一化常见别名，例如：

- `ali`、`alipan` -> `aliyun`
- `123pan` -> `123`
- `lanzouyun` -> `lanzou`
- `weiyunpan` -> `weiyun`

如果上游 `/api/health` 返回插件和频道信息，Bot 会在 `/sources`、`/plugins`、`/channels` 和 `/status` 中展示。

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

## 🛠️ 技术栈

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
├── api_main.py          # HTTP API 入口
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
    ├── http_api.py      # HTTP API 服务
    ├── config.py        # 配置管理
    ├── pansou_client.py # Pansou API 客户端
    ├── user_settings.py # 用户设置
    └── bot_config.py    # Bot 优化配置
```

## 🧯 故障排查

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
2. 确认 `ADMIN_IDS` 已配置为正确的 Telegram 数字 ID，否则管理员命令不会开放
3. 确认 pansou 服务运行正常：`curl http://localhost:8888/api/health`
4. 检查网络连接
5. 如需刷新状态可执行 `/refresh`
6. 如需在线拉取新版本可执行 `/update`

## 📄 许可证

MIT License

## 🙏 致谢

- [pansou](https://github.com/fish2018/pansou) - 网盘搜索 API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot 框架

---

**维护者**: [Tumblr-code](https://github.com/Tumblr-code)
