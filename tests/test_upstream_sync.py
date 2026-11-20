"""Exercise the upstream sync workflow using local Git repositories only."""

import os
import subprocess
from pathlib import Path

import pytest

SYNC_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_upstream.sh"


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=check,
    )


@pytest.fixture
def repositories(tmp_path):
    upstream = tmp_path / "upstream"
    fork = tmp_path / "fork.git"
    work = tmp_path / "work"
    upstream.mkdir()
    git(upstream, "init", "-b", "main")
    git(upstream, "config", "user.name", "upstream-test")
    git(upstream, "config", "user.email", "upstream@example.invalid")
    (upstream / "README.md").write_text("base\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "baseline")

    subprocess.run(
        ["git", "init", "--bare", str(fork)], capture_output=True, check=True
    )
    git(fork, "symbolic-ref", "HEAD", "refs/heads/main")
    subprocess.run(
        ["git", "clone", str(upstream), str(work)], capture_output=True, check=True
    )
    git(work, "remote", "set-url", "origin", str(fork))
    git(work, "push", "-u", "origin", "main")
    git(work, "config", "user.name", "fork-test")
    git(work, "config", "user.email", "fork@example.invalid")

    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    gh = executable_dir / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$GH_LOG_FILE"\n')
    gh.chmod(0o755)
    env = os.environ.copy()
    env["SHIKHU_UPSTREAM_URL"] = str(upstream)
    env["GH_LOG_FILE"] = str(tmp_path / "gh-args")
    env["PATH"] = f"{executable_dir}:{env['PATH']}"
    return upstream, fork, work, env


def run_sync(work: Path, env: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SYNC_SCRIPT)],
        cwd=work,
        env=env,
        text=True,
        capture_output=True,
    )


def test_sync_opens_review_branch_without_changing_main(repositories):
    upstream, fork, work, env = repositories
    old_main = git(fork, "rev-parse", "refs/heads/main").stdout.strip()
    (upstream / "NEWS.md").write_text("new upstream feature\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "new feature")
    upstream_sha = git(upstream, "rev-parse", "HEAD").stdout.strip()
    short = git(upstream, "rev-parse", "--short=12", "HEAD").stdout.strip()

    result = run_sync(work, env)
    assert result.returncode == 0, result.stderr
    assert git(fork, "rev-parse", "refs/heads/main").stdout.strip() == old_main
    new_head = git(fork, "rev-parse", f"refs/heads/sync/upstream-{short}").stdout.strip()
    parents = git(fork, "show", "-s", "--format=%P", new_head).stdout.split()
    assert parents == [old_main, upstream_sha]
    assert "pr create --base main --head" in Path(env["GH_LOG_FILE"]).read_text()

    second = run_sync(work, env)
    assert second.returncode == 0
    assert "already exists" in second.stdout


def test_conflict_stops_without_remote_push(repositories):
    upstream, fork, work, env = repositories
    (work / "README.md").write_text("fork change\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "fork change")
    git(work, "push", "origin", "main")
    fork_main = git(fork, "rev-parse", "refs/heads/main").stdout.strip()

    (upstream / "README.md").write_text("upstream change\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "upstream change")
    short = git(upstream, "rev-parse", "--short=12", "HEAD").stdout.strip()

    result = run_sync(work, env)
    assert result.returncode == 1
    assert "No remote changes were pushed" in result.stderr
    assert git(fork, "rev-parse", "refs/heads/main").stdout.strip() == fork_main
    remote_branch = git(fork, "rev-parse", f"refs/heads/sync/upstream-{short}", check=False)
    assert remote_branch.returncode != 0
    assert not Path(env["GH_LOG_FILE"]).exists()
