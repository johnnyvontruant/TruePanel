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


def make_tree(root):
    for rel, text in {
        "truepanel.py": "launcher\n",
        "truepanel/__init__.py": "v\n",
        "truepanel/loadmaster/plan.py": "plan\n",
        # Never part of the fingerprint: same excludes as promotion.
        "truepanel/__pycache__/x.cpython-311.pyc": "cache",
        "truepanel/old.pyc": "cache",
        "truepanel.yaml": "config\n",
        ".venv/lib/site.py": "venv\n",
        "bin/truepanel": "wrapper\n",
        "development/logs/run.log": "log\n",
        "truepanel.yaml.before-v2": "snapshot\n",
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_fingerprint_covers_what_promotion_installs(tmp_path):
    from truepanel.build import tree_digest

    make_tree(tmp_path)
    assert sorted(tree_digest(tmp_path)) == [
        "truepanel.py",
        "truepanel/__init__.py",
        "truepanel/loadmaster/plan.py",
    ]


def test_verify_reports_files_changed_outside_the_upgrade(tmp_path):
    root = tmp_path / "deployed"
    make_tree(root)
    repo = make_repo(tmp_path)
    write_build(root, repo)  # as staging + promotion would leave it

    result = check_build(root)
    assert result["status"] == "PASS" and result["detail"].endswith("files match")

    # Config, caches and venv change all the time: not drift.
    (root / "truepanel.yaml").write_text("edited config\n")
    (root / "truepanel" / "__pycache__" / "y.pyc").write_text("new cache")
    assert check_build(root)["status"] == "PASS"

    # A hand deploy: one file edited, one removed, one added.
    (root / "truepanel" / "loadmaster" / "plan.py").write_text("hot patch\n")
    (root / "truepanel" / "__init__.py").unlink()
    (root / "truepanel" / "loadmaster" / "extra.py").write_text("new\n")
    result = check_build(root)
    assert result["status"] == "WARN"
    assert "1 changed, 1 missing, 1 extra" in result["detail"]
    assert "truepanel/loadmaster/plan.py" in result["detail"]


def test_stamp_without_fingerprint_still_passes(tmp_path):
    root = tmp_path / "deployed"
    root.mkdir()
    (root / BUILD_FILE).write_text('{"commit": "0031e9de0ca6", "branch": "main"}')
    result = check_build(root)
    assert result["status"] == "PASS" and "files match" not in result["detail"]
