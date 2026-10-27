"""Smoke test a staged tree with the deployment's own Python.

Staging byte-compiles the stage, which finds syntax errors but not a module
that fails to import or a setting the new code rejects. The deployment's
virtualenv has no pytest, so this runs a few checks that need nothing extra:

* import every module in ``truepanel`` and ``qnaplcd`` from the stage;
* load the deployed ``truepanel.yaml`` (copied into the stage) with the new
  code, including Loadmaster's settings validation;
* plan a tiny drive, as a sanity check of the sync planner.

Run as ``python -B -P -c "...smoke.main()" STAGE CONFIG`` so only the stage's
code is imported; it prints one line per problem and exits 1 if any.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

PACKAGES = ("truepanel", "qnaplcd")


def check(stage: Path, config_path: Path) -> list[str]:
    problems: list[str] = []
    stage = stage.resolve()

    for package_name in PACKAGES:
        try:
            package = importlib.import_module(package_name)
        except Exception as error:  # noqa: BLE001 - every failure is a finding
            problems.append(f"import {package_name}: {type(error).__name__}: {error}")
            continue
        origin = Path(package.__file__).resolve()
        if stage not in origin.parents:
            problems.append(f"{package_name} was imported from {origin}, not the stage")
            continue
        for info in pkgutil.walk_packages(package.__path__, f"{package_name}."):
            if info.name.rsplit(".", 1)[-1] == "__main__":
                continue
            try:
                importlib.import_module(info.name)
            except Exception as error:  # noqa: BLE001
                problems.append(f"import {info.name}: {type(error).__name__}: {error}")

    try:
        from truepanel.config.loader import load_config
        from truepanel.loadmaster import load_settings

        load_settings(load_config(str(config_path)))
    except Exception as error:  # noqa: BLE001
        problems.append(f"config {config_path}: {type(error).__name__}: {error}")

    try:
        from truepanel.loadmaster.plan import build_plan
        from truepanel.loadmaster.scan import Fingerprint

        plan = build_plan(
            drive_name="smoke",
            nas={"Show/S01E01.mkv": Fingerprint(1, 0)},
            usb={"Show/S01E02.mkv": Fingerprint(2, 0)},
            record=None,
        )
        if [a["op"] for a in plan["actions"]] != ["to_usb", "to_nas"]:
            problems.append(f"planner sanity check failed: {plan['actions']}")
    except Exception as error:  # noqa: BLE001
        problems.append(f"planner: {type(error).__name__}: {error}")

    return problems


def main() -> None:
    stage, config_path = Path(sys.argv[1]), Path(sys.argv[2])
    sys.path.insert(0, str(stage))
    problems = check(stage, config_path)
    for problem in problems:
        print(problem, file=sys.stderr)
    sys.exit(1 if problems else 0)


def command(python: Path, stage: Path, config_path: Path) -> list[str]:
    """The command staging runs (stage first on sys.path, no bytecode)."""

    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from truepanel.upgrade.smoke import main; main()"
    )
    return [str(python), "-B", "-P", "-c", code, str(stage), str(config_path)]


__all__ = ["check", "command", "main"]
