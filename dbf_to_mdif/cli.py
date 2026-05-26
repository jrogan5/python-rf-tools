#!/usr/bin/env python3
"""CLI entry-point for the DBF .mat → MDIF converter."""

import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.cli import prompt_validated


def _validate_dir(s: str):
    d = Path(s)
    return (True, d) if d.is_dir() else (False, f"Not a directory: {d}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert DBF .mat VNA measurement files to a combined MDIF file."
    )
    p.add_argument(
        "--test-dir", type=Path,
        help="Root test directory containing ADC*-P*-J*.txt path files.",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--powered",   dest="powered", action="store_true",  default=None,
                       help="Use powered measurement subfolder.")
    group.add_argument("--unpowered", dest="powered", action="store_false",
                       help="Use unpowered measurement subfolder.")
    p.add_argument(
        "--out-name", default=None,
        help="Override output filename (written into <test-dir>/plots/).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    test_dir: Path = args.test_dir or prompt_validated(
        "Test directory (containing ADC*-P*-J*.txt files)", _validate_dir
    )
    if not test_dir.is_dir():
        sys.exit(f"[ERROR] Directory not found: {test_dir}")

    powered: bool
    if args.powered is None:
        raw = input("Powered or unpowered measurement? [p/u]: ").strip().lower()
        powered = raw.startswith("p")
    else:
        powered = args.powered

    from dbf_to_mdif.converter import run
    try:
        out = run(test_dir, powered, out_name=args.out_name)
        print(f"MDIF written to: {out}")
    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
