import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from truepanel.lab.commands import (
    build_parser,
    main,
    run_fingerprint,
)


@dataclass
class FakeLatency:
    count: int = 3
    minimum_ms: float = 50.1
    average_ms: float = 50.4
    median_ms: float = 50.4
    maximum_ms: float = 50.7


@dataclass
class FakeDiscoveryReport:
    board_id: int | None = 0x007D
    protocol_version: int | None = 0x0100
    button_status: int | None = 0x0000
    successes: int = 3
    failures: int = 0
    healthy: bool = True

    def __post_init__(self):
        self.results = [object(), object(), object()]
        self.latency = FakeLatency()


@contextmanager
def fake_open_controller(*args, **kwargs):
    yield object(), Path(
        "development/logs/fake_fingerprint.log"
    )


def test_parser_accepts_live_fingerprint():
    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )

    assert args.lab_command == "fingerprint"
    assert args.live is True


def test_baseline_fingerprint_does_not_open_hardware(
    monkeypatch,
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("hardware should not be opened")

    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fail_if_called,
    )

    args = build_parser().parse_args(["fingerprint"])
    result = run_fingerprint(args)

    assert result.success is True
    assert result.data["board_id"] is None
    assert result.data["metadata"].get("acquisition_mode") != "live"


def test_live_fingerprint_populates_identity_and_timing(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.commands.run_discovery",
        lambda controller, probe_callback=None: FakeDiscoveryReport(),
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live", "--json"]
    )
    result = run_fingerprint(args)

    assert result.success is True
    assert result.data["board_id"] == "0x007D"
    assert result.data["firmware_version"] == "0x0100"
    assert (
        result.data["timing"]["average_latency_ms"]
        == pytest.approx(50.4)
    )
    assert result.data["confidence"] == pytest.approx(1.0)


def test_live_fingerprint_records_capture_metadata(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.commands.run_discovery",
        lambda controller, probe_callback=None: FakeDiscoveryReport(),
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )
    result = run_fingerprint(args)
    metadata = result.data["metadata"]

    assert metadata["acquisition_mode"] == "live"
    assert metadata["discovery_successes"] == 3
    assert metadata["discovery_failures"] == 0
    assert metadata["discovery_probe_count"] == 3
    assert metadata["discovery_healthy"] is True
    assert metadata["capture_path"].endswith(
        "fake_fingerprint.log"
    )


def test_live_fingerprint_verifies_capabilities(
    monkeypatch,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.commands.run_discovery",
        lambda controller, probe_callback=None: FakeDiscoveryReport(),
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )
    result = run_fingerprint(args)
    capabilities = result.data["capabilities"]

    assert capabilities["board_query"]["state"] == "supported"
    assert capabilities["board_query"]["confidence"] == 1.0
    assert capabilities["version_query"]["confidence"] == 1.0
    assert capabilities["button_query"]["confidence"] == 1.0


def test_live_missing_response_marks_capability_unknown(
    monkeypatch,
):
    report = FakeDiscoveryReport(
        protocol_version=None,
        successes=2,
        failures=1,
        healthy=False,
    )

    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.commands.run_discovery",
        lambda controller, probe_callback=None: report,
    )

    args = build_parser().parse_args(
        ["fingerprint", "--live"]
    )
    result = run_fingerprint(args)

    assert result.data["firmware_version"] is None
    assert (
        result.data["capabilities"]["version_query"]["state"]
        == "unknown"
    )
    assert result.data["metadata"]["discovery_failures"] == 1


def test_main_outputs_live_json_without_second_probe(
    monkeypatch,
    capsys,
):
    calls = {"count": 0}

    def fake_discovery(controller, probe_callback=None):
        calls["count"] += 1
        return FakeDiscoveryReport()

    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.commands.run_discovery",
        fake_discovery,
    )

    exit_code = main(
        ["fingerprint", "--live", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls["count"] == 1
    assert payload["board_id"] == "0x007D"
    assert payload["firmware_version"] == "0x0100"
    assert payload["metadata"]["acquisition_mode"] == "live"


def test_main_outputs_live_human_fingerprint(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.open_controller",
        fake_open_controller,
    )
    monkeypatch.setattr(
        "truepanel.lab.commands.run_discovery",
        lambda controller, probe_callback=None: FakeDiscoveryReport(),
    )

    exit_code = main(["fingerprint", "--live"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Board ID   : 0x007D" in output
    assert "Firmware   : 0x0100" in output
    assert "Latency    : 50.400 ms" in output
    assert "Confidence : 100.0%" in output
