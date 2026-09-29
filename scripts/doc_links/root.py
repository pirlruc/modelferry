"""Resolve the invoking repository root for the doc-link linter."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git_toplevel(cwd: Path) -> Path | None:
    """Return ``git rev-parse --show-toplevel`` for ``cwd``, or None."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.strip()
    return Path(text).resolve() if text else None


def is_submodule_git(git_path: Path) -> bool:
    """Return True when ``.git`` is a gitdir pointer file (submodule/worktree)."""
    if not git_path.is_file():
        return False
    try:
        return git_path.read_text(encoding="utf-8").lstrip().startswith("gitdir:")
    except OSError:
        return False


def walk_repo_root(start: Path) -> Path | None:
    """Walk up from ``start``, skipping submodule checkouts.

    Returns:
        The consuming repository root, or ``None`` when no candidate matches.
    """
    current = start.resolve()
    for candidate in (current, *current.parents):
        git_path = candidate / ".git"
        if not (candidate / "README.md").is_file() or not git_path.exists():
            continue
        if is_submodule_git(git_path):
            continue
        return candidate
    return None


def resolve_root(cli_root: Path | None) -> Path:
    """Resolve the invoking repository root.

    Returns:
        The directory whose markdown links should be checked.
    """
    if cli_root is not None:
        return cli_root.expanduser().resolve()
    env = os.environ.get("CONSUMING_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd()
    toplevel = git_toplevel(cwd)
    if toplevel is not None:
        return toplevel
    walked = walk_repo_root(cwd)
    return walked if walked is not None else cwd.resolve()
