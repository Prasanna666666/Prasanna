"""The update command never moves or discards the owner's own work: it refuses when there are unsaved changes or local commits, and otherwise only moves the branch forward."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "update-code.sh"


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


def commit(cwd: Path, name: str, text: str = "x") -> None:
    (cwd / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-m", name)


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "atlas", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(origin), str(seed))
    git(seed, "checkout", "-b", "atlas")
    commit(seed, "one")
    git(seed, "push", "origin", "atlas")
    mine = tmp_path / "mine"
    git(tmp_path, "clone", "-b", "atlas", str(origin), str(mine))
    return seed, mine


def update(mine: Path, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env={**os.environ, "ATLAS_REPO": str(mine), **env})


def publish(seed: Path, name: str) -> None:
    commit(seed, name)
    git(seed, "push", "origin", "atlas")


def test_behind_moves_forward_and_marks_where_it_was(repos):
    seed, mine = repos
    before = git(mine, "rev-parse", "HEAD")
    publish(seed, "two")
    result = update(mine)
    assert result.returncode == 0, result.stderr
    assert (mine / "two").exists()
    assert git(mine, "tag", "-l", "atlas-before-update-*").splitlines()
    assert git(mine, "rev-parse", git(mine, "tag", "-l", "atlas-before-update-*").splitlines()[0]) == before


def test_up_to_date_changes_nothing(repos):
    _seed, mine = repos
    head = git(mine, "rev-parse", "HEAD")
    assert update(mine).returncode == 0
    assert git(mine, "rev-parse", "HEAD") == head


def test_unsaved_changes_are_refused_and_left_exactly_as_they_were(repos):
    seed, mine = repos
    publish(seed, "two")
    (mine / "one").write_text("my unsaved edit")
    (mine / "new-file").write_text("untracked work")
    result = update(mine)
    assert result.returncode != 0 and "not saved" in result.stderr
    assert (mine / "one").read_text() == "my unsaved edit" and (mine / "new-file").read_text() == "untracked work"
    assert not (mine / "two").exists()


def test_local_commits_ahead_are_refused_and_stay_reachable(repos):
    _seed, mine = repos
    commit(mine, "mine-1", "my work")
    mine_head = git(mine, "rev-parse", "HEAD")
    result = update(mine)
    assert result.returncode != 0 and "1 commit" in result.stderr
    assert git(mine, "rev-parse", "atlas") == mine_head and (mine / "mine-1").read_text() == "my work"


def test_a_diverged_branch_is_refused_and_nothing_moves(repos):
    seed, mine = repos
    publish(seed, "server-2")
    commit(mine, "mine-1")
    mine_head = git(mine, "rev-parse", "HEAD")
    result = update(mine)
    assert result.returncode != 0
    assert git(mine, "rev-parse", "atlas") == mine_head and not (mine / "server-2").exists()


def test_no_local_branch_is_created_from_the_remote(repos, tmp_path):
    _seed, mine = repos
    git(mine, "checkout", "--detach")
    git(mine, "branch", "-D", "atlas")
    result = update(mine)
    assert result.returncode == 0, result.stderr
    assert git(mine, "rev-parse", "--abbrev-ref", "HEAD") == "atlas"


def test_being_on_another_branch_keeps_that_branch(repos):
    seed, mine = repos
    git(mine, "checkout", "-b", "experiment")
    commit(mine, "exp", "experiment work")
    publish(seed, "two")
    result = update(mine)
    assert result.returncode == 0, result.stderr
    assert git(mine, "rev-parse", "experiment") and git(mine, "show", "experiment:exp") == "experiment work"
