from datetime import UTC, datetime, timedelta

import pytest

from truepanel.lab.authorization import (
    ExecutionAuthorization,
)


def test_authorization_is_valid_for_its_request():
    now = datetime.now(UTC)

    authorization = ExecutionAuthorization.issue(
        "request-1",
        now=now,
    )

    assert authorization.is_valid_for(
        "request-1",
        now=now,
    )


def test_authorization_rejects_other_request():
    authorization = ExecutionAuthorization.issue(
        "request-1"
    )

    assert not authorization.is_valid_for(
        "request-2"
    )


def test_authorization_expires():
    now = datetime.now(UTC)

    authorization = ExecutionAuthorization.issue(
        "request-1",
        lifetime_seconds=10,
        now=now,
    )

    assert not authorization.is_valid_for(
        "request-1",
        now=now + timedelta(seconds=10),
    )


def test_authorization_has_unique_token():
    first = ExecutionAuthorization.issue("request-1")
    second = ExecutionAuthorization.issue("request-1")

    assert first.token != second.token


def test_authorization_requires_request_id():
    with pytest.raises(ValueError):
        ExecutionAuthorization.issue("")


def test_authorization_requires_positive_lifetime():
    with pytest.raises(ValueError):
        ExecutionAuthorization.issue(
            "request-1",
            lifetime_seconds=0,
        )
