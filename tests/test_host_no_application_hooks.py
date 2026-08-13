from pathlib import Path

import truepanel.host as host


def test_host_package_exposes_no_application_hook_type():
    assert not hasattr(
        host,
        "HostAgentApplicationHooks",
    )


def test_host_contracts_contain_only_privileged_services():
    hooks = Path(
        "truepanel/host/hooks.py"
    ).read_text(encoding="utf-8")
    package = Path(
        "truepanel/host/__init__.py"
    ).read_text(encoding="utf-8")
    factory = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")
    runtime = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")

    assert "HostAgentSafetyServices" in hooks
    assert "HostAgentApplicationHooks" not in hooks
    assert "LCDButtonHandler" not in hooks
    assert "lcd_button_handler" not in hooks

    assert "HostAgentApplicationHooks" not in package
    assert "application_hooks" not in factory
    assert "lcd_button_handler" not in factory
    assert "lcd_command" not in runtime
    assert "lcd_server" not in runtime
