# TG PanSou Bot

[简体中文](README.md) · [Installation and operations](docs/OPERATIONS.en.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

A Telegram long-polling bot for [PanSou](https://github.com/Tumblr-code/pansou), with private/group search, storage-provider categories, pagination, refresh, optional TMDB metadata, and owner-checked delivery of complete magnet links. There is no HTTP API or online self-update command.

## Production baseline for v1.0.0

This release captures the running `20260915T145702Z-b51171327d99` release inspected read-only on 2026-10-07. Its directory has no `.git`; the suffix is not presented as a verified Git SHA. The missing TMDB, media-view, magnet modules and deployed fixes were recovered through a source-only allowlist. [PRODUCTION_SOURCE.json](docs/PRODUCTION_SOURCE.json) records individual hashes without environment files, user settings or tokens.

This work synchronized source, documentation, CI and release assets. **It did not deploy, restart services or send customer messages.** The repository has no declared project license; this release does not select MIT or another license for the owner. The backend's MIT license does not license this Bot. Dependencies retain their own terms.

## Installation

Use Python 3.11/3.12, a Telegram Bot Token, and a reachable PanSou API. Download and verify the [Release](https://github.com/Tumblr-code/tg-pansou-bot/releases) assets:

```bash
sha256sum -c SHA256SUMS
tar -xzf tg-pansou-bot-v1.0.0-source.tar.gz
cd tg-pansou-bot-v1.0.0-source
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit private values locally before starting:
.venv/bin/python main.py
```

See the [operations guide](docs/OPERATIONS.en.md) for systemd, service accounts, upgrades, rollback, backup and recovery. Never place real tokens in Git, images or shell history. Run only one polling instance per token; do not use a production token to test a candidate.

## Configuration and commands

| Variable | Default or purpose |
|---|---|
| `TG_BOT_TOKEN` | Required private token |
| `PANSOU_API_URL` | `http://localhost:8888` |
| `PANSOU_API_TOKEN` | Optional backend Bearer token |
| `DATA_DIR` | `./data`; use `/var/lib/tg-pansou-bot` for systemd |
| `APP_VERSION` | `dev`; set a release/revision when deploying |
| `DROP_PENDING_UPDATES` | `false`; preserve pending updates |
| `MAX_CONCURRENT_SEARCHES` / `SEARCH_QUEUE_TIMEOUT` | `4` / `8` seconds |
| `SEARCH_TIMEOUT` / `MAX_KEYWORD_LENGTH` | `30` seconds / `128` characters |
| `ADMIN_IDS` | Comma-separated numeric administrator IDs |
| `TMDB_READ_ACCESS_TOKEN` / `TMDB_API_KEY` | Optional; leave blank for resource-only search |
| `HTTP_PROXY` / `HTTPS_PROXY` | Optional outbound proxies |

See [.env.example](.env.example). Search with `/search keyword` or `/s keyword`; source, plugin, channel, filter and settings administration retains its existing permission checks. Magnet delivery verifies the original search user and current result revision. Very long links are sent as text files without truncating the URI. Default JSON logs redact token/Bearer/API-key values and omit raw queries and user IDs.

## Development and release

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

The source package includes only allowlisted Git application source, templates, guides, provenance and checksums. It excludes the interpreter, virtual environments, private data and tokens. Direct dependency versions preserve production declarations; installation still downloads dependencies. This is not an offline wheel repository. CI uses mocks and never sends real Telegram notifications.
