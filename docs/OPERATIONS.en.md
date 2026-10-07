# TG PanSou Bot installation and operations

[简体中文](OPERATIONS.zh-CN.md) · [Home](../README.en.md)

## Fresh installation (Ubuntu 24.04/systemd)

Install Python 3.11/3.12 with venv and ca-certificates. Provide an already reachable PanSou backend. Verify `SHA256SUMS` before extraction. Run this example inside the extracted directory; do not recreate existing accounts/directories or put private configuration in a release.

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

Before starting, privately configure `TG_BOT_TOKEN`, `PANSOU_API_URL`, `DATA_DIR=/var/lib/tg-pansou-bot`, `APP_VERSION=v1.0.0`, and administrator IDs. Preserve `DROP_PENDING_UPDATES=false`. Supply one optional TMDB credential only when needed; both may remain empty. Follow the backend repository's guide for PanSou itself; do not overwrite or duplicate an existing backend installation.

## Docker alternative

The existing Compose file uses Linux host networking, a non-root user, a read-only root filesystem and `/data`. Create `./data` writable only by uid/gid 1000, fill a private `.env`, then run `docker compose up -d --build`. The backend URL uses host loopback in this Linux configuration. Never run Docker and systemd polling instances for the same token concurrently.

## Verification and troubleshooting

Check `systemctl is-active tg-pansou-bot.service`, `systemctl show -p MainPID,NRestarts tg-pansou-bot.service`, and `journalctl -u tg-pansou-bot.service -n 50 --no-pager`. Logs are operator-only and still require redaction before sharing. Isolated `scripts/smoke_test.py` and pytest need no real token. Operators separately validate production `/status`, search, categories, pagination, and magnet delivery.

- `Conflict/getUpdates`: another instance uses the same token. Identify its owner; do not clear pending updates as a workaround.
- Backend failures: check local PanSou health, URL, proxy and authentication. Preserve existing authentication and the private network boundary.
- Settings write failures: align `DATA_DIR`, 0700 ownership and systemd writable paths. Unknown or corrupt files are quarantined; preserve evidence before recovery.
- TMDB failure: check your credential and egress. Optional metadata failure preserves resource search; visible posters do not prove every provider works.

## Upgrade and rollback

Verify the candidate package, unpack a new root-owned release, create its own venv and run offline checks. Do not test with a second production-token process. Save `current`, private configuration and units. Stop the Bot and back up user settings, then use `scripts/activate_release.sh /opt/tg-pansou-bot/releases/<candidate>`. It saves `previous` and switches atomically; startup failure restores the old link. An active process is not business acceptance. Roll back with `scripts/activate_release.sh /opt/tg-pansou-bot/previous` only after checking compatibility with current settings; never overwrite newer user data.

## Backup and recovery

Stop the Bot before copying `/var/lib/tg-pansou-bot`, private `/etc/tg-pansou-bot`, units and release-link targets. Use 0700 backup directories, 0600 files, checksums, encryption and off-host storage. Never publish settings or tokens. Rehearse recovery in isolated directories with a dummy token and no real polling: verify JSON structure, ownership, offline smoke and tests. For actual recovery, stop the sole production instance first and restore matching code/data. Do not delete quarantined evidence or blindly replace newer data.

## Publication and licensing

Main/PR CI only validates changes. Final Releases upload source/provenance/checksum assets without deploying. No repository-wide license has been declared; this does not authorize relabeling the project as MIT. `DEPLOY.md` remains a historical migration record. This guide is the v1.0.0 installation and operations entry point.
