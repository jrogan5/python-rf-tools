#!/usr/bin/env python3
"""
sorting.4pack
~~~~~~~~~~~~~

Read an MDIF file where each block represents one (SN, Path, Temperature)
combination, average *s21_db* across the four paths for each SN/temperature
pair, and write the sorted result to a new MDIF file.

SNs are ordered by their mean ambient‑temperature (23 °C or 25 °C) gain,
lowest first.  SNs with no ambient measurement appear after the sorted ones.

Usage (interactive):  python sorting.py
Usage (scripted):     python sorting.py --input path/to/in.mdif --output path/to/out.mdif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.mdif import read_mdif, write_mdif
from utils.cli import prompt_validated

# -------------------------------------------------------------------------
# Input validators
# -------------------------------------------------------------------------

def _must_be_mdif_file(p: str) -> Tuple[bool, Any]:
    f = Path(p)
    if not f.is_file():
        return False, f"File not found: {f}"
    if f.suffix.lower() != ".mdif":
        return False, "File must end with .mdif"
    return True, f


def _good_mdif_name(name: str) -> Tuple[bool, Any]:
    if not name:
        return False, "Filename cannot be empty"
    if any(c in name for c in "/\\"):
        return False, "Filename must not contain path separators"
    if not name.lower().endswith(".mdif"):
        name += ".mdif"
    return True, name


def _must_be_dir(p: str) -> Tuple[bool, Any]:
    d = Path(p)
    return (True, d) if d.is_dir() else (False, f"Directory not found: {d}")


def _safe_out_dir(p: str) -> Tuple[bool, Any]:
    d = Path(p)
    if d.is_dir():
        return True, d
    ans = input(f"  '{d}' does not exist. Create it? [y/N]: ").strip().lower()
    if ans not in {"y", "yes"}:
        return False, f"Directory not created: {d}"
    try:
        d.mkdir(parents=True)
        return True, d
    except Exception as exc:
        return False, f"Could not create directory: {exc}"


# -------------------------------------------------------------------------
# Core logic
# -------------------------------------------------------------------------

# Maps (SN, Temperature) → list of (path_number, s21_db_array)
_GroupKey = Tuple[int, float]
_Groups = Dict[_GroupKey, List[Tuple[int, np.ndarray]]]
_FullMap = Dict[Tuple[int, float, int], Dict[str, np.ndarray]]


def _load(mdif_path: Path) -> Tuple[np.ndarray, _Groups, _FullMap]:
    """
    Return the shared frequency vector and a dict mapping (SN, Temperature) →
    list of (path_number, s21_db_array) pairs.
    """
    meta, blocks = read_mdif(mdif_path)
    freq = blocks[0]["freq"]
    groups: _Groups = {}
    full:   _FullMap = {}

    for m, b in zip(meta, blocks):
        key: _GroupKey = (int(m["SN"]), float(m["Temperature"]))
        groups.setdefault(key, []).append((int(m["Path"]), b["s21_db"]))
        full[(int(m["SN"]), float(m["Temperature"]), int(m["Path"]))] = b
    return freq, groups, full


def _avg_paths(path_blocks: List[Tuple[int, np.ndarray]]) -> np.ndarray:
    """Average s21_db across all paths (sorted by path number for consistency)."""
    path_blocks.sort(key=lambda p: p[0])
    return np.mean(np.vstack([g for _, g in path_blocks]), axis=0)


def _sort_index(groups: _Groups) -> Dict[int, int]:
    """
    Map SN → SortIndex (1 = lowest ambient gain).
    SNs without an ambient measurement get index len(ambient_sns) + 1.
    """
    ambient = {23.0, 25.0}
    scores = [
        (sn, np.mean(_avg_paths(paths)))
        for (sn, temp), paths in groups.items()
        if temp in ambient
    ]
    scores.sort(key=lambda x: x[1])
    return {sn: rank + 1 for rank, (sn, _) in enumerate(scores)}


def _build_blocks(
    freq: np.ndarray,
    groups: _Groups,
    full: _FullMap,
    idx: Dict[int, int],
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Return write_mdif blocks ordered by SortIndex (ambient SNs first,
    lowest to highest).  Non‑ambient SNs appear afterwards.
    """
    beyond = max(idx.values(), default=0) + 1
    ordered = sorted(groups.keys(), key=lambda k: (idx.get(k[0], beyond), k[1]))

    blocks = []
    for sn, temp in ordered:
        path_list = groups[(sn, temp)]
        path_list.sort(key=lambda p: p[0])
        for path, _ in path_list:
            meta = {
                "!SortIndex": idx.get(sn, beyond),
                "SN": sn,
                "Temperature": temp,
                "Path": path,
            }

            blk = full[(sn, temp, path)]
            rows: List[Dict[str, Any]] = []
            for i, f in enumerate(freq):
                row = {"freq": float(f)}
                for col, arr in blk.items():
                    if col == "freq":
                        continue
                    row[col] = float(arr[i])
                rows.append(row)

            blocks.append((meta, rows))
    return blocks

MDIF_HEADER_TOKENS = [
    "%freq(real)",
    "s11_db(real)",
    "s11_deg(real)",
    "s21_db(real)",
    "s21_deg(real)",
    "s12_db(real)",
    "s12_deg(real)",
    "s22_db(real)",
    "s22_deg(real)",
]

def main(in_mdif: Path, out_mdif: Path) -> None:
    freq, groups, sparameters = _load(in_mdif)
    idx = _sort_index(groups)
    blocks = _build_blocks(freq, groups, sparameters, idx)
    write_mdif(out_mdif, blocks=blocks, header_tokens=MDIF_HEADER_TOKENS)
    print(f"Written sorted/averaged data to {out_mdif}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Average 4‑pack s21_db paths per SN and sort by ambient gain."
    )
    p.add_argument("--input",  type=Path, help="Input MDIF file.")
    p.add_argument("--output", type=Path, help="Output MDIF file.")
    return p.parse_args()


if __name__ == "__main__":
    print("=" * 40)
    print(" 4‑Pack Path Sorting / Averaging")
    print("=" * 40)

    args = _parse_args()

    if args.input:
        in_path = args.input
    else:
        in_dir  = prompt_validated("Input directory containing the .mdif file", _must_be_dir)
        in_name = prompt_validated("Input filename", _good_mdif_name)
        in_path = Path(in_dir, in_name)
        ok, msg = _must_be_mdif_file(str(in_path))
        if not ok:
            sys.exit(f"Error: {msg}")

    if args.output:
        out_path = args.output
    else:
        out_dir  = prompt_validated("Output directory", _safe_out_dir)
        out_name = prompt_validated("Output filename", _good_mdif_name)
        out_path = Path(out_dir, out_name)

    main(in_path, out_path)
