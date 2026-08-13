from pathlib import Path


def test_lcd_shutdown_never_bypasses_host_ownership():
    source = Path(
        "lcd-menu.py"
    ).read_text(encoding="utf-8")

    assert "host_agent_runtime.shutdown()" in source
    assert "host_bootstrap.fan_runtime.shutdown()" not in source
    assert (
        "skipping fan-runtime shutdown without ownership"
        in source
    )


def test_bootstrap_construction_is_non_actuating():
    bootstrap = Path(
        "truepanel/host/bootstrap.py"
    ).read_text(encoding="utf-8")
    executor = Path(
        "truepanel/hardware/fan_executor.py"
    ).read_text(encoding="utf-8")

    build_start = bootstrap.index(
        "def build_host_agent_bootstrap("
    )
    build_block = bootstrap[build_start:]

    assert "fan_runtime_factory(" in build_block
    assert "Construction never grants hardware authority" in build_block

    init_start = executor.index("    def __init__(")
    init_end = executor.index("    @staticmethod", init_start)
    init_block = executor[init_start:init_end]

    assert "self._validate_surface()" in init_block
    assert "self._capture_original_state()" in init_block
    assert "self.writer(" not in init_block
