from truepanel.config.loader import load_config


def test_minimal_config_uses_safe_buzzer_defaults(
    tmp_path,
):
    config_path = tmp_path / "truepanel.yaml"
    config_path.write_text(
        "theme_pack: default\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["buzzer"]["enabled"] is False
    assert config["buzzer"]["backend"] == "pcspkr"


def test_explicit_buzzer_settings_override_safe_defaults(
    tmp_path,
):
    config_path = tmp_path / "truepanel.yaml"
    config_path.write_text(
        (
            "theme_pack: default\n"
            "\n"
            "buzzer:\n"
            "  enabled: true\n"
            "  backend: terminal\n"
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["buzzer"]["enabled"] is True
    assert config["buzzer"]["backend"] == "terminal"
