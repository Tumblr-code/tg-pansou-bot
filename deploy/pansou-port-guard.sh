#!/usr/bin/env bash
set -euo pipefail

port=8888

install_rule() {
  local command_name=$1
  local reject_type=$2
  local -a rule=(! -i lo -p tcp --dport "$port" -j REJECT --reject-with "$reject_type")

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required firewall command missing: $command_name" >&2
    exit 1
  fi

  if ! "$command_name" -w 5 -C INPUT "${rule[@]}" 2>/dev/null; then
    "$command_name" -w 5 -I INPUT 1 "${rule[@]}"
  fi
}

install_rule iptables icmp-port-unreachable
install_rule ip6tables icmp6-port-unreachable
