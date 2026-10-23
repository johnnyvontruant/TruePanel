"""Fail-closed activation of read-only Loadmaster telemetry in Mission Control.

ONLY edits the known TruePanel *application* YAML, with exact one-line insert,
root-private backup, service restart, and rollback. No USB/HDD access here.
Live production code must already implement the flight_deck_snapshot_path
setting. Never rewrites other YAML keys or deploys Python into production.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from truepanel.cargo.flightdeck import read_flightdeck

PRODUCTION = Path("/opt/truepanel")
CONFIG = PRODUCTION / "truepanel.yaml"
PROVIDER = PRODUCTION / "truepanel/cargo/provider.py"
ENV_FILE = Path("/etc/default/truepanel-mission-control")
SERVICE = "truepanel-mission-control.service"
STATE = Path("/mnt/SSDs/Applications/Loadmaster-Watchdog-Qualification")
BACKUPS = STATE / "tv-nz-production"
SNAPSHOT = STATE / "flightdeck-tv-nz-production.json"
SETTING = "flight_deck_snapshot_path"
EXPECTED_SETTING = "      flight_deck_snapshot_path: " + str(SNAPSHOT) + "\n"


class ActivationHold(RuntimeError):
    pass


def _private(path: Path) -> None:
    st = path.lstat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != 0
            or st.st_mode & 0o077 or path.is_symlink()):
        raise ActivationHold("root-private state directory required")


def _installed_path_valid() -> None:
    if (PRODUCTION.is_symlink() or CONFIG.is_symlink() or
            not CONFIG.is_file() or PROVIDER.is_symlink() or
            not PROVIDER.is_file()):
        raise ActivationHold("installed TruePanel config/provider path unexpected")
    if SETTING not in PROVIDER.read_text():
        raise ActivationHold("installed Mission Control lacks Flight Deck support")
    if ENV_FILE.exists():
        raw = ENV_FILE.read_text()
        keys = re.findall(r"^TRUEPANEL_MC_CONFIG_PATH=(.*)$", raw, re.M)
        if len(keys) != 1:
            raise ActivationHold("Mission Control config environment ambiguous")
        declared = keys[0].strip().strip("'\"")
        if declared != str(CONFIG):
            raise ActivationHold("Mission Control uses a different config path")


def patched_config(text: str) -> tuple[str, bool]:
    """Simple structural text patch, never serializes or rewrites YAML."""
    if not isinstance(text, str):
        raise ActivationHold("YAML input not text")
    import yaml
    try:
        current = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ActivationHold("invalid current application YAML") from exc
    if not isinstance(current, dict):
        raise ActivationHold("invalid application YAML root")
    loadmaster = (current.get("mission_control", {})
                  .get("cargo_bay", {}).get("loadmaster", {}))
    if not isinstance(loadmaster, dict) or loadmaster.get("enabled") is not True:
        raise ActivationHold("Mission Control Loadmaster not enabled in YAML")
    existing = loadmaster.get(SETTING)
    if existing is not None:
        if existing != str(SNAPSHOT):
            raise ActivationHold("another Flight Deck source configured")
        return text, False
    if SETTING in text:
        # Refuse comments/unexpected duplicates instead of guessing.
        raise ActivationHold("Flight Deck setting already mentioned ambiguously")
    lines = text.splitlines(keepends=True)
    occurrences = [index for index,line in enumerate(lines)
                   if line.rstrip("\r\n") == "    loadmaster:"]
    if len(occurrences) != 1:
        raise ActivationHold("cannot locate unique exact Loadmaster YAML block")
    lines.insert(occurrences[0] + 1, EXPECTED_SETTING)
    next_text = "".join(lines)
    try:
        parsed = yaml.safe_load(next_text)
    except yaml.YAMLError as exc:
        raise ActivationHold("patched YAML invalid") from exc
    import copy
    expected = copy.deepcopy(current)
    expected["mission_control"]["cargo_bay"]["loadmaster"][SETTING] = str(SNAPSHOT)
    if parsed != expected:
        raise ActivationHold("patch changed unrelated TruePanel settings")
    return next_text, True


def _atomic_replace(path: Path, data: bytes, *, st: os.stat_result) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".loadmaster-config-", dir=path.parent)
    temp = Path(temp_name)
    try:
        os.fchown(fd, st.st_uid, st.st_gid)
        os.fchmod(fd, stat.S_IMODE(st.st_mode))
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if temp.exists():
            temp.unlink()


def _restart_healthy() -> None:
    subprocess.run(
        ["systemctl", "restart", SERVICE], timeout=35, check=True,
        capture_output=True, text=True)
    for _ in range(15):
        state = subprocess.run(
            ["systemctl", "is-active", SERVICE],
            capture_output=True, text=True, timeout=8)
        if state.returncode == 0 and state.stdout.strip() == "active":
            # Give the process time to initialize before calling it healthy.
            time.sleep(1)
            second = subprocess.run(
                ["systemctl", "is-active", SERVICE],
                capture_output=True, text=True, timeout=8)
            if second.returncode == 0 and second.stdout.strip() == "active":
                return
        time.sleep(.3)
    raise ActivationHold("Mission Control did not remain active after restart")


def activate(*, apply: bool = False) -> dict:
    """Inspect always; commit only when apply=True and all prechecks pass."""
    if os.geteuid() != 0:
        raise ActivationHold("root required for Mission Control config")
    _private(STATE)
    _private(BACKUPS)
    if read_flightdeck(SNAPSHOT).get("state") != "READY":
        raise ActivationHold("authenticated SSD Flight Deck snapshot invalid")
    _installed_path_valid()
    before = CONFIG.read_bytes()
    st = CONFIG.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise ActivationHold("configuration is not a regular file")
    new_text, changed = patched_config(before.decode("utf-8"))
    if not apply:
        return {
            "state": "LOADMASTER_UI_ACTIVATION_PREFLIGHT",
            "ready": True, "would_update_config": changed,
            "would_restart_service": changed,
            "physical_authorized": False,
        }
    if not changed:
        return {
            "state": "LOADMASTER_UI_ALREADY_CONNECTED",
            "config_changed": False, "service_restarted": False,
            "physical_authorized": False,
        }
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = BACKUPS / ("mission-control-config-" + stamp + ".yaml")
    if backup.exists() or backup.is_symlink():
        raise ActivationHold("config backup collision")
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(before)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    try:
        _atomic_replace(CONFIG, new_text.encode("utf-8"), st=st)
        _restart_healthy()
    except BaseException as exc:
        try:
            _atomic_replace(CONFIG, before, st=st)
            _restart_healthy()
        except BaseException as restore_error:
            raise ActivationHold(
                "CRITICAL: Mission Control YAML or service rollback unverified") from restore_error
        raise ActivationHold("UI activation failed; original config restored") from exc
    return {
        "state": "LOADMASTER_UI_CONNECTED",
        "config_changed": True,
        "service_restarted": True,
        "backup_path": str(backup),
        "snapshot_path": str(SNAPSHOT),
        "physical_authorized": False,
    }
