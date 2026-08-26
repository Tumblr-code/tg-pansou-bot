#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

if [[ $# -ne 1 || ! $1 =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  echo "usage: $0 <git-sha>" >&2
  exit 1
fi

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
release_root=/opt/tg-pansou-bot/releases
release_id="$(date -u +%Y%m%dT%H%M%SZ)-${1:0:12}"
candidate="${release_root}/${release_id}"

if [[ -e $candidate ]]; then
  echo "release already exists: $candidate" >&2
  exit 1
fi

install -d -o root -g root -m 0755 "$release_root" "$candidate"
rsync -a \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='data/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='*.log' \
  "$source_dir/" "$candidate/"

# rsync preserves the source directory mode on the destination root. Normalize
# it so the unprivileged service account can always enter the release.
chmod 0755 "$candidate"

python3 -m venv "$candidate/.venv"
"$candidate/.venv/bin/python" -m pip install --disable-pip-version-check -r "$candidate/requirements.txt"
"$candidate/.venv/bin/python" -m pip check

check_dir=$(mktemp -d /tmp/tg-pansou-check.XXXXXX)
cleanup() {
  rm -rf -- "$check_dir"
}
trap cleanup EXIT

python3 -m venv "$check_dir/venv"
"$check_dir/venv/bin/python" -m pip install --disable-pip-version-check -r "$candidate/requirements-dev.txt"
verify_data="$check_dir/data"
install -d -m 0700 "$verify_data"
(
  cd "$candidate"
  export DATA_DIR="$verify_data"
  export TG_BOT_TOKEN=12345:RELEASE_CHECK_TOKEN_PLACEHOLDER_12345
  "$check_dir/venv/bin/python" -m compileall -q main.py src scripts tests
  "$check_dir/venv/bin/python" scripts/secret_scan.py
  "$check_dir/venv/bin/python" scripts/smoke_test.py
  "$check_dir/venv/bin/ruff" check .
  "$check_dir/venv/bin/pytest" -q
  "$check_dir/venv/bin/python" -m pip check
)

chown -R root:root "$candidate"
chmod -R go-w "$candidate"
echo "$candidate"
