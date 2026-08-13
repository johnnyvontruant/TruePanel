from pathlib import Path


def test_standalone_construction_is_ready_but_activation_is_locked():
    agent = Path(
        "truepanel/host/agent.py"
    ).read_text(encoding="utf-8")

    assert "build_host_agent_bootstrap(" in agent
    assert "build_host_agent_runtime_from_bootstrap(" in agent
    assert "HostAgentApplicationHooks()" in agent
    assert "STANDALONE_PRODUCTION_ACTIVATED = False" in agent
    assert "require_standalone_activation()" in agent

    main_start = agent.index("def main()")
    process_start = agent.index(
        "process = HostAgentProcess(",
        main_start,
    )
    gate_start = agent.index(
        "require_standalone_activation()",
        main_start,
    )

    assert gate_start < process_start
