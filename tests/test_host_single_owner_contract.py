from pathlib import Path


def test_host_runtime_acquires_owner_before_privileged_fan_server():
    source = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")

    start = source.index("    def start(self) -> None:")
    end = source.index("    def shutdown(self) -> None:", start)
    block = source[start:end]

    acquire = block.index("self._ownership_guard.acquire()")
    fan_factory = block.index("self._fan_server_factory()")

    assert acquire < fan_factory
    assert "lcd_server" not in block
    assert "lcd_command" not in block


def test_host_runtime_restores_before_releasing_owner():
    source = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")

    start = source.index("    def shutdown(self) -> None:")
    block = source[start:]

    restore = block.index("self._fan_runtime.shutdown()")
    release = block.index("self._ownership_guard.release()")

    assert restore < release


def test_embedded_and_standalone_use_distinct_owner_names():
    factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")
    agent = Path(
        "truepanel/host/agent.py"
    ).read_text(encoding="utf-8")

    assert 'owner_name: str = "embedded-lcd"' in factory
    assert 'owner_name="standalone-host-agent"' in agent
    assert "STANDALONE_PRODUCTION_ACTIVATED = False" in agent
