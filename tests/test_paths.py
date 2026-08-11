from pathlib import Path

from truepanel.paths import (
    installation_root,
)


def test_explicit_installation_root_wins(
    monkeypatch,
    tmp_path,
):
    explicit = tmp_path / "explicit"

    monkeypatch.setenv(
        "TRUEPANEL_ROOT",
        str(tmp_path / "environment"),
    )

    assert installation_root(
        explicit,
    ) == explicit.resolve()


def test_installation_root_uses_environment(
    monkeypatch,
    tmp_path,
):
    root = tmp_path / "environment"

    monkeypatch.setenv(
        "TRUEPANEL_ROOT",
        str(root),
    )

    assert installation_root() == root.resolve()


def test_installation_root_uses_project_tree(
    monkeypatch,
):
    monkeypatch.delenv(
        "TRUEPANEL_ROOT",
        raising=False,
    )

    expected = (
        Path(__file__).resolve().parents[1]
    )

    assert installation_root() == expected
