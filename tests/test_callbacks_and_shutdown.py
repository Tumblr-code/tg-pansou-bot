from __future__ import annotations

import asyncio

import pytest

import runtime_state
from keyboards import is_cache_owner, parse_type_callback


def test_callback_ownership_requires_chat_user_and_message() -> None:
    key = "-1001:2002:3003"

    assert is_cache_owner(key, -1001, 2002, 3003)
    assert not is_cache_owner(key, -1001, 9999, 3003)
    assert not is_cache_owner(key, -1001, 2002, 9999)
    assert not is_cache_owner("malformed", -1001, 2002, 3003)


def test_type_callback_parser_preserves_signed_chat_id() -> None:
    assert parse_type_callback("type:-1001:2002:3003:quark:2") == (
        "-1001:2002:3003",
        "quark",
        2,
    )


@pytest.mark.asyncio
async def test_runtime_shutdown_cancels_cleanup_task() -> None:
    started = asyncio.Event()

    async def worker() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(worker())
    await started.wait()
    runtime_state._cleanup_task = task
    runtime_state._deletion_tasks[(1, 2)] = 3.0

    await runtime_state.shutdown_runtime_state()

    assert task.cancelled()
    assert runtime_state._cleanup_task is None
    assert runtime_state._deletion_tasks == {}
