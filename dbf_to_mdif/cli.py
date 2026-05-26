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
        "--base-dir", type=Path,
        help="Base directory containing test directories with ADC*-P*-J*.txt files.",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--powered",   dest="powered", action="store_true",  default=None,
                       help="Use powered measurement subfolder.")
    group.add_argument("--unpowered", dest="powered", action="store_false",
                       help="Use unpowered measurement subfolder.")
    p.add_argument(
        "--out-dir",
        help="Give output MDIF file directory",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    base_dir: Path = args.base_dir or prompt_validated("Base directory containing test directories with ADC*-P*-J*.txt files", _validate_dir)
    if not base_dir.is_dir():
        sys.exit(f"[ERROR] Directory not found: {base_dir}")

    out_dir: Path = args.out_dir or prompt_validated("Give output MDIF file directory", _validate_dir)
    if not out_dir.is_dir():
        sys.exit(f"[ERROR] Directory not found: {out_dir}")

    powered: bool
    if args.powered is None:
        raw = input("Powered or unpowered measurement? [p/u]: ").strip().lower()
        powered = raw.startswith("p")
    else:
        powered = args.powered

    from dbf_to_mdif.converter import run
    try:
        out = run(base_dir, powered, out_dir=out_dir)
        print(f"MDIF written to: {out}")
    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
