from __future__ import annotations

from bot import create_application


def test_application_has_bounded_updates_and_no_online_update_command() -> None:
    application = create_application()
    commands = {
        command
        for handlers in application.handlers.values()
        for handler in handlers
        for command in getattr(handler, "commands", set())
    }

    assert application.update_processor.max_concurrent_updates == 32
    assert "update" not in commands
    assert {"search", "s", "status", "refresh"} <= commands
