# TG Pansou Bot

基于 Telegram 与 [PanSou](https://github.com/fish2018/pansou) 的网盘搜索机器人。运行接口只有 Telegram long polling；项目不提供 HTTP API，也不包含在线自更新命令。

## 功能

- `/search 关键词`：私聊或群聊搜索
- `/s 关键词`：群聊短命令
- 按网盘分类、分页、刷新和显示全部
- 管理员可管理来源、插件、频道、过滤器和个人设置
- 120 秒结果缓存与相同请求合并
- 最多 4 个上游搜索并发，排队默认最多 8 秒
- 用户设置以原子 JSON 文件保存，损坏或未知结构会隔离而不是覆盖
- JSON 结构化日志，不记录原始搜索词、Telegram 用户 ID、完整 Update 或令牌

## 运行要求

- Python 3.11 或 3.12
- 已运行的 PanSou API，默认 `http://127.0.0.1:8888`
- Telegram Bot Token

## 配置

复制示例后填写私密值；不要提交 `.env`。

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

主要配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TG_BOT_TOKEN` | 必填 | Telegram Bot Token |
| `PANSOU_API_URL` | `http://localhost:8888` | PanSou API 地址 |
| `PANSOU_API_TOKEN` | 空 | PanSou Bearer Token |
| `DATA_DIR` | `./data` | 用户设置目录；生产建议 `/var/lib/tg-pansou-bot` |
| `APP_VERSION` | `dev` | `/status` 显示的只读发布版本 |
| `DROP_PENDING_UPDATES` | `false` | 正常重启时保留 pending updates |
| `MAX_CONCURRENT_SEARCHES` | `4` | 上游搜索并发上限 |
| `SEARCH_QUEUE_TIMEOUT` | `8` | 搜索排队超时（秒） |
| `MAX_KEYWORD_LENGTH` | `128` | 搜索关键词最大字符数；最小为 2 |
| `SEARCH_TIMEOUT` | `30` | 上游 HTTP read 超时（秒） |
| `LOG_LEVEL` | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |
| `ADMIN_IDS` | 空 | 逗号分隔的 Telegram 管理员数字 ID |

HTTPX 对 PanSou 使用 connect/pool 5 秒、write 10 秒和 `SEARCH_TIMEOUT` read 超时。

## 搜索与管理命令

```text
/search 三体
/search 三体 --src plugin --types quark,aliyun --plugins panta --limit 5 --refresh
/s 三体
/status
/sources
/plugins
/channels
/settings
/filter
/reset
/refresh
```

普通用户保留搜索、分类、分页和刷新结果能力；来源和设置命令继续受现有管理员权限控制。

## 开发验证

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/python scripts/secret_scan.py
.venv/bin/python scripts/smoke_test.py
.venv/bin/python -m pip check
docker build -t tg-pansou-bot:local .
```

Secret scan 只读取 Git 已跟踪或已暂存文件，不会扫描未跟踪的生产 `.env`、`data/` 或虚拟环境。

## 生产部署

生产使用专用 `tgpansou` 用户、只读 release 目录、`/opt/tg-pansou-bot/current` 与 `previous` 原子链接，并将状态放在 `/var/lib/tg-pansou-bot`。完整安装、切换、验证与回滚流程见 [DEPLOY.md](DEPLOY.md)。

Docker 仅用于开发或独立部署：

```bash
docker compose up -d --build
```

Compose 默认以非 root、只读根文件系统和空 capability 集运行，状态写入 `./data`。
