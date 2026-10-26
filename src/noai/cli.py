"""The deliberately ordinary command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .project import DEFAULT_EXCLUDES, transform_project


def main(argv: list[str] | None = None) -> int:
    """Transform a project; return conventional process status codes."""
    parser = argparse.ArgumentParser(description="Protect your voice. Remove your words.")
    parser.add_argument("source", type=Path, help="project directory containing UTF-8 HTML")
    parser.add_argument("--output", "-o", required=True, type=Path, help="new output directory outside source")
    parser.add_argument("--seed", default="sovereignty", help="Artistic Sovereignty Constant")
    parser.add_argument("--dry-run", action="store_true", help="validate and count without writing files")
    parser.add_argument("--exclude", action="append", default=[], metavar="DIRECTORY", help="additional directory basename to skip")
    parser.add_argument("--version", action="version", version=f"NoAI {__version__}")
    args = parser.parse_args(argv)
    if any(not name or name in {".", ".."} or "/" in name or "\\" in name for name in args.exclude):
        parser.error("--exclude takes a directory basename, not a path")
    try:
        report = transform_project(
            args.source, args.output, seed=args.seed, dry_run=args.dry_run,
            exclude=DEFAULT_EXCLUDES | frozenset(args.exclude),
        )
    except (OSError, UnicodeError, ValueError) as error:
        print(f"noai: {error}", file=sys.stderr)
        return 1
    label = "Would evacuate" if args.dry_run else "Evacuated"
    print(f"{label} {report.changed_files}/{report.html_files} HTML files; "
          f"{report.copied_files} assets; {report.skipped_symlinks} symlinks skipped.")
    print("Semantic accessibility: regrettably diminished. AI resistance: unproven.")
    return 0
