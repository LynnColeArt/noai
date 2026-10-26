"""Non-destructive project copying with transactional output publication."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .transform import garble_html

DEFAULT_EXCLUDES = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"})


@dataclass(frozen=True)
class Report:
    """Counts for files actually considered by the operation."""

    html_files: int = 0
    changed_files: int = 0
    copied_files: int = 0
    skipped_symlinks: int = 0


def transform_project(
    source: Path,
    output: Path,
    *,
    seed: str = "sovereignty",
    dry_run: bool = False,
    exclude: frozenset[str] = DEFAULT_EXCLUDES,
) -> Report:
    """Copy a project to a new sibling/outside folder, transforming UTF-8 HTML.

    Existing output is never intentionally overwritten. Symlinks are skipped;
    unreadable files and invalid UTF-8 abort before the final output is created.
    Exclusions match directory basenames at any depth.
    """
    source, output = source.resolve(), output.absolute()
    resolved_output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"Source is not a directory: {source}")
    if resolved_output == source or source in resolved_output.parents:
        raise ValueError("Output must be outside the source directory.")
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"Output parent does not exist: {output.parent}")

    counts = {"html_files": 0, "changed_files": 0, "copied_files": 0, "skipped_symlinks": 0}
    temporary = None if dry_run else Path(tempfile.mkdtemp(prefix=".noai-", dir=output.parent))
    try:
        def fail(error: OSError) -> None:
            raise error

        for root, dirs, files in os.walk(source, followlinks=False, onerror=fail):
            directory = Path(root)
            counts["skipped_symlinks"] += sum((directory / name).is_symlink() for name in dirs)
            dirs[:] = sorted(name for name in dirs if name not in exclude and not (directory / name).is_symlink())
            destination = temporary / directory.relative_to(source) if temporary else None
            if destination:
                destination.mkdir(parents=True, exist_ok=True)
            for name in sorted(files):
                path = directory / name
                if path.is_symlink():
                    counts["skipped_symlinks"] += 1
                    continue
                if not path.is_file():
                    raise ValueError(f"Unsupported non-regular file: {path}")
                if path.suffix.lower() in {".html", ".htm"}:
                    # Reading bytes avoids Python's universal-newline conversion.
                    original = path.read_bytes().decode("utf-8")
                    transformed = garble_html(original, seed)
                    counts["html_files"] += 1
                    counts["changed_files"] += original != transformed
                    if destination:
                        target = destination / name
                        target.write_bytes(transformed.encode("utf-8"))
                        shutil.copystat(path, target)
                else:
                    counts["copied_files"] += 1
                    if destination:
                        shutil.copy2(path, destination / name)
        if temporary:
            # Check again immediately before publication; no partial site on failure.
            if output.exists() or output.is_symlink():
                raise ValueError(f"Output appeared during processing: {output}")
            temporary.rename(output)
        return Report(**counts)
    finally:
        if temporary and temporary.exists():
            shutil.rmtree(temporary)
