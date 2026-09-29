"""Collect documentation files, skipping nested checkouts."""

from __future__ import annotations

from pathlib import Path

SKIP_DIR_NAMES = {".git", "node_modules", "vendor", ".venv"}
DOC_GLOBS = ("*.md", "*.mdc")


def is_skipped(path: Path, root: Path) -> bool:
    """Return True when ``path`` sits under a skipped or nested-git directory."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    if any(part in SKIP_DIR_NAMES for part in rel.parts):
        return True
    current = path.parent
    while current != root and current != current.parent:
        if (current / ".git").exists():
            return True
        current = current.parent
    return False


def collect_doc_files(root: Path) -> list[Path]:
    """Return sorted markdown and Cursor-rule files under ``root``."""
    files: list[Path] = []
    for glob in DOC_GLOBS:
        files.extend(p for p in root.rglob(glob) if not is_skipped(p, root))
    return sorted(files)
