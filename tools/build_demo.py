#!/usr/bin/env python3
"""Build the public demo with the real transformer, or verify reproducibility."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from noai import garble_html  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = {
        "index.html": garble_html((ROOT / "examples/index.html").read_text(encoding="utf-8")).encode("utf-8"),
        "style.css": (ROOT / "examples/style.css").read_bytes(),
        "icon.svg": (ROOT / "examples/icon.svg").read_bytes(),
        ".nojekyll": b"",
    }
    for name, content in expected.items():
        target = ROOT / "docs" / name
        if args.check:
            if not target.is_file() or target.read_bytes() != content:
                print(f"Demo is stale: {target}", file=sys.stderr)
                return 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print("Demo is reproducible." if args.check else "Demo evacuated into docs/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
