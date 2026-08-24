# 生产部署与回滚

本文档对应 Ubuntu 24.04 + systemd。生产运行目录不可直接编辑；每次发布创建新的只读 release，再原子切换 `current`。

## 目录与权限

```text
/opt/tg-pansou-bot/
  releases/<timestamp>-<sha>/
  current -> releases/<candidate>
  previous -> releases/<rollback>
/var/lib/tg-pansou-bot/       0700 tgpansou:tgpansou
/etc/tg-pansou-bot/bot.env   0640 root:tgpansou

/opt/pansou/
  releases/<timestamp>-<binary-sha>/
  current -> releases/<candidate>
  previous -> releases/<rollback>
/var/lib/pansou/cache/        0700 pansou:pansou
/etc/pansou/pansou.env        0640 root:pansou
```

创建服务账号和目录：

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin tgpansou
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin pansou
sudo install -d -o root -g root -m 0755 /opt/tg-pansou-bot/releases /opt/pansou/releases
sudo install -d -o tgpansou -g tgpansou -m 0700 /var/lib/tg-pansou-bot
sudo install -d -o pansou -g pansou -m 0700 /var/lib/pansou/cache
sudo install -d -o root -g tgpansou -m 0750 /etc/tg-pansou-bot
sudo install -d -o root -g pansou -m 0750 /etc/pansou
```

将现有环境文件复制到 `/etc/tg-pansou-bot/bot.env`，保留 Token，不要在终端输出内容；补充：

```env
DATA_DIR=/var/lib/tg-pansou-bot
APP_VERSION=<git-sha>
DROP_PENDING_UPDATES=false
MAX_CONCURRENT_SEARCHES=4
SEARCH_QUEUE_TIMEOUT=8
MAX_KEYWORD_LENGTH=128
```

设置 `0640 root:tgpansou`。PanSou 环境文件同理设置 `0640 root:pansou`，只把缓存路径改为 `/var/lib/pansou/cache`，其余插件、频道和缓存参数保持不变。

## 构建 Bot 候选 release

在干净的已合并提交中运行：

```bash
sudo ./scripts/build_release.sh <git-sha>
```

脚本输出候选目录；它只复制项目文件，排除 `.env`、`data/`、虚拟环境、日志和缓存，创建独立 `.venv`，按锁文件安装依赖，并执行离线 smoke、pytest、Ruff、secret scan 与 `pip check`。候选目录最终为 root 所有且不可由服务账号写入。

安装单元：

```bash
sudo install -o root -g root -m 0644 deploy/systemd/tg-pansou-bot.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/systemd/pansou-native.service /etc/systemd/system/
sudo install -o root -g root -m 0755 deploy/pansou-port-guard.sh /usr/local/sbin/pansou-port-guard
sudo install -o root -g root -m 0644 deploy/systemd/pansou-port-guard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pansou-port-guard.service pansou-native.service tg-pansou-bot.service
```

## Bot 切换

首次切换前确认已有外部备份。候选验证通过后：

```bash
sudo systemctl stop tg-pansou-bot.service
sudo rsync -a --chmod=Du=rwx,Dgo=,Fu=rw,Fgo= /root/tg-pansou-bot/data/ /var/lib/tg-pansou-bot/
sudo chown -R tgpansou:tgpansou /var/lib/tg-pansou-bot
sudo ./scripts/activate_release.sh /opt/tg-pansou-bot/releases/<candidate>
sudo systemctl disable --now tg-pansou-http-api.service
sudo rm -f /etc/systemd/system/tg-pansou-http-api.service
sudo systemctl daemon-reload
```

`activate_release.sh` 会保存旧 `current` 为 `previous`，原子切换后启动并检查 Bot；启动失败会立即恢复旧链接。确认 HTTP API 已退役：

```bash
sudo ss -lntp | grep ':8090 ' && exit 1 || true
sudo systemctl is-enabled tg-pansou-http-api.service 2>/dev/null && exit 1 || true
```

## PanSou 切换

Bot 稳定后再单独迁移 PanSou，二进制、插件、频道和缓存配置版本必须保持不变。复制原 release 到 `/opt/pansou/releases/<timestamp>-<binary-sha>`，由 root 持有并移除组/其他写权限；短暂停服后将缓存最终同步到 `/var/lib/pansou/cache`，再原子切换 `/opt/pansou/current`。

启动前必须先应用 `pansou-port-guard.service`。PanSou 即使监听 `*:8888`，IPv4/IPv6 的所有非 loopback 入站都应被 REJECT；Bot 仍通过 `127.0.0.1:8888` 访问。

## 验证

```bash
systemctl is-active tg-pansou-bot.service pansou-native.service pansou-port-guard.service
systemctl show -p User,Group,NRestarts tg-pansou-bot.service pansou-native.service
systemd-analyze security tg-pansou-bot.service pansou-native.service
curl --fail --silent http://127.0.0.1:8888/api/health
ss -lntp | grep -E ':(8090|8888) '
journalctl -u tg-pansou-bot.service -n 50 --no-pager
```

还需完成：Telegram `getMe`、`/status`、一次真实搜索、分类、分页；PanSou 一次真实搜索与缓存写入；从另一台 LAN 主机验证 `192.168.0.35:8888` 的 IPv4/IPv6 都不可达；确认两个服务 `NRestarts=0`。

## 回滚

```bash
sudo ./scripts/activate_release.sh /opt/tg-pansou-bot/previous
```

PanSou 回滚时单独停止服务，将 `current` 原子指回 `previous`，恢复旧单元后启动。出现反复重启、健康失败、设置文件异常或真实搜索失败时立即回滚。旧 `/root` 运行目录和完整备份至少保留 24 小时，不立即删除。

SSH 策略、root 密码轮换和系统包升级不属于本项目发布；确认密钥登录后另行轮换已暴露的密码。
