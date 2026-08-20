import json

from truepanel.holodeck.__main__ import main
from truepanel.holodeck.missions import mission_names
from truepanel.holodeck.report import (
    run_flight_deck_report,
    run_mission_report,
)


def test_every_builtin_mission_satisfies_terminal_contract(tmp_path):
    for name in mission_names():
        report = run_mission_report(
            name,
            runtime_dir=tmp_path / name,
        )

        assert report["passed"] is True
        assert report["contracts"]["passed"] is True
        assert report["contracts"]["check_count"] == 1
        assert report["contracts"]["checks"][0]["passed"] is True
        assert report["invariants"]["passed"] is True


def test_flight_deck_runs_complete_catalog(tmp_path):
    report = run_flight_deck_report(runtime_dir=tmp_path / "flight-deck")

    assert report["passed"] is True
    assert report["mission_count"] == len(mission_names())
    assert report["passed_count"] == len(mission_names())
    assert report["failed_count"] == 0
    assert report["scenario_event_count"] > report["mission_count"]
    assert [item["mission"] for item in report["missions"]] == list(
        mission_names()
    )
    assert all(item["contracts_passed"] for item in report["missions"])
    assert all(item["invariants_passed"] for item in report["missions"])


def test_flight_deck_cli_emits_machine_readable_summary(tmp_path, capsys):
    result = main(
        [
            "flight-deck",
            "--json",
            "--runtime-dir",
            str(tmp_path / "runtime"),
        ]
    )

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is True
    assert report["mission_count"] == len(mission_names())
    assert report["failed_count"] == 0
    assert "hostname" not in report
    assert "snapshot" not in report
