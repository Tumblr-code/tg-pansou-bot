# TG PanSou Bot 安装与运维

[English](OPERATIONS.en.md) · [首页](../README.md)

## 新装（Ubuntu 24.04/systemd）

需要 Python 3.11/3.12 及 venv、ca-certificates，已安装且可访问的 PanSou 后端。先核验下载包的 `SHA256SUMS`。在解压目录执行；已有账号/目录无需重复创建。不要把私有配置放进 release。

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin tgpansou
sudo install -d -m 0755 /opt/tg-pansou-bot/releases
sudo install -d -o tgpansou -g tgpansou -m 0700 /var/lib/tg-pansou-bot
sudo install -d -o root -g tgpansou -m 0750 /etc/tg-pansou-bot
sudo cp -a . /opt/tg-pansou-bot/releases/v1.0.0
sudo python3 -m venv /opt/tg-pansou-bot/releases/v1.0.0/.venv
sudo /opt/tg-pansou-bot/releases/v1.0.0/.venv/bin/pip install -r /opt/tg-pansou-bot/releases/v1.0.0/requirements.txt
sudo chown -R root:root /opt/tg-pansou-bot/releases/v1.0.0
sudo chmod -R go-w /opt/tg-pansou-bot/releases/v1.0.0
sudo install -o root -g tgpansou -m 0640 .env.example /etc/tg-pansou-bot/bot.env
sudoedit /etc/tg-pansou-bot/bot.env
sudo install -m 0644 deploy/systemd/tg-pansou-bot.service /etc/systemd/system/
sudo ln -s /opt/tg-pansou-bot/releases/v1.0.0 /opt/tg-pansou-bot/current
sudo systemctl daemon-reload
sudo systemctl enable --now tg-pansou-bot.service
```

启动前在私有环境文件中设置真实 `TG_BOT_TOKEN`、正确的 `PANSOU_API_URL`、`DATA_DIR=/var/lib/tg-pansou-bot`、`APP_VERSION=v1.0.0` 和管理员 ID。保留 `DROP_PENDING_UPDATES=false`。需要 TMDB 时自行填入一种凭据，两项均为空时无需 TMDB。PanSou 自身的安装教程在其仓库；不要重复安装或覆盖已运行的后端。

## Docker 方式

现有 `docker-compose.yml` 使用 host 网络、非 root、只读根目录与单独 `/data`。先以 uid/gid 1000 建好仅服务可读写的 `./data`，并在私有 `.env` 中填写值；执行 `docker compose up -d --build`。host 网络示例面向 Linux，后端地址是宿主机 loopback。不要同时运行 systemd 与 Docker 两个 polling 实例。

## 验证与故障

`systemctl is-active tg-pansou-bot.service`、`systemctl show -p MainPID,NRestarts tg-pansou-bot.service` 和 `journalctl -u tg-pansou-bot.service -n 50 --no-pager` 可核验进程。日志只供维护者查看，贴 issue 前仍需脱敏。隔离测试用 `scripts/smoke_test.py` 和 pytest，不需要真实 Token；生产 `/status`、搜索、分类、分页和磁力领取由部署者另行验收。

- `Conflict/getUpdates`：同一 Token 有另一 polling 实例；先定位所有者，不能随意清空 pending updates。
- 上游不可用：检查 PanSou 本机健康、URL/代理/认证；不要为恢复搜索关闭现有鉴权或公网暴露端口。
- 设置不可写：检查 `DATA_DIR`、0700 属主及 systemd 可写目录；未知或损坏设置文件会隔离，先留存证据再恢复。
- TMDB 不可用：核验自有凭据和出口。可选元数据失败会保留资源搜索；不能以封面显示证明所有来源正常。

## 升级与回退

先下载校验新包、在新的 root 所有 release 目录建独立 venv，运行离线检查；不要用生产 Token 启动第二实例。保存原 `current`、环境和单元。停 Bot 后备份用户设置，再执行仓库已有 `scripts/activate_release.sh /opt/tg-pansou-bot/releases/<candidate>`；脚本保存 `previous` 并原子切换。启动失败会恢复旧链接，但进程 active 不替代业务验收。回退可执行 `scripts/activate_release.sh /opt/tg-pansou-bot/previous`；确认旧版本可读现有设置结构，不覆盖较新的用户数据。

## 备份与恢复

停 Bot 后备份 `/var/lib/tg-pansou-bot`、私有 `/etc/tg-pansou-bot`、服务单元和 release 链接目标。备份目录0700、文件0600，校验和、加密、异机保存；不得上传用户设置/Token到GitHub。恢复演练使用隔离目录与假 Token，不启动真实 polling：恢复后检查 JSON 结构、属主、离线 smoke 与测试。实际恢复前再停唯一生产实例，恢复匹配版本和数据后核验，不删除异常隔离文件或盲目覆盖新数据。

## 发布与许可

main/PR 仅 CI；正式 Release 上传来源包和 SHA256，均不会自动部署。项目尚无仓库级许可证，不代表可以按 MIT 重新授权。历史迁移说明 `DEPLOY.md` 留作记录，本指南是 v1.0.0 的新装与维护入口。
