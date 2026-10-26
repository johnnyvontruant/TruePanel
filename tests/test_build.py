from __future__ import annotations

import subprocess

from truepanel.build import BUILD_FILE, describe, read_build, source_build, write_build
from truepanel.verify.checks import check_build


def git(repo, *args):
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=T",
            "-c",
            "user.email=t@example.com",
            *args,
        ],
        check=True,
        capture_output=True,
    )


def make_repo(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "truepanel.py").write_text("print('hi')\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def test_source_build_describes_a_checkout(tmp_path):
    repo = make_repo(tmp_path)
    build = source_build(repo)
    assert len(build["commit"]) == 40
    assert build["branch"] == "main" and build["dirty"] is False
    assert build["committed_at"][:4].isdigit()

    (repo / "truepanel.py").write_text("print('changed')\n")
    assert source_build(repo)["dirty"] is True
    (repo / "untracked.txt").write_text("x")  # untracked files do not count
    git(repo, "checkout", "-q", "--", "truepanel.py")
    assert source_build(repo)["dirty"] is False

    assert source_build(tmp_path / "not-a-repo") == {}


def test_stage_stamp_round_trip_and_description(tmp_path):
    repo = make_repo(tmp_path)
    stage = tmp_path / "stage"
    stage.mkdir()
    build = write_build(stage, repo)
    assert (stage / BUILD_FILE).is_file()
    assert read_build(stage) == build
    text = describe(build)
    assert text.startswith(build["commit"][:7] + " (main, ")
    assert describe({**build, "dirty": True}).endswith("with uncommitted changes")
    assert describe({"commit": "abcdef1234", "branch": "HEAD"}) == "abcdef1"
    assert describe(None) == "not recorded"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert write_build(empty, tmp_path / "not-a-repo") == {}
    assert read_build(empty) is None


def test_verify_reports_the_deployed_build(tmp_path):
    root = tmp_path / "deployed"
    root.mkdir()
    assert check_build(root)["status"] == "WARN"

    repo = make_repo(tmp_path)
    build = write_build(root, repo)
    result = check_build(root)
    assert result["status"] == "PASS" and result["detail"].startswith(
        build["commit"][:7]
    )

    (repo / "truepanel.py").write_text("print('changed')\n")
    write_build(root, repo)
    assert check_build(root)["status"] == "WARN"
