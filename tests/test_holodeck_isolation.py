import builtins
import socket
import subprocess
from pathlib import Path

from truepanel.cli import build_parser
from truepanel.holodeck.commands import handle_holodeck_command

PROTECTED_ROOTS = tuple(
    Path(value)
    for value in (
        "/dev",
        "/etc",
        "/proc",
        "/run",
        "/sys",
        "/var",
    )
)


def test_holodeck_run_uses_no_socket_subprocess_or_protected_path(
    monkeypatch,
    capsys,
):
    original_open = builtins.open

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, Path)):
            candidate = Path(file).resolve(strict=False)
            assert not any(
                candidate == root or root in candidate.parents
                for root in PROTECTED_ROOTS
            ), candidate
        return original_open(file, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError(f"forbidden production I/O: {args!r} {kwargs!r}")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)

    args = build_parser().parse_args(
        ["holodeck", "run", "battlestation", "--steps", "1", "--json"]
    )
    assert handle_holodeck_command(args) == 0
    assert capsys.readouterr().out


def test_cli_import_does_not_eagerly_load_holodeck_host_runtime():
    command = (
        "import sys; import truepanel.cli; "
        "assert 'truepanel.holodeck.host_agent' not in sys.modules; "
        "assert 'truepanel.holodeck.runner' not in sys.modules"
    )

    result = subprocess.run(
        [subprocess.sys.executable, "-I", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
