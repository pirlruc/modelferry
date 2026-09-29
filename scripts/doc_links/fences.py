"""Blank fenced code blocks so example links are not linted."""

from __future__ import annotations

import re

FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})")


def _fence_marker(line: str) -> str | None:
    """Return the fence marker on ``line``, or None."""
    match = FENCE_OPEN.match(line.lstrip())
    return match.group(1) if match else None


def _fence_step(line: str, fence: str | None) -> tuple[str | None, str]:
    """Advance fence state for one line.

    Returns:
        The new fence marker and the text that should be kept for this line.
    """
    marker = _fence_marker(line)
    blank = "\n" if line.endswith("\n") else ""
    if marker and fence is None:
        return marker, blank
    if marker and fence is not None and line.lstrip().startswith(fence):
        return None, blank
    return fence, (blank if fence is not None else line)


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks so example links are not linted.

    Returns:
        The text with fenced regions replaced by blank lines.
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        fence, piece = _fence_step(line, fence)
        out.append(piece)
    return "".join(out)
