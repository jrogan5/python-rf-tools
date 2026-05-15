#!/usr/bin/env python3
"""CLI entry‑point for the NF sweep converter."""

import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_to_mdif.nf.converter import run, DEFAULT_KEY
from utils.cli import prompt_missing, TEMP_MIN, TEMP_MAX


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Combine all NF‑sweep CSVs into a single MDIF file."
    )
    p.add_argument("--base-path", type=Path,
                   help="Root directory containing the net sub‑folders (E1, E2, …).")
    p.add_argument("--temperature", type=float,
                   help=f"Test temperature in °C ({TEMP_MIN} … {TEMP_MAX}).")
    p.add_argument("--key", default=DEFAULT_KEY,
                   help="Keyword that appears in the CSV filename (default: NF).")
    p.add_argument("--out-name", default=None,
                   help="Output filename override (written inside <base-path>/plots/).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    base_path: Path = args.base_path or prompt_missing(
        "Base directory containing net folders (E1, E2, …)", Path
    )
    if not base_path.is_dir():
        sys.exit(f"[ERROR] Directory not found: {base_path}")

    temperature: float = (
        args.temperature
        if args.temperature is not None
        else prompt_missing(f"Temperature (°C, {TEMP_MIN}…{TEMP_MAX})", float)
    )

    try:
        run(base_path, temperature, key=args.key, out_name=args.out_name)
    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
