# 更新日志

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 🔐 安全基线与工程化

### Added

- 新增 GitHub Actions CI，包含 secret scan、Python 编译检查、smoke import test 和 Docker build 校验
- 新增 `scripts/secret_scan.py`，阻止 `.env.*` 备份文件和明显的 Telegram Bot Token 被提交
- 新增 `scripts/smoke_test.py`，在不启动真实 Bot 的前提下验证核心模块可导入
- 新增 `REQUIRE_HTTP_API_TOKEN` 配置项，用于显式控制 HTTP API 是否允许无令牌访问

### Changed

- `api_main.py` 在安全模式下若未配置 `HTTP_API_TOKEN` 会直接拒绝启动
- `src/http_api.py` 默认改为要求令牌鉴权，只有显式关闭安全模式时才允许匿名访问
- `src/bot.py` 抽出统一搜索流程，减少普通搜索与回调重搜之间的重复逻辑
- `.gitignore` 增强为忽略 `.env.*` 和 `.env.backup*` 变体，避免敏感文件误提交
- README 与 `.env.example` 补充 HTTP API 安全默认值和本地检查说明

### Fixed

- 移除误加入仓库的 `.env.backup.20260228_200505` 敏感备份文件

## [2.3.0] - 2026-03-19

### 💼 企业微信客服接入

### Added

- 新增 `src/wecom_service.py`，支持企业微信客服回调验签、AES 解密、消息读取和自动回复
- 新增 `/api/wecom/accounts`，可查询当前企业微信客服账号列表
- 新增 `/wecom/callback`，可直接作为企业微信客服开发配置里的回调地址
- 新增 `WECOM_CORP_ID`、`WECOM_SECRET`、`WECOM_TOKEN`、`WECOM_ENCODING_AES_KEY`、`WECOM_OPEN_KFID`、`WECOM_SEARCH_LIMIT` 配置项

### Changed

- HTTP API 健康检查现在会额外返回企业微信客服配置状态
- 企业微信客服回调改为快速应答、后台异步处理，减少平台重试造成的重复请求
- README 和 `.env.example` 补充企业微信客服接入说明、回调地址和账号查询用法

## [2.2.0] - 2026-03-19

### 🌐 Webhook 接入准备

### Added

- 新增独立 `HTTP API` 入口 `api_main.py`
- 新增 `src/http_api.py`，提供 `/healthz` 和 `/api/pansou/search`
- 新增 `HTTP_API_HOST`、`HTTP_API_PORT`、`HTTP_API_TOKEN` 配置项
- 新增结构化 JSON 搜索输出，便于企业微信客服、Webhook 和站点页面复用

### Changed

- README 和 `.env.example` 补充 HTTP API 启动方式、鉴权方式和请求示例
- 搜索能力从纯 Telegram 交互扩展为可复用的本地服务层

## [2.1.0] - 2026-03-18

### 🚀 稳定性与运维升级

### Added

- 新增管理员命令 `/refresh`，用于刷新运行时缓存、限流记录和健康检查状态
- 新增管理员命令 `/update`，支持拉取 GitHub 最新代码、按需安装依赖并自动重启机器人
- 新增搜索请求并发合并机制，相同查询会复用同一次上游请求
- 新增上游搜索结果短时缓存，热门查询可直接命中缓存
- 新增健康检查短缓存，避免频繁探活拖慢响应
- 新增每用户滑动窗口限流，减少高频请求对上游服务的冲击

### Changed

- 搜索缓存 TTL 改为基于单调时钟，避免系统时间变化导致缓存判断异常
- 搜索结果请求量改为按实际显示需求控制，降低单次查询对上游 API 的压力
- 回调按钮处理逻辑重构，确保群聊场景下只能操作自己发起的搜索结果
- 帮助文档与 README 补充维护命令说明和管理员 ID 必填说明

### Fixed

- 修复管理员未配置时默认放开所有高级命令权限的问题
- 修复 Telegram HTML 模式下关键词、用户名、错误信息和搜索结果未转义导致的格式异常
- 修复回调按钮在结果过期、跨用户点击或回调数据解析时的状态不一致问题
- 修复 `rate_limit_per_minute` 配置存在但未实际生效的问题

## [1.1.0] - 2026-03-13

### ⚡ 性能优化

### Changed

- **HTTP 客户端优化**
  - 采用单例模式复用 HTTP 客户端，避免重复创建连接
  - 连接池大小从 10/20 提升到 20/50
  - 启用 HTTP/2 支持，减少网络延迟
  - 优化超时配置：连接超时 5s，读取超时 30s

- **重试机制优化**
  - 实现指数退避重试策略 (0.5s → 1s → 2s → 5s)
  - 新增 `RemoteProtocolError` 异常处理
  - 重试次数从 2 次提升到 3 次

- **缓存系统优化**
  - 新增 LRU 缓存类，支持 TTL 自动过期
  - 缓存大小限制为 50 条，防止内存泄漏
  - 缓存有效期 5 分钟自动清理

- **Bot 配置优化**
  - 连接池大小从 16 提升到 32
  - 优化各超时参数配置

### Fixed

- 修复网络不稳定时频繁断开连接的问题
- 修复长时间运行后内存占用过高的问题
- 修复缓存无限制增长导致的性能下降

## [1.0.0] - 2026-02-26

### 🎉 初始发布

### Added

- 🔍 智能网盘资源搜索功能
- 💬 支持私聊和群组使用
- 📁 支持多种网盘类型（百度、阿里、夸克、天翼等）
- 🔄 搜索结果刷新功能
- ⚡ 异步处理，快速响应
- 🐳 Docker 部署支持
- 📝 详细的部署文档和教程

### 支持的网盘

- 百度网盘
- 阿里云盘
- 夸克网盘
- 天翼云盘
- UC网盘
- 移动云盘
- 115网盘
- PikPak
- 迅雷网盘
- 123网盘
- 磁力链接
- 电驴链接

---

Made with ❤️ by TG Pansou Bot Team
