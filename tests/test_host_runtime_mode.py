from pathlib import Path

from truepanel.host.mode import (
    HostRuntimeMode,
    resolve_host_runtime_mode,
)


def test_marker_absent_selects_embedded_mode(tmp_path):
    marker = tmp_path / "standalone-host-agent.enabled"

    assert (
        resolve_host_runtime_mode(marker_path=marker)
        is HostRuntimeMode.EMBEDDED
    )


def test_marker_present_selects_external_mode(tmp_path):
    marker = tmp_path / "standalone-host-agent.enabled"
    marker.write_text("armed\n", encoding="utf-8")

    assert (
        resolve_host_runtime_mode(marker_path=marker)
        is HostRuntimeMode.EXTERNAL
    )


def test_mode_resolver_is_strictly_passive():
    source = Path(
        "truepanel/host/mode.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        ".write_text(",
        ".touch(",
        ".mkdir(",
        ".unlink(",
        "os.remove(",
        "subprocess",
        "systemctl",
        "HostOwnershipGuard",
        "flock",
    ):
        assert forbidden not in source
