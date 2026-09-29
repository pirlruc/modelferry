#!/usr/bin/env python3
"""Validate relative markdown and Cursor-rule links under the repository root.

Snapshot of `.github/scaffold` tag 1.7.0 (`e76bb3f`) for CI. The Actions
secrets can read guardrails and commondevops, and they are denied on
`pirlruc/github-scaffold`.

Algorithm tracks pirlruc/methodologies@1.2.1 common/scripts/lint-doc-links.py.
Helpers live in scripts/doc_links/ so each module meets PY-CPLX-002. Refresh
those helpers from that tag when bumping the methodologies pin. Vendored
because both repos are private and GITHUB_TOKEN cannot check out a sibling
repository in CI.

Root resolution (first match wins): ``--root``, ``CONSUMING_REPO_ROOT``,
``git rev-parse --show-toplevel`` from the current working directory. A ``.git``
file whose contents start with ``gitdir:`` is a submodule boundary and is not
treated as the repo root, so a vendored copy of this script does not silently
lint the wrong tree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI arguments.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root to scan (overrides env and git detection)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Lint relative links.

    Returns:
        ``0`` when every relative link resolves, ``1`` otherwise.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from doc_links.check import check_file
    from doc_links.root import resolve_root
    from doc_links.scan import collect_doc_files

    args = parse_args(argv)
    root = resolve_root(args.root)
    doc_files = collect_doc_files(root)
    if not doc_files:
        print(f"ERROR: no markdown or Cursor-rule files found under {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    for md_file in doc_files:
        failures.extend(check_file(md_file, root))
    if not failures:
        print("Markdown link check passed.")
        return 0
    print("ERROR: Broken markdown links found:")
    for item in failures:
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
