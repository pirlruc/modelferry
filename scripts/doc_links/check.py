"""Check that extracted destinations resolve under the repository root."""

from __future__ import annotations

from pathlib import Path

from doc_links.fences import strip_fences
from doc_links.parse import is_absolute_fs_path, iter_destinations, path_from_destination


def is_repo_relative(path_only: str) -> bool:
    """Return True when ``path_only`` is not explicitly file-relative."""
    return not path_only.startswith(("./", "../")) and path_only not in {".", ".."}


def is_under_root(path: Path, root: Path) -> bool:
    """Return True when ``path`` resolves inside ``root``."""
    return path.resolve().is_relative_to(root.resolve())


def candidate_targets(source: Path, path_only: str, root: Path) -> list[Path]:
    """Return paths to try for a relative link (file-relative, then repo-root)."""
    targets = [source.parent / path_only]
    if is_repo_relative(path_only):
        targets.append(root / path_only)
    return targets


def target_ok(path: Path) -> bool:
    """Return True when ``path`` is a file, or a directory that contains README.md."""
    resolved = path.resolve()
    if resolved.is_file():
        return True
    return resolved.is_dir() and (resolved / "README.md").is_file()


def _missing_target(md_file: Path, path_only: str, root: Path) -> Path:
    """Return the path that should have existed for a broken link."""
    if is_repo_relative(path_only):
        return (root / path_only).resolve()
    return (md_file.parent / path_only).resolve()


def _failure_message(rel: Path, raw: str, target: Path) -> str:
    """Format one broken-link line.

    Returns:
        The single-line failure text.
    """
    if target.is_dir():
        return f"{rel} -> {raw} (directory target; link a file)"
    return f"{rel} -> {raw}"


def _check_relative(md_file: Path, path_only: str, raw: str, root: Path, rel: Path) -> str | None:
    """Return a failure for a relative dest, or None when it resolves in-repo."""
    escaped = False
    for candidate in candidate_targets(md_file, path_only, root):
        if not is_under_root(candidate, root):
            escaped = True
            continue
        if target_ok(candidate):
            return None
    if escaped:
        return f"{rel} -> {raw} (escapes repository root)"
    return _failure_message(rel, raw, _missing_target(md_file, path_only, root))


def check_destination(md_file: Path, path_only: str, raw: str, root: Path, rel: Path) -> str | None:
    """Return a failure string for one destination, or None when it is ok."""
    if is_absolute_fs_path(path_only):
        return f"{rel} -> {raw} (absolute path)"
    return _check_relative(md_file, path_only, raw, root, rel)


def check_file(md_file: Path, root: Path) -> list[str]:
    """Return failure strings for one documentation file."""
    failures: list[str] = []
    text = strip_fences(md_file.read_text(encoding="utf-8"))
    rel = md_file.relative_to(root)
    for raw in iter_destinations(text):
        path_only = path_from_destination(raw)
        if path_only is None:
            continue
        failure = check_destination(md_file, path_only, raw, root, rel)
        if failure:
            failures.append(failure)
    return failures
