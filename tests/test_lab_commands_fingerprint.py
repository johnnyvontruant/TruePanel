import json

from truepanel.lab.commands import (
    build_parser,
    main,
    run_fingerprint,
)


def test_parser_accepts_fingerprint_command():
    args = build_parser().parse_args(["fingerprint"])

    assert args.lab_command == "fingerprint"
    assert args.handler is run_fingerprint
    assert args.json_output is False
    assert args.compact is False


def test_parser_accepts_json_after_fingerprint_command():
    args = build_parser().parse_args(
        ["fingerprint", "--json"]
    )

    assert args.lab_command == "fingerprint"
    assert args.json_output is True
    assert args.compact is False


def test_parser_accepts_global_json_before_command():
    args = build_parser().parse_args(
        ["--json", "fingerprint"]
    )

    assert args.lab_command == "fingerprint"
    assert args.json_output is True


def test_parser_accepts_compact_output():
    args = build_parser().parse_args(
        ["fingerprint", "--compact"]
    )

    assert args.compact is True


def test_run_fingerprint_returns_canonical_payload():
    args = build_parser().parse_args(["fingerprint"])
    result = run_fingerprint(args)

    assert result.success is True
    assert result.command == "fingerprint"
    assert result.value == "A125"
    assert result.data["controller_family"] == "A125"
    assert result.data["transport"]["serial_port"] == "/dev/ttyS1"
    assert result.data["transport"]["baud_rate"] == 1200
    assert result.data["transport"]["protocol_preamble"] == 0x4D


def test_main_prints_human_fingerprint(capsys):
    exit_code = main(["fingerprint"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Project Stargate Fingerprint" in output
    assert "Controller : A125" in output
    assert "Port       : /dev/ttyS1" in output
    assert "Preamble   : 0x4D" in output
    assert "[+] Board Query [supported]" in output


def test_main_prints_json_fingerprint(capsys):
    exit_code = main(["fingerprint", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert payload["controller_family"] == "A125"
    assert payload["transport"]["serial_port"] == "/dev/ttyS1"
    assert payload["capabilities"]["board_query"]["state"] == "supported"
    assert "command" not in payload


def test_main_prints_compact_json(capsys):
    exit_code = main(["fingerprint", "--compact"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "\n" not in output.rstrip("\n")

    payload = json.loads(output)
    assert payload["controller_family"] == "A125"


def test_existing_status_command_still_uses_lab_result_output(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "truepanel.lab.commands.service_is_active",
        lambda: False,
    )

    exit_code = main(["status"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Command: status" in output
    assert "Status: PASS" in output
    assert "Serial port available" in output
