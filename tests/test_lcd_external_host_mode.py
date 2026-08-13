from pathlib import Path


def source():
    return Path("lcd-menu.py").read_text(encoding="utf-8")


def test_lcd_resolves_host_mode_before_bootstrap_construction():
    text = source()

    mode = text.index(
        "host_runtime_mode = resolve_host_runtime_mode()"
    )
    bootstrap = text.index(
        "host_bootstrap = ("
    )

    assert mode < bootstrap
    assert (
        "if host_runtime_mode is HostRuntimeMode.EMBEDDED"
        in text[bootstrap:bootstrap + 240]
    )


def test_external_mode_skips_embedded_host_construction_and_cycle():
    text = source()
    main = text[text.index("def main():"):]

    construction = main.index(
        "if host_bootstrap is not None:"
    )
    lcd_server = main.index(
        "lcd_command_server = build_lcd_command_server("
    )

    assert construction < lcd_server

    loop_start = main.index("while not shutdown_requested:")
    loop_end = main.index("publish_lcd_reader_status()", loop_start)
    loop = main[loop_start:loop_end]

    assert "if host_agent_runtime is not None:" in loop
    assert "host_agent_runtime.service_cycle()" in loop


def test_external_mode_never_falls_back_to_bootstrap_status_publication():
    text = source()
    start = text.index("def publish_fan_control_status(")
    end = text.index("\ndef ", start + 1)
    block = text[start:end]

    assert "if host_bootstrap is None:" in block
    assert "return None" in block


def test_external_mode_shutdown_is_non_privileged():
    text = source()
    main = text[text.index("def main():"):]
    shutdown = main[main.index("finally:"):]

    assert (
        "elif host_runtime_mode is HostRuntimeMode.EMBEDDED:"
        in shutdown
    )
    assert "External Host runtime mode active;" in shutdown
    assert "embedded shutdown skipped." in shutdown
