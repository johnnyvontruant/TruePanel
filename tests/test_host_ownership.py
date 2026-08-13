import json
import os

import pytest

from truepanel.host.ownership import (
    HostOwnershipError,
    HostOwnershipGuard,
)


def test_ownership_guard_blocks_second_owner(tmp_path):
    path = tmp_path / "host-owner.lock"
    first = HostOwnershipGuard(
        "embedded-lcd",
        path=path,
    )
    second = HostOwnershipGuard(
        "standalone-host-agent",
        path=path,
    )

    first.acquire()
    try:
        record = json.loads(
            path.read_text(encoding="utf-8")
        )
        assert record == {
            "owner": "embedded-lcd",
            "pid": os.getpid(),
        }

        with pytest.raises(
            HostOwnershipError,
            match="embedded-lcd",
        ):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    assert second.held is True
    second.release()
    assert second.held is False


def test_ownership_guard_is_idempotent(tmp_path):
    guard = HostOwnershipGuard(
        "embedded-lcd",
        path=tmp_path / "host-owner.lock",
    )

    guard.acquire()
    guard.acquire()
    assert guard.held is True

    guard.release()
    guard.release()
    assert guard.held is False


def test_ownership_guard_rejects_empty_owner(tmp_path):
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        HostOwnershipGuard(
            "   ",
            path=tmp_path / "host-owner.lock",
        )
