"""Packaging contract for TruePanel's pyserial dependency."""

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _normalized_dependency_name(requirement: str) -> str:
    """Return a normalized distribution name from a requirement string."""
    name = re.split(r"[<>=!~;\[\]\s]", requirement, maxsplit=1)[0]

    return re.sub(
        r"[-_.]+",
        "-",
        name,
    ).lower()


def test_repository_does_not_vendor_serial_package():
    """TruePanel must use installed pyserial, not shadow it locally."""
    assert not (PROJECT_ROOT / "serial").exists(), (
        "A top-level serial/ directory would shadow the installed "
        "pyserial distribution."
    )

    assert not (PROJECT_ROOT / "serial.py").exists(), (
        "A top-level serial.py module would shadow the installed "
        "pyserial distribution."
    )


def test_pyserial_is_an_explicit_runtime_dependency():
    """The project must install pyserial through package metadata."""
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(
            encoding="utf-8",
        )
    )

    dependencies = pyproject["project"].get(
        "dependencies",
        [],
    )

    normalized_names = {
        _normalized_dependency_name(requirement)
        for requirement in dependencies
    }

    assert "pyserial" in normalized_names, (
        "pyserial must remain an explicit project dependency."
    )


def test_imported_serial_exposes_pyserial_contract():
    """The test environment must resolve a supported pyserial package."""
    import serial

    assert serial.__file__ is not None
    assert callable(getattr(serial, "Serial", None))

    version = getattr(serial, "__version__", None)

    assert version is not None

    version_parts = tuple(
        int(part)
        for part in version.split(".")[:2]
    )

    assert version_parts >= (3, 5)
