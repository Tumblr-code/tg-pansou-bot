from __future__ import annotations

import json
import stat

import pytest

from user_settings import SettingsManager, UserSettings


def test_settings_are_written_atomically_with_private_permissions(tmp_path) -> None:
    manager = SettingsManager(tmp_path / "settings")
    saved = UserSettings(user_id=101, plugins=["panta"], result_limit=5)

    manager.save_settings(saved)

    settings_file = tmp_path / "settings" / "user_101.json"
    assert stat.S_IMODE(settings_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings_file.parent.stat().st_mode) == 0o700
    assert json.loads(settings_file.read_text(encoding="utf-8"))["plugins"] == ["panta"]
    assert not list(settings_file.parent.glob(".settings-*.tmp"))


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        json.dumps({"user_id": 102, "unknown": True}),
        json.dumps({"user_id": 999, "plugins": []}),
    ],
)
def test_invalid_settings_are_quarantined_instead_of_overwritten(tmp_path, payload: str) -> None:
    manager = SettingsManager(tmp_path / "settings")
    settings_file = tmp_path / "settings" / "user_102.json"
    settings_file.write_text(payload, encoding="utf-8")

    loaded = manager.get_settings(102)

    assert loaded.user_id == 102
    quarantined = list(settings_file.parent.glob("user_102.json.invalid-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == payload
    assert json.loads(settings_file.read_text(encoding="utf-8"))["user_id"] == 102


def test_update_rejects_unknown_fields(tmp_path) -> None:
    manager = SettingsManager(tmp_path / "settings")

    with pytest.raises(ValueError, match="unknown settings field"):
        manager.update_settings(103, surprise=True)
