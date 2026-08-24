#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /opt/tg-pansou-bot/releases/<release>" >&2
  exit 1
fi

app_root=/opt/tg-pansou-bot
candidate=$(readlink -f -- "$1")
case "$candidate" in
  "$app_root"/releases/*) ;;
  *)
    echo "candidate must resolve below $app_root/releases" >&2
    exit 1
    ;;
esac

if [[ ! -f $candidate/main.py || ! -x $candidate/.venv/bin/python ]]; then
  echo "candidate is incomplete: $candidate" >&2
  exit 1
fi

atomic_link() {
  local target=$1
  local link_path=$2
  local temp_link="${link_path}.new.$$"
  ln -s "$target" "$temp_link"
  mv -Tf "$temp_link" "$link_path"
}

old_target=""
if [[ -L $app_root/current ]]; then
  old_target=$(readlink -f -- "$app_root/current")
fi

systemctl stop tg-pansou-bot.service
if [[ -n $old_target && $old_target != "$candidate" ]]; then
  atomic_link "$old_target" "$app_root/previous"
fi
atomic_link "$candidate" "$app_root/current"

if systemctl start tg-pansou-bot.service; then
  sleep 3
fi

restart_count=$(systemctl show -p NRestarts --value tg-pansou-bot.service 2>/dev/null || echo 1)
if systemctl is-active --quiet tg-pansou-bot.service && [[ $restart_count == 0 ]]; then
  echo "activated: $candidate"
  exit 0
fi

echo "candidate failed; restoring previous release" >&2
systemctl stop tg-pansou-bot.service || true
if [[ -n $old_target ]]; then
  atomic_link "$old_target" "$app_root/current"
  systemctl start tg-pansou-bot.service
fi
exit 1
