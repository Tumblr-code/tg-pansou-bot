from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_release_is_traversable_by_service_user() -> None:
    script = (ROOT / "scripts/build_release.sh").read_text(encoding="utf-8")

    assert 'chmod 0755 "$candidate"' in script
