from truepanel.web.snapshot import SnapshotService


class CargoProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = 0

    def snapshot(self):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.payload


def service_with(provider):
    service = object.__new__(SnapshotService)
    service.cargo_provider = provider
    return service


def test_cargo_bay_attaches_provider_payload():
    cargo = {
        "schema_version": 1,
        "read_only": True,
        "state": "NOMINAL",
        "window_seconds": 86400,
        "summary": {
            "total": 5,
            "tv": 3,
            "movies": 2,
            "resolved": 5,
            "unresolved": 0,
            "moved_since_import": 1,
            "total_bytes": 123,
        },
        "backup": {
            "tracking": False,
            "state": "NOT_TRACKED",
        },
        "groups": {
            "tv": [],
            "movies": [],
        },
    }

    provider = CargoProvider(payload=cargo)
    service = service_with(provider)

    payload = service._with_cargo_bay(
        {
            "schema_version": 1,
            "read_only": True,
            "system": {"hostname": "BattleStation"},
        }
    )

    assert payload["cargo_bay"] == cargo
    assert payload["system"]["hostname"] == "BattleStation"
    assert provider.calls == 1


def test_missing_cargo_provider_is_unavailable():
    service = service_with(None)

    cargo = service._cargo_bay_payload()

    assert cargo["state"] == "UNAVAILABLE"
    assert cargo["read_only"] is True
    assert cargo["summary"]["total"] == 0
    assert cargo["groups"] == {
        "tv": [],
        "movies": [],
    }


def test_cargo_failure_does_not_escape_snapshot_boundary():
    provider = CargoProvider(
        error=OSError("Sonarr unavailable")
    )
    service = service_with(provider)

    payload = service._with_cargo_bay(
        {
            "schema_version": 1,
            "read_only": True,
            "system": {"hostname": "BattleStation"},
        }
    )

    assert payload["system"]["hostname"] == "BattleStation"
    assert payload["cargo_bay"]["state"] == "UNAVAILABLE"
    assert payload["cargo_bay"]["summary"]["total"] == 0
    assert provider.calls == 1


def test_invalid_cargo_payload_is_unavailable():
    provider = CargoProvider(payload=["not", "a", "dict"])
    service = service_with(provider)

    cargo = service._cargo_bay_payload()

    assert cargo["state"] == "UNAVAILABLE"
