from __future__ import annotations

import pytest
from pydantic import ValidationError

from config import Settings


def make_settings(**overrides) -> Settings:
    values = {"tg_bot_token": "test-token", **overrides}
    return Settings(_env_file=None, **values)


def test_default_production_safety_settings() -> None:
    configured = make_settings()

    assert configured.drop_pending_updates is False
    assert configured.max_concurrent_searches == 4
    assert configured.search_queue_timeout == 8
    assert configured.max_keyword_length == 128


@pytest.mark.parametrize("level", ["debug", "INFO", "Warning"])
def test_log_level_is_normalized(level: str) -> None:
    assert make_settings(log_level=level).log_level == level.upper()


def test_invalid_result_limit_relationship_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(default_result_limit=30, max_result_limit=20)


def test_invalid_admin_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(admin_ids="123,not-a-number")
