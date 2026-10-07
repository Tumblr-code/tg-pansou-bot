# TG PanSou Bot

[English](README.en.md) · [安装与运维](docs/OPERATIONS.zh-CN.md) · [贡献](CONTRIBUTING.md) · [安全](SECURITY.md)

通过 Telegram long polling 使用 [PanSou](https://github.com/Tumblr-code/pansou) 搜索资源。支持私聊/群聊、网盘分类、分页、刷新、可选 TMDB 影视信息，以及由搜索本人领取完整磁力链接。项目没有 HTTP API，也没有在线自更新命令。

## v1.0.0 生产基线

本版归档 2026-10-07 只读核验的在线 release `20260915T145702Z-b51171327d99`。运行目录没有 `.git`，该后缀不当作已证明的 Git SHA；历史 main 缺少的 TMDB、影视视图、磁力模块和线上修复已按源码白名单补齐。逐文件证据见 [PRODUCTION_SOURCE.json](docs/PRODUCTION_SOURCE.json)，不包含 `.env`、用户设置或令牌。

本轮只同步源码、文档、CI 和发行附件，**没有部署、重启或发送客户消息**。仓库当前未声明项目许可证，本次不擅自添加 MIT 或其他授权；PanSou 后端的 MIT 不等于本 Bot 的授权。依赖继续遵循各自许可证。

## 安装

需要 Python 3.11/3.12、Telegram Bot Token 和可访问的 PanSou API。下载并校验 [Release](https://github.com/Tumblr-code/tg-pansou-bot/releases) 附件：

```bash
sha256sum -c SHA256SUMS
tar -xzf tg-pansou-bot-v1.0.0-source.tar.gz
cd tg-pansou-bot-v1.0.0-source
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 用编辑器填写自己的私密值，再启动：
.venv/bin/python main.py
```

新装 systemd、专用用户、升级/回退、备份恢复见[双语教程](docs/OPERATIONS.zh-CN.md)。真实 Token 不进入 Git、镜像或命令历史。同一 Token 只能运行一个 polling 实例，不能用生产 Token 启动候选来测试。

## 配置与命令

| 变量 | 默认值/作用 |
|---|---|
| `TG_BOT_TOKEN` | 必填，私有 Token |
| `PANSOU_API_URL` | `http://localhost:8888` |
| `PANSOU_API_TOKEN` | 可选后端 Bearer Token |
| `DATA_DIR` | `./data`；生产建议 `/var/lib/tg-pansou-bot` |
| `APP_VERSION` | `dev`；部署时设为发行版本/提交 |
| `DROP_PENDING_UPDATES` | `false`，保留待处理 updates |
| `MAX_CONCURRENT_SEARCHES` / `SEARCH_QUEUE_TIMEOUT` | `4` / `8` 秒 |
| `SEARCH_TIMEOUT` / `MAX_KEYWORD_LENGTH` | `30` 秒 / `128` 字符 |
| `ADMIN_IDS` | 逗号分隔管理员数字 ID |
| `TMDB_READ_ACCESS_TOKEN` / `TMDB_API_KEY` | 可选，留空保持普通资源搜索 |
| `HTTP_PROXY` / `HTTPS_PROXY` | 可选出口代理 |

更多示例见 [.env.example](.env.example)。使用 `/search 关键词` 或 `/s 关键词` 搜索；来源、插件、频道、过滤及设置管理保留原管理员限制。磁力取回校验原搜索用户和当前结果版本；超长链接以文本文件返回，不截断 URI。默认 JSON 日志屏蔽 Token/Bearer/API key，不输出原始搜索词或用户 ID。

## 开发与发布

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/verify_production_source.py
.venv/bin/python scripts/secret_scan.py
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/python scripts/smoke_test.py
.venv/bin/python -m pip check
.venv/bin/python scripts/package_release.py --version v1.0.0
```

发布包仅含 Git 白名单应用源码、模板、文档、来源清单与校验和，不附带解释器、虚拟环境、私有数据或令牌。直接依赖版本保留生产声明，安装时仍需取得相应依赖；发行包不是离线 wheel 仓。CI 使用模拟数据和网络客户端，不执行真实 Telegram 通知。
