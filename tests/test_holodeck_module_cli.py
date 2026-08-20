import json

from truepanel.holodeck.__main__ import main
from truepanel.holodeck.missions import mission_names


def test_standalone_holodeck_lists_builtin_missions(capsys):
    assert main(["list"]) == 0
    assert tuple(capsys.readouterr().out.splitlines()) == mission_names()


def test_standalone_holodeck_runs_mission_as_json(tmp_path, capsys):
    result = main(
        [
            "run",
            "thermal-ramp",
            "--json",
            "--runtime-dir",
            str(tmp_path / "runtime"),
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == (0 if report["invariants"]["passed"] else 1)
    assert report["mission"] == "thermal-ramp"
    assert report["simulated_seconds"] == 300
    assert report["final"]["cpu_temperature_c"] == 54.0


def test_standalone_holodeck_human_report_is_compact(tmp_path, capsys):
    main(
        [
            "run",
            "network-flap",
            "--runtime-dir",
            str(tmp_path / "runtime"),
        ]
    )
    output = capsys.readouterr().out

    assert "HoloDeck mission: network-flap" in output
    assert "Simulated time: 90.0s" in output
    assert "network=up" in output
    assert "snapshot" not in output
    assert "hostname" not in output
