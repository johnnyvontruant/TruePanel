from pathlib import Path


def test_lcd_primes_host_cycle_without_reconciliation_before_start():
    source = Path("lcd-menu.py").read_text(encoding="utf-8")
    main = source[source.index("def main():"):]

    prime = main.index(
        "host_agent_runtime.service_cycle(\n"
        "            reconcile=False"
    )
    start = main.index("host_agent_runtime.start()")

    assert prime < start


def test_lcd_main_loop_delegates_periodic_host_work_to_runtime():
    source = Path("lcd-menu.py").read_text(encoding="utf-8")
    main = source[source.index("def main():"):]

    loop_start = main.index("while not shutdown_requested:")
    loop_end = main.index("delay = 5", loop_start)
    loop = main[loop_start:loop_end]

    assert "host_agent_runtime.service_cycle()" in loop
    assert "reconcile_fan_control()" not in loop
    assert "observe_thermal_fan_policy()" not in loop
    assert "publish_fan_control_status()" not in loop
