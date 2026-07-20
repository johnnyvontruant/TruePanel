from truepanel.cli import build_parser


def test_mission_control_command_is_registered():
    parser = build_parser()
    args = parser.parse_args(
        ["mission-control", "status"]
    )

    assert args.command == "mission-control"
    assert (
        args.mission_control_action
        == "status"
    )


def test_mission_control_defaults_to_status():
    parser = build_parser()
    args = parser.parse_args(
        ["mission-control"]
    )

    assert args.command == "mission-control"
    assert args.mission_control_action is None


def test_mission_control_actions_are_registered():
    parser = build_parser()

    for action in (
        "status",
        "start",
        "stop",
        "restart",
        "logs",
    ):
        args = parser.parse_args(
            ["mission-control", action]
        )

        assert (
            args.mission_control_action
            == action
        )
