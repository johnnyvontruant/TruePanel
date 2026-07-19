from pathlib import Path
import re
import tomllib

import truepanel
from truepanel.mission_control.constants import MISSION_CONTROL_VERSION


ROOT = Path(__file__).resolve().parents[1]


def load_pyproject():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def dependency_name(requirement):
    return re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0].strip().lower()


def test_stable_product_version():
    assert truepanel.__version__ == "1.0.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", truepanel.__version__)
    assert MISSION_CONTROL_VERSION == truepanel.__version__


def test_project_metadata_uses_authoritative_version():
    metadata = load_pyproject()

    assert metadata["project"]["name"] == "truepanel"
    assert metadata["project"]["dynamic"] == ["version"]
    assert (
        metadata["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        == "truepanel.__version__"
    )
    assert metadata["project"]["requires-python"] == ">=3.11"


def test_runtime_requirements_match_project_dependencies():
    metadata = load_pyproject()

    project_dependencies = {
        dependency_name(item)
        for item in metadata["project"]["dependencies"]
    }

    runtime_dependencies = {
        dependency_name(line)
        for line in (ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert runtime_dependencies == project_dependencies


def test_release_policy_files_exist():
    required = [
        "CHANGELOG.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "docs/UPGRADING.md",
        "docs/RELEASE.md",
    ]

    for relative_path in required:
        assert (ROOT / relative_path).is_file(), relative_path


def test_documentation_index_exposes_release_guides():
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")

    assert "UPGRADING.md" in index
    assert "RELEASE.md" in index
    assert "../CHANGELOG.md" in index
    assert "../SECURITY.md" in index
    assert "../CONTRIBUTING.md" in index


def test_installer_release_paths_are_consistent():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    uninstaller = (ROOT / "uninstall.sh").read_text(encoding="utf-8")

    assert 'INSTALL_DIR="/opt/truepanel"' in installer
    assert 'BIN_DIR="$INSTALL_DIR/bin"' in installer
    assert 'ExecStart=$BIN_FILE run' in installer

    assert 'INSTALL_DIR="/opt/truepanel"' in uninstaller
    assert 'BIN_FILE="$INSTALL_DIR/bin/truepanel"' in uninstaller
