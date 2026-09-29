"""Extract markdown destinations from unfenced text."""

from __future__ import annotations

import re
from urllib.parse import unquote

from doc_links.dest import read_inline_destination
from doc_links.title import strip_title

ABS_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")
REF_DEF = re.compile(r"^\s*\[[^\]]+\]:\s+(\S+)")


def iter_destinations(text: str) -> list[str]:
    """Yield inline and reference-style markdown destinations.

    Returns:
        Destinations in source order.
    """
    dests: list[str] = []
    i = 0
    while True:
        start = text.find("](", i)
        if start == -1:
            break
        dest, nxt = read_inline_destination(text, start + 2)
        if dest:
            dests.append(dest)
        i = nxt
    dests.extend(_reference_destinations(text))
    return dests


def _reference_destinations(text: str) -> list[str]:
    """Return destinations from markdown reference definitions."""
    dests: list[str] = []
    for line in text.splitlines():
        match = REF_DEF.match(line)
        if match:
            dests.append(strip_title(match.group(1)))
    return dests


def path_from_destination(raw: str) -> str | None:
    """Return a filesystem path, or None when the dest is a skipped scheme.

    http(s)/mailto/tel/# destinations are skipped. Absolute host paths are
    returned so the checker can fail them — they must not be treated as
    external links or joined onto the repository root.
    """
    link = unquote(raw.strip())
    if not link or link.startswith(ABS_PREFIXES):
        return None
    path_only = link.split("#", 1)[0].split("?", 1)[0].strip()
    return path_only or None


def is_absolute_fs_path(path_only: str) -> bool:
    """Return True when ``path_only`` is a host absolute path."""
    if path_only.startswith("/") or path_only.startswith("\\"):
        return True
    if len(path_only) < 3 or not path_only[0].isalpha() or path_only[1] != ":":
        return False
    return path_only[2] in "/\\"
