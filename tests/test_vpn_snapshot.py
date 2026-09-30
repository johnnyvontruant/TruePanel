from truepanel.web.snapshot import SnapshotService


class FakeVpnProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def snapshot(self):
        if self.error is not None:
            raise self.error

        return dict(self.payload)


def service_with(provider):
    service = SnapshotService.__new__(
        SnapshotService
    )

    service.cargo_provider = None
    service.vpn_status_provider = provider

    return service


def test_snapshot_includes_vpn_payload():
    expected = {
        "read_only": True,
        "label": "ExpressVPN",
        "state": "CONNECTED",
        "tone": "good",
        "connected": True,
    }

    service = service_with(
        FakeVpnProvider(expected)
    )

    payload = service._with_cargo_bay(
        {
            "schema_version": 1,
            "read_only": True,
        }
    )

    assert payload["vpn"] == expected


def test_snapshot_falls_back_when_vpn_probe_fails():
    service = service_with(
        FakeVpnProvider(
            error=RuntimeError(
                "probe failed"
            )
        )
    )

    payload = service._with_cargo_bay(
        {
            "schema_version": 1,
            "read_only": True,
        }
    )

    vpn = payload["vpn"]

    assert vpn["read_only"] is True
    assert vpn["state"] == "UNAVAILABLE"
    assert vpn["tone"] == "neutral"
    assert vpn["connected"] is False
