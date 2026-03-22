#!/usr/bin/env python3
"""最小 secret 扫描脚本。

目标：阻止明显的 env 备份、真实 Telegram Bot Token 等被提交。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCKED_FILE_PATTERNS = [
    re.compile(r"^\.env\.backup.*$"),
    re.compile(r"^\.env\..+$"),
]

# Telegram Bot Token 常见格式：数字:id 风格
TG_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")

ALLOWED_FILES = {".env.example"}


def scan() -> list[str]:
    problems: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(ROOT).as_posix()
        name = path.name

        if ".git/" in rel or rel.startswith(".git/"):
            continue

        if name not in ALLOWED_FILES:
            for pattern in BLOCKED_FILE_PATTERNS:
                if pattern.match(name):
                    problems.append(f"blocked sensitive file: {rel}")
                    break

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if name not in ALLOWED_FILES and TG_TOKEN_RE.search(text):
            problems.append(f"possible Telegram token found in: {rel}")

    return problems


if __name__ == "__main__":
    found = scan()
    if found:
        print("Secret scan failed:")
        for item in found:
            print(f"- {item}")
        sys.exit(1)

    print("Secret scan passed")
