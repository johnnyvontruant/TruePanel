from truepanel.health.services import (
    REQUIRED_SERVICES,
    ServiceStatusProvider,
)


class Result:
    def __init__(self, stdout=""):
        self.stdout = stdout


def test_service_status_provider_reports_required_units():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)

        return Result(
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
        )

    provider = ServiceStatusProvider(
        runner=runner,
        clock=lambda: 100.0,
    )

    payload = provider.snapshot()

    assert payload["available"] is True

    assert [
        service["name"]
        for service in payload["services"]
    ] == list(REQUIRED_SERVICES)

    assert all(
        service["required"] is True
        for service in payload["services"]
    )

    assert all(
        service["active_state"] == "active"
        for service in payload["services"]
    )

    assert len(calls) == 2


def test_service_status_provider_reports_failed_unit():
    def runner(command, **kwargs):
        name = command[2]

        if name == "truepanel.service":
            return Result(
                "LoadState=loaded\n"
                "ActiveState=failed\n"
                "SubState=failed\n"
            )

        return Result(
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
        )

    provider = ServiceStatusProvider(
        runner=runner,
        clock=lambda: 100.0,
    )

    payload = provider.snapshot()

    lcd_service = payload["services"][0]

    assert payload["available"] is True
    assert lcd_service["active_state"] == "failed"
    assert lcd_service["sub_state"] == "failed"


def test_service_status_provider_fails_closed_when_systemd_unavailable():
    def runner(command, **kwargs):
        raise OSError("systemctl unavailable")

    provider = ServiceStatusProvider(
        runner=runner,
        clock=lambda: 100.0,
    )

    payload = provider.snapshot()

    assert payload["available"] is False

    assert all(
        service["observed"] is False
        for service in payload["services"]
    )


def test_service_status_provider_caches_observation():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)

        return Result(
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
        )

    times = iter(
        [
            100.0,
            102.0,
        ]
    )

    provider = ServiceStatusProvider(
        runner=runner,
        clock=lambda: next(times),
        cache_seconds=5.0,
    )

    first = provider.snapshot()
    second = provider.snapshot()

    assert first == second

    # Two systemctl calls total, not two calls per browser refresh.
    assert len(calls) == 2


def test_service_status_provider_preserves_partial_observation():
    def runner(command, **kwargs):
        if command[2] == "truepanel.service":
            return Result(
                "LoadState=loaded\n"
                "ActiveState=failed\n"
                "SubState=failed\n"
            )

        raise OSError("status unavailable")

    provider = ServiceStatusProvider(
        runner=runner,
        clock=lambda: 100.0,
    )

    payload = provider.snapshot()

    assert payload["available"] is True
    assert payload["services"][0]["observed"] is True
    assert payload["services"][1]["observed"] is False
