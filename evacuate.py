#!/usr/bin/env python3
"""Run from a source checkout without installing dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from noai.cli import main  # noqa: E402 — source checkout bootstrap

if __name__ == "__main__":
    raise SystemExit(main())
