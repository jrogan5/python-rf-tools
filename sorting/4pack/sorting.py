#!/usr/bin/env python3
"""
sorting.4pack
~~~~~~~~~~~~~

Read an S-parameter MDIF file (VAR SN, Path, Temperature blocks from
sparam_nf_to_mdif.py), sort each (SN, Path, Temperature) block by a
SortIndex derived from the mean ambient-temperature s21_db per SN.

Optionally accepts a second NF MDIF file (same SN/Path/Temperature structure)
and writes a sorted NF MDIF using the same SortIndex.

SortIndex: lowest ambient-temperature mean s21_db (averaged across paths)
gets index 1. SNs with no ambient measurement are placed at the end.

Usage (interactive):  python sorting.py
Usage (scripted):     python sorting.py --input p/in.mdif --output p/out.mdif
                                        --input-nf p/nf.mdif --output-nf p/nf_out.mdif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
# Type aliases
# -------------------------------------------------------------------------

_GroupKey = Tuple[int, float]           # (SN, Temperature)
_Groups   = Dict[_GroupKey, List[Tuple[int, np.ndarray]]]          # -> [(path, s21_db)]
_FullMap  = Dict[Tuple[int, float, int], Dict[str, np.ndarray]]    # (SN, Temp, Path) -> cols


# -------------------------------------------------------------------------
# S-parameter loading
# -------------------------------------------------------------------------

def _load(mdif_path: Path) -> Tuple[np.ndarray, _Groups, _FullMap]:
    """
    Returns:
        freq    -- shared frequency vector
        groups  -- (SN, Temperature) -> [(path, s21_db_array)]  (for SortIndex)
        full    -- (SN, Temperature, Path) -> full column dict   (for block writing)
    """
    meta, blocks = read_mdif(mdif_path)
    freq: np.ndarray = blocks[0]["freq"]
    groups: _Groups = {}
    full:   _FullMap = {}
    for m, b in zip(meta, blocks):
        sn   = int(m["SN"])
        temp = float(m["Temperature"])
        path = int(m["Path"])
        groups.setdefault((sn, temp), []).append((path, b["s21_db"]))
        full[(sn, temp, path)] = b
    return freq, groups, full


# -------------------------------------------------------------------------
# NF loading
# -------------------------------------------------------------------------

def _load_nf(
    mdif_path: Path,
) -> Tuple[np.ndarray, Dict[Tuple[int, float, int], Dict[str, np.ndarray]]]:
    """
    Load an NF MDIF (SN + Path + Temperature VAR blocks, freq + nf_db columns).

    Returns:
        freq   -- shared frequency vector
        nf_map -- (SN, Temperature, Path) -> column dict
    """
    meta, blocks = read_mdif(mdif_path)
    freq = blocks[0]["freq"]
    nf_map: Dict[Tuple[int, float, int], Dict[str, np.ndarray]] = {}
    for m, b in zip(meta, blocks):
        nf_map[(int(m["SN"]), float(m["Temperature"]), int(m["Path"]))] = b
    return freq, nf_map


# -------------------------------------------------------------------------
# Sorting
# -------------------------------------------------------------------------

def _avg_paths(path_blocks: List[Tuple[int, np.ndarray]]) -> np.ndarray:
    """Average an array column across all paths (sorted by path number)."""
    path_blocks.sort(key=lambda p: p[0])
    return np.mean(np.vstack([g for _, g in path_blocks]), axis=0)


def _sort_index(groups: _Groups) -> Dict[int, int]:
    """
    Map SN -> SortIndex (1 = lowest ambient mean s21_db).
    SNs with no ambient measurement are not in the returned dict (caller uses
    a 'beyond' sentinel for them).
    """
    ambient = {23.0, 25.0}
    scores = [
        (sn, np.mean(_avg_paths(list(paths))))
        for (sn, temp), paths in groups.items()
        if temp in ambient
    ]
    scores.sort(key=lambda x: x[1])
    return {sn: rank + 1 for rank, (sn, _) in enumerate(scores)}


def _sorted_keys(groups: _Groups, idx: Dict[int, int]) -> List[_GroupKey]:
    """Return (SN, Temperature) keys ordered by SortIndex then temperature."""
    beyond = max(idx.values(), default=0) + 1
    return sorted(groups.keys(), key=lambda k: (idx.get(k[0], beyond), k[1]))


# -------------------------------------------------------------------------
# Block builders
# -------------------------------------------------------------------------

SPARAM_HEADER = [
    "%freq(real)",
    "s11_db(real)", "s11_deg(real)",
    "s21_db(real)", "s21_deg(real)",
    "s12_db(real)", "s12_deg(real)",
    "s22_db(real)", "s22_deg(real)",
]

NF_HEADER = ["%freq(real)", "nf_db(real)"]


def _build_sparam_blocks(
    freq: np.ndarray,
    groups: _Groups,
    full: _FullMap,
    idx: Dict[int, int],
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    beyond = max(idx.values(), default=0) + 1
    blocks = []
    for sn, temp in _sorted_keys(groups, idx):
        path_list = sorted(groups[(sn, temp)], key=lambda p: p[0])
        for path, _ in path_list:
            blk = full.get((sn, temp, path))
            if blk is None:
                continue
            meta = {
                "SortIndex": idx.get(sn, beyond),
                "!SN": sn,
                "Temperature": temp,
                "Path": path,
            }
            rows = [
                {"freq": float(f), **{col: float(arr[i]) for col, arr in blk.items() if col != "freq"}}
                for i, f in enumerate(freq)
            ]
            blocks.append((meta, rows))
    return blocks


def _build_nf_blocks(
    nf_freq: np.ndarray,
    nf_map: Dict[Tuple[int, float, int], Dict[str, np.ndarray]],
    groups: _Groups,
    idx: Dict[int, int],
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Write one NF block per (SN, Temperature, Path), in the same order as the
    S-param output so the two files are aligned block-for-block.
    """
    beyond = max(idx.values(), default=0) + 1
    blocks = []
    for sn, temp in _sorted_keys(groups, idx):
        path_list = sorted(groups[(sn, temp)], key=lambda p: p[0])
        for path, _ in path_list:
            blk = nf_map.get((sn, temp, path))
            if blk is None:
                continue
            meta = {
                "SortIndex": idx.get(sn, beyond),
                "!SN": sn,
                "Temperature": temp,
                "Path": path,
            }
            rows = [{"freq": float(f), "nf_db": float(blk["nf_db"][i])}
                    for i, f in enumerate(nf_freq)]
            blocks.append((meta, rows))
    return blocks


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main(
    in_mdif: Path,
    out_mdif: Path,
    nf_in_mdif: Optional[Path] = None,
    nf_out_mdif: Optional[Path] = None,
) -> None:
    freq, groups, full = _load(in_mdif)
    idx = _sort_index(groups)

    sparam_blocks = _build_sparam_blocks(freq, groups, full, idx)
    write_mdif(out_mdif, blocks=sparam_blocks, header_tokens=SPARAM_HEADER)
    print(f"Written sorted S-parameter data to {out_mdif}")

    if nf_in_mdif and nf_out_mdif:
        nf_freq, nf_map = _load_nf(nf_in_mdif)
        nf_blocks = _build_nf_blocks(nf_freq, nf_map, groups, idx)
        write_mdif(nf_out_mdif, blocks=nf_blocks, header_tokens=NF_HEADER)
        print(f"Written sorted NF data to {nf_out_mdif}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sort 4-pack S-param (and optionally NF) MDIF by ambient gain."
    )
    p.add_argument("--input",     type=Path, help="Input S-parameter MDIF file.")
    p.add_argument("--output",    type=Path, help="Output S-parameter MDIF file.")
    p.add_argument("--input-nf",  type=Path, help="Input NF MDIF file (optional).")
    p.add_argument("--output-nf", type=Path, help="Output NF MDIF file (optional).")
    return p.parse_args()


if __name__ == "__main__":
    print("=" * 40)
    print(" 4-Pack Path Sorting")
    print("=" * 40)

    args = _parse_args()

    # -- S-parameter input ---------------------------------------------------
    if args.input:
        in_path = args.input
        in_dir  = in_path.parent
    else:
        in_dir  = prompt_validated("Input directory containing the MDIF files", _must_be_dir)
        in_name = prompt_validated("S-parameter input filename", _good_mdif_name)
        in_path = Path(in_dir, in_name)
        ok, msg = _must_be_mdif_file(str(in_path))
        if not ok:
            sys.exit(f"Error: {msg}")

    # -- NF input (same directory) -------------------------------------------
    if args.input_nf:
        nf_in_path: Optional[Path] = args.input_nf
    else:
        nf_name = prompt_validated("NF input filename (in same directory)", _good_mdif_name)
        nf_in_path = Path(in_dir, nf_name)
        ok, msg = _must_be_mdif_file(str(nf_in_path))
        if not ok:
            sys.exit(f"Error: {msg}")

    # -- S-parameter output --------------------------------------------------
    if args.output:
        out_path = args.output
        out_dir  = out_path.parent
    else:
        out_dir  = prompt_validated("Output directory", _safe_out_dir)
        out_name = prompt_validated("S-parameter output filename", _good_mdif_name)
        out_path = Path(out_dir, out_name)

    # -- NF output (same output directory) -----------------------------------
    if args.output_nf:
        nf_out_path: Optional[Path] = args.output_nf
    else:
        nf_out_name = prompt_validated("NF output filename (in same output directory)", _good_mdif_name)
        nf_out_path = Path(out_dir, nf_out_name)

    main(in_path, out_path, nf_in_path, nf_out_path)
