import re
import tomllib
from pathlib import Path

import truepanel
from truepanel.mission_control.constants import MISSION_CONTROL_VERSION

ROOT = Path(__file__).resolve().parents[1]


def load_pyproject():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def dependency_name(requirement):
    return re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0].strip().lower()


def test_release_candidate_product_version():
    assert truepanel.__version__ == "1.2.0rc2"
    assert re.fullmatch(
        r"\d+\.\d+\.\d+rc\d+",
        truepanel.__version__,
    )
    assert truepanel.__version__ == MISSION_CONTROL_VERSION


def test_release_policy_documents_candidate_and_stable_versions():
    release = (ROOT / "docs" / "RELEASE.md").read_text(
        encoding="utf-8",
    )

    assert "X.Y.ZrcN" in release
    assert "vX.Y.Z-rcN" in release
    assert "vX.Y.Z" in release
    assert "no prerelease suffix" in release


def test_project_metadata_uses_authoritative_version():
    metadata = load_pyproject()

    assert metadata["project"]["name"] == "truepanel"
    assert metadata["project"]["version"] == truepanel.__version__
    assert "dynamic" not in metadata["project"]
    assert "dynamic" not in metadata["tool"]["setuptools"]
    assert metadata["project"]["requires-python"] == ">=3.11"
    assert metadata["project"]["scripts"] == {
        "truepanel": "truepanel.cli:main"
    }


def test_ci_smokes_installed_wheel_outside_source_checkout():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    smoke = ROOT / "development" / "tools" / "smoke_installed_wheel.py"

    assert "installed-wheel-smoke:" in workflow
    assert "python -m build --wheel" in workflow
    assert "cd \"$RUNNER_TEMP\"" in workflow
    assert "smoke_installed_wheel.py" in workflow
    assert smoke.is_file()



def test_pytest_collection_is_scoped_to_canonical_suite():
    metadata = load_pyproject()

    assert (
        metadata["tool"]["pytest"]["ini_options"]["testpaths"]
        == ["tests"]
    )

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

    for source in (
        installer,
        uninstaller,
    ):
        assert "TRUEPANEL_INSTALL_ROOT" in source
        assert "--root" in source
        assert (
            "systemctl show truepanel.service"
            in source
        )
        assert "/opt/truepanel" not in source

    assert 'BIN_DIR="$INSTALL_DIR/bin"' in installer
    assert 'ExecStart=$BIN_FILE run' in installer

    assert (
        'BIN_FILE="$INSTALL_DIR/bin/truepanel"'
        in uninstaller
    )

def test_production_entrypoints_compile():
    entrypoints = (
        "truepanel.py",
        "collector.py",
        "lcd-menu.py",
    )

    for relative_path in entrypoints:
        candidate = ROOT / relative_path

        source = candidate.read_text(
            encoding="utf-8",
        )

        compile(
            source,
            str(candidate),
            "exec",
        )
