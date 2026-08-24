from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

from config import settings
from logger import get_logger, setup_logging

ROOT = Path(__file__).resolve().parent.parent


def test_application_logs_do_not_attach_sensitive_fields() -> None:
    blocked = {"keyword", "user_id", "chat_id", "update", "token", "message"}
    violations = []

    for source_path in (ROOT / "src").glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"debug", "info", "warning", "error", "exception", "critical"}:
                continue
            names = {keyword.arg for keyword in node.keywords if keyword.arg}
            if names & blocked:
                violations.append((source_path.name, node.lineno, sorted(names & blocked)))

    assert violations == []


def test_log_level_and_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(settings, "log_level", "WARNING")
    setup_logging()
    logger = get_logger("privacy-test")

    logger.info("hidden_event")
    logger.warning("visible_event", duration_ms=12, result_count=3)

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "visible_event"
    assert payload["duration_ms"] == 12
    assert payload["result_count"] == 3


def test_stdlib_logs_are_json_and_tokens_are_redacted(monkeypatch, capsys) -> None:
    monkeypatch.setattr(settings, "log_level", "INFO")
    setup_logging()

    fake_token = "123456789:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    logging.getLogger("third-party").warning("request failed for %s", fake_token)

    line = capsys.readouterr().out.strip()
    payload = json.loads(line)
    assert payload["logger"] == "third-party"
    assert payload["level"] == "warning"
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in payload["event"]
    assert "[REDACTED_TELEGRAM_TOKEN]" in payload["event"]
