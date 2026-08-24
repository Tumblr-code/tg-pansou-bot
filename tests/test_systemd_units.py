from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pansou_sandbox_allows_sonic_runtime_loader() -> None:
    unit = (ROOT / "deploy/systemd/pansou-native.service").read_text(encoding="utf-8")

    assert "MemoryDenyWriteExecute" not in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "CapabilityBoundingSet=" in unit
    assert "ReadWritePaths=/var/lib/pansou" in unit
