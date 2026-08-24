"""Maintenance command helpers for safe in-chat updates."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from structlog import get_logger

logger = get_logger()

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "main.py"
UPDATE_COMMAND_TIMEOUT = 300
PIP_INSTALL_TIMEOUT = 600
MAX_COMMAND_OUTPUT = 1200


def truncate_output(text: str, limit: int = MAX_COMMAND_OUTPUT) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}\n...（输出已截断）"


async def run_command(
    *args: str,
    timeout: int = UPDATE_COMMAND_TIMEOUT,
    cwd: Path = REPO_ROOT,
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return 124, "", f"命令执行超时（>{timeout}秒）"

    return (
        process.returncode,
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
    )


def _looks_like_git_tls_error(detail: str) -> bool:
    lowered = detail.lower()
    indicators = (
        "gnutls_handshake()",
        "tls connection was non-properly terminated",
        "http/2 stream",
        "http2 stream",
        "curl 56",
        "remote end hung up unexpectedly",
        "recv failure",
        "connection reset by peer",
    )
    return any(indicator in lowered for indicator in indicators)


async def run_git_command(
    *args: str,
    timeout: int = UPDATE_COMMAND_TIMEOUT,
    cwd: Path = REPO_ROOT,
) -> tuple[int, str, str]:
    commands = [
        ("default", ("git", *args)),
        (
            "http1_fallback",
            (
                "git",
                "-c",
                "http.version=HTTP/1.1",
                "-c",
                "http.maxRequests=1",
                *args,
            ),
        ),
    ]

    last_result = (1, "", "")
    for mode, command in commands:
        code, stdout, stderr = await run_command(*command, timeout=timeout, cwd=cwd)
        if code == 0:
            return code, stdout, stderr

        last_result = (code, stdout, stderr)
        detail = "\n".join(part for part in (stderr, stdout) if part)
        if mode == "default" and _looks_like_git_tls_error(detail):
            logger.warning("git_command_retry_with_http1", args=list(args), error=detail)
            await asyncio.sleep(1)
            continue
        break

    return last_result


async def restart_process(delay_seconds: float = 1.0) -> None:
    await asyncio.sleep(delay_seconds)
    os.chdir(str(REPO_ROOT))
    os.execv(sys.executable, [sys.executable, str(ENTRYPOINT)])
