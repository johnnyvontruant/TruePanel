from pathlib import Path


def test_lcd_fan_page_uses_read_only_host_status_client():
    source = Path(
        "lcd-menu.py"
    ).read_text(encoding="utf-8")

    assert "HostAgentStatusClient" in source
    assert (
        "host_status_client = HostAgentStatusClient()"
        in source
    )

    start = source.index("def show_fan_control():")
    end = source.index("\ndef ", start + 1)
    block = source[start:end]

    assert (
        "host_status_client.read_fan_status("
        in block
    )
    assert "host_agent_runtime" not in block
    assert "host_bootstrap" not in block


def test_status_client_is_independent_of_privileged_bootstrap():
    source = Path(
        "lcd-menu.py"
    ).read_text(encoding="utf-8")

    status_client = source.index(
        "host_status_client = HostAgentStatusClient()"
    )
    main = source.index("def main():")

    assert status_client < main
