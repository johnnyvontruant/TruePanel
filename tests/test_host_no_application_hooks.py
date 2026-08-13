import inspect
from pathlib import Path

import truepanel.host as host
from truepanel.host import factory


def test_host_package_exposes_no_application_hook_type():
    assert not hasattr(
        host,
        "HostAgentApplicationHooks",
    )


def test_host_contracts_contain_only_privileged_services():
    hooks = Path(
        "truepanel/host/hooks.py"
    ).read_text(encoding="utf-8")

    assert "HostAgentSafetyServices" in hooks
    assert "HostAgentApplicationHooks" not in hooks
    assert "LCDButtonHandler" not in hooks
    assert "lcd_button_handler" not in hooks


def test_host_factories_accept_no_application_callback_surface():
    factory_source = Path(
        "truepanel/host/factory.py"
    ).read_text(encoding="utf-8")
    runtime_source = Path(
        "truepanel/host/runtime.py"
    ).read_text(encoding="utf-8")

    assert "application_hooks" not in factory_source
    assert "lcd_button_handler" not in factory_source
    assert "LCDCommand" not in factory_source
    assert "lcd_command" not in runtime_source
    assert "lcd_server" not in runtime_source

    direct = inspect.signature(
        factory.build_host_agent_runtime
    )
    bootstrap = inspect.signature(
        factory.build_host_agent_runtime_from_bootstrap
    )

    assert "application_hooks" not in direct.parameters
    assert "application_hooks" not in bootstrap.parameters
