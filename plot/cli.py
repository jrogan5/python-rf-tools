#!/usr/bin/env python3
"""
rf-plot — standalone interactive MDIF plotter.

Usage:
  rf-plot [path/to/file.mdif]
  python plot/cli.py
"""

import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.cli import prompt_validated
from utils.mdif import read_mdif


def _build_label(meta: dict) -> str:
    """Format a VAR dict into a human-readable trace label."""
    parts = []
    for k, v in meta.items():
        v_f = float(v)
        parts.append(f"{k}={int(v_f)}" if v_f.is_integer() else f"{k}={v_f:.4g}")
    return ", ".join(parts)


def _validate_file(s: str):
    f = Path(s)
    if not f.is_file():
        return False, f"File not found: {f}"
    return True, f


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Interactive plotter for MDIF measurement files."
    )
    p.add_argument(
        "mdif_file", nargs="?", type=Path, help="Path to the .mdif file to open."
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    mdif_path: Path = args.mdif_file or prompt_validated(
        "MDIF file path", _validate_file
    )
    if not mdif_path.is_file():
        sys.exit(f"[ERROR] File not found: {mdif_path}")

    try:
        meta_arr, data_blocks = read_mdif(mdif_path)
    except Exception as exc:
        sys.exit(f"[ERROR] Could not read MDIF file: {exc}")

    if not data_blocks:
        sys.exit("[ERROR] No data blocks found in the MDIF file.")

    traces = [
        (_build_label(meta), data)
        for meta, data in zip(meta_arr, data_blocks)
    ]

    from plot.gui import launch
    launch(traces, title=mdif_path.name)


if __name__ == "__main__":
    main()
