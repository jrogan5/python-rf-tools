#!/usr/bin/env python3
"""
sorting.rdi
~~~~~~~~~~~

Read an MDIF file containing many Net blocks, group the nets four‑by‑four
(ordered by Net number), average the *s21_db* column within each group, and
write the result to a new MDIF file.

Groups are ordered by their mean ambient‑temperature (23 °C or 25 °C) gain,
lowest first.  Non‑ambient temperatures receive no SortIndex and appear after
the sorted ambient groups.

Usage (interactive):  python sorting.py
Usage (scripted):     python sorting.py --input path/to/in.mdif --output path/to/out.mdif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

NUM_NETS = 508 # the number of nets in the RDI. Some nets may be mising measurement entries. 

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.mdif import read_mdif, write_mdif
from utils.cli import prompt_validated

# -------------------------------------------------------------------------
# Input validators (used by the interactive CLI)
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

# define the groupings as if all rdi measurements were present
def _canonical_groups() -> List[List[int]]:
    """Return [[1,2,3,4], [5,6,7,8], …, [505,506,507,508]]"""
    return [list(range(start, start + 4))
            for start in range(1, NUM_NETS + 1, 4)]

# loading the mewasurement data from an mdif file. 
def _load(mdif_path: Path) -> Tuple[np.ndarray, Dict[float, List[Tuple[int, np.ndarray]]], Dict[float, List[Tuple[int, np.ndarray]]]]:
    """
    Return the shared frequency vector and a dict mapping temperature →
    sorted list of (net_number, s21_db_array) pairs.
    """
    meta, blocks = read_mdif(mdif_path)
    freq = blocks[0]["freq"]
    data: Dict[float, List[Tuple[int, np.ndarray]]] = {}
    full_map: Dict[float, List[Tuple[int, np.ndarray]]] = {}
    for m, b in zip(meta, blocks):
        data.setdefault(float(m["Temperature"]), []).append((int(m["Net"]), b["s21_db"]))
        full_map[(float(m["Temperature"]), int(m["Net"]))] = b
    return freq, data, full_map


def _group_by_4(nets: List[Tuple[int, np.ndarray]]) -> List[List[Tuple[int, np.ndarray]]]:
    """Split a list of (net, array) into sorted groups of four. Don't skip any net index in 1, 2, 3, ..., 508. """
    net_lookup: Dict[int, np.ndarray] = {net: arr for net, arr in nets}

    groups: List[List[Tuple[int, np.ndarray]]] = []
    for template in _canonical_groups():               # e.g. [1, 2, 3, 4]
        present = [
            (n, net_lookup[n]) for n in template if n in net_lookup
        ]                                               # 0‑4 items
        groups.append(present)

    return groups


def _avg_group(group: List[Tuple[int, np.ndarray]]) -> np.ndarray:
    return np.mean(np.vstack([s for _, s in group]), axis=0)


def _make_sort_index(
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]]
) -> Dict[Tuple[float, int], int]:
    """
    Rank each ambient‑temperature group by its mean s21_db (lowest → rank 1).
    Returns a dict mapping (temperature, group_id) → SortIndex.
    """
    ambient = {23.0, 25.0}
    ambient_means = {
        (temp, gid): np.mean(_avg_group(group))
            for temp, groups in temp_groups.items()
                if temp in ambient
                    for gid, group in enumerate(groups)
                        if group 
    }
    ordered = sorted(ambient_means.items(), key=lambda kv: kv[1])
    print(ordered)
    return {key: rank + 1 for rank, (key, _) in enumerate(ordered)}


def _flatten_and_sort(
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]],
    idx_map: Dict[Tuple[float, int], int],
) -> List[Tuple[float, int, List[Tuple[int, np.ndarray]]]]:
    """
    Return all groups ordered by SortIndex (ambient first, lowest index first).
    Non‑ambient groups receive a large index so they sort to the end.
    """
    beyond = max(idx_map.values(), default=0) + 1
    flat = [
        (idx_map.get((temp, gid), beyond), temp, gid, group)
        for temp, groups in temp_groups.items()
        for gid, group in enumerate(groups)
    ]
    flat.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(temp, gid, group) for _, temp, gid, group in flat]

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
    freq, temp_data, sparameters = _load(in_mdif)
    temp_groups = {t: _group_by_4(lst) for t, lst in temp_data.items()}
    idx_map = _make_sort_index(temp_groups)
    ordered = _flatten_and_sort(temp_groups, idx_map)

    blocks: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for temp, gid, group in ordered:
        for net in _canonical_groups()[gid]:
            blk = sparameters.get((temp, net))
            if blk is None : # no data
                continue
            meta = {
                "!SortIndex": idx_map.get((temp, gid), 0),
                "Net": net,
                "Temperature": temp,
            }
            rows = []
            for i, f in enumerate(freq):
                row = {"freq": float(f)}
                for col, arr in blk.items():
                    if col == "freq":
                        continue
                    row[col] = float(arr[i])
                rows.append(row)

            blocks.append((meta, rows))

    write_mdif(out_mdif, blocks=blocks, header_tokens=MDIF_HEADER_TOKENS)
    print(f"Written sorted/averaged data to {out_mdif}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Group RDI nets by 4, average s21_db, sort by ambient gain."
    )
    p.add_argument("--input",  type=Path, help="Input MDIF file.")
    p.add_argument("--output", type=Path, help="Output MDIF file.")
    return p.parse_args()


if __name__ == "__main__":
    print("=" * 40)
    print(" RDI Net Sorting / Averaging")
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
