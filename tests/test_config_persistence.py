from pathlib import Path

import yaml

from truepanel.config.persistence import (
    ConfigurationPersistenceService,
)


def initial_config():
    return {
        "flightdeck": {
            "rotation_interval": 5,
            "night_mode": {
                "enabled": True,
                "idle_after": 1800,
                "rotation_interval": 60,
                "suppress_info": True,
                "dashboard_pages": [
                    "home",
                    "storage",
                    "capacity",
                ],
                "backlight_off": True,
                "wake_on_button": True,
                "allow_warning_alerts": True,
                "allow_critical_alerts": True,
            },
        },
        "history": {
            "enabled": True,
        },
    }


def write_config(path: Path):
    path.write_text(
        yaml.safe_dump(
            initial_config(),
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_dry_run_never_writes_or_backs_up(tmp_path):
    config_path = tmp_path / "truepanel.yaml"
    write_config(config_path)
    original = config_path.read_text(encoding="utf-8")

    service = ConfigurationPersistenceService(
        config_path,
        initial_config(),
        clock=lambda: 100.0,
    )

    result = service.save_night_mode(
        {
            "idle_after": 3600,
        },
        dry_run=True,
    )

    assert result.changed is True
    assert result.persisted is False
    assert result.dry_run is True
    assert result.backup_path is None
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("*.backup-*"))


def test_save_creates_backup_and_atomic_yaml(tmp_path):
    config_path = tmp_path / "truepanel.yaml"
    write_config(config_path)
    original = config_path.read_text(encoding="utf-8")

    service = ConfigurationPersistenceService(
        config_path,
        initial_config(),
        clock=lambda: 100.0,
    )

    result = service.save_night_mode(
        {
            "idle_after": 3600,
            "rotation_interval": 90,
        }
    )

    assert result.persisted is True
    assert result.changed_fields == (
        "idle_after",
        "rotation_interval",
    )

    backup_path = Path(result.backup_path)
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == original

    payload = yaml.safe_load(
        config_path.read_text(encoding="utf-8")
    )
    night_mode = payload["flightdeck"]["night_mode"]

    assert night_mode["idle_after"] == 3600
    assert night_mode["rotation_interval"] == 90
    assert payload["history"]["enabled"] is True


def test_no_change_does_not_write_or_backup(tmp_path):
    config_path = tmp_path / "truepanel.yaml"
    write_config(config_path)
    original = config_path.read_text(encoding="utf-8")

    service = ConfigurationPersistenceService(
        config_path,
        initial_config(),
    )

    result = service.save_night_mode(
        {
            "idle_after": 1800,
        }
    )

    assert result.changed is False
    assert result.persisted is False
    assert result.backup_path is None
    assert config_path.read_text(encoding="utf-8") == original


def test_service_updates_its_in_memory_config_after_save(tmp_path):
    config_path = tmp_path / "truepanel.yaml"
    write_config(config_path)

    service = ConfigurationPersistenceService(
        config_path,
        initial_config(),
    )

    service.save_night_mode(
        {
            "idle_after": 3600,
        }
    )

    preview = service.preview_night_mode(
        {
            "idle_after": 3600,
        }
    )

    assert preview.changed is False


def test_save_preserves_existing_file_mode(tmp_path):
    config_path = tmp_path / "truepanel.yaml"
    write_config(config_path)
    config_path.chmod(0o640)

    service = ConfigurationPersistenceService(
        config_path,
        initial_config(),
    )

    service.save_night_mode(
        {
            "rotation_interval": 90,
        }
    )

    assert (
        config_path.stat().st_mode & 0o777
    ) == 0o640
