#!/usr/bin/env python3
"""
sorting.rdi
~~~~~~~~~~~

Read an S-parameter MDIF file containing per-net blocks, sort each net into
its canonical 4-net group (groups defined by fixed net ranges 1-4, 5-8, ...),
and write the blocks in SortIndex order.

Optionally accepts a second NF MDIF file (same net/temperature structure, from
the nf converter) and writes a sorted NF MDIF using the same SortIndex.

SortNet is assigned per net: within each ambient-ranked group (ranked by mean
s21_db at 23 °C or 25 °C, lowest gain = rank 1), the four nets receive
SortNet values 4*(rank-1)+1 … 4*(rank-1)+4, giving a unique 1..508 index.
Non-ambient-temperature blocks receive SortNet=0.

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

NUM_NETS = 508  # total RDI net count; defines canonical group boundaries

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
# Canonical group definitions
# -------------------------------------------------------------------------

def _canonical_groups() -> List[List[int]]:
    """Return [[1,2,3,4], [5,6,7,8], ..., [505,506,507,508]]."""
    return [list(range(start, start + 4)) for start in range(1, NUM_NETS + 1, 4)]


# -------------------------------------------------------------------------
# S-parameter loading
# -------------------------------------------------------------------------

def _load(
    mdif_path: Path,
) -> Tuple[
    np.ndarray,
    Dict[float, List[Tuple[int, np.ndarray]]],
    Dict[Tuple[float, int], Dict[str, np.ndarray]],
]:
    """
    Returns:
        freq       -- shared frequency vector (from first block)
        temp_data  -- temperature -> [(net, s21_db_array)]  (for SortIndex calc)
        full_map   -- (temperature, net) -> full column dict (for block writing)
    """
    meta, blocks = read_mdif(mdif_path)
    freq = blocks[0]["freq"]
    temp_data: Dict[float, List[Tuple[int, np.ndarray]]] = {}
    full_map: Dict[Tuple[float, int], Dict[str, np.ndarray]] = {}
    for m, b in zip(meta, blocks):
        temp = float(m["Temperature"])
        net  = int(m["Net"])
        temp_data.setdefault(temp, []).append((net, b["s21_db"]))
        full_map[(temp, net)] = b
    return freq, temp_data, full_map


# -------------------------------------------------------------------------
# NF loading
# -------------------------------------------------------------------------

def _load_nf(
    mdif_path: Path,
) -> Tuple[np.ndarray, Dict[Tuple[float, int], Dict[str, np.ndarray]]]:
    """
    Load an NF MDIF (Net + Temperature VAR blocks, freq + nf_db columns).

    Returns:
        freq    -- shared frequency vector
        nf_map  -- (temperature, net) -> column dict
    """
    meta, blocks = read_mdif(mdif_path)
    freq = blocks[0]["freq"]
    nf_map: Dict[Tuple[float, int], Dict[str, np.ndarray]] = {}
    for m, b in zip(meta, blocks):
        nf_map[(float(m["Temperature"]), int(m["Net"]))] = b
    return freq, nf_map


# -------------------------------------------------------------------------
# Grouping and sorting
# -------------------------------------------------------------------------

def _group_by_4(
    nets: List[Tuple[int, np.ndarray]],
) -> List[List[Tuple[int, np.ndarray]]]:
    """
    Assign each measured net to its canonical group slot.
    Groups that have no measured nets are included as empty lists so that
    group IDs stay aligned with _canonical_groups().
    """
    net_lookup: Dict[int, np.ndarray] = dict(nets)
    return [
        [(n, net_lookup[n]) for n in slot if n in net_lookup]
        for slot in _canonical_groups()
    ]


def _avg_group(group: List[Tuple[int, np.ndarray]]) -> np.ndarray:
    return np.mean(np.vstack([s for _, s in group]), axis=0)


def _make_sort_index(
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]],
) -> Dict[Tuple[float, int], int]:
    """
    Rank non-empty ambient-temperature groups by mean s21_db (lowest -> rank 1).
    Returns (temperature, group_id) -> SortIndex.
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
    return {key: rank + 1 for rank, (key, _) in enumerate(ordered)}


def _ordered_groups(
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]],
    idx_map: Dict[Tuple[float, int], int],
) -> List[Tuple[float, int, List[Tuple[int, np.ndarray]]]]:
    """
    Return all (temp, gid, group) triples sorted by SortIndex.
    Non-ambient groups are placed after all ambient groups.
    """
    beyond = max(idx_map.values(), default=0) + 1
    flat = [
        (idx_map.get((temp, gid), beyond), temp, gid, group)
        for temp, groups in temp_groups.items()
        for gid, group in enumerate(groups)
    ]
    flat.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(temp, gid, group) for _, temp, gid, group in flat]


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


def _sort_net(sort_index: int, pos_in_group: int) -> int:
    """Convert a 1-based group sort_index and 0-based intra-group position to a
    globally unique SortNet value in 1..NUM_NETS.  Returns 0 for unsorted blocks
    (sort_index == 0, i.e. non-ambient temperature groups)."""
    if sort_index == 0:
        return 0
    return 4 * (sort_index - 1) + pos_in_group + 1


def _build_sparam_blocks(
    freq: np.ndarray,
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]],
    full_map: Dict[Tuple[float, int], Dict[str, np.ndarray]],
    idx_map: Dict[Tuple[float, int], int],
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    blocks = []
    for temp, gid, _ in _ordered_groups(temp_groups, idx_map):
        group_sort_index = idx_map.get((temp, gid), 0)
        for pos, net in enumerate(_canonical_groups()[gid]):
            blk = full_map.get((temp, net))
            if blk is None:
                continue
            meta = {
                "SortNet": _sort_net(group_sort_index, pos),
                "!Net": net,
                "Temperature": temp,
            }
            rows = [
                {"freq": float(f), **{col: float(arr[i]) for col, arr in blk.items() if col != "freq"}}
                for i, f in enumerate(freq)
            ]
            blocks.append((meta, rows))
    return blocks


def _build_nf_blocks(
    nf_freq: np.ndarray,
    nf_map: Dict[Tuple[float, int], Dict[str, np.ndarray]],
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]],
    idx_map: Dict[Tuple[float, int], int],
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Write one NF block per net, in the same group order as the S-param output."""
    blocks = []
    for temp, gid, _ in _ordered_groups(temp_groups, idx_map):
        group_sort_index = idx_map.get((temp, gid), 0)
        for pos, net in enumerate(_canonical_groups()[gid]):
            blk = nf_map.get((temp, net))
            if blk is None:
                continue
            meta = {
                "SortNet": _sort_net(group_sort_index, pos),
                "!Net": net,
                "Temperature": temp,
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
    freq, temp_data, full_map = _load(in_mdif)
    temp_groups = {t: _group_by_4(lst) for t, lst in temp_data.items()}
    idx_map = _make_sort_index(temp_groups)

    sparam_blocks = _build_sparam_blocks(freq, temp_groups, full_map, idx_map)
    write_mdif(out_mdif, blocks=sparam_blocks, header_tokens=SPARAM_HEADER)
    print(f"Written sorted S-parameter data to {out_mdif}")

    if nf_in_mdif and nf_out_mdif:
        nf_freq, nf_map = _load_nf(nf_in_mdif)
        nf_blocks = _build_nf_blocks(nf_freq, nf_map, temp_groups, idx_map)
        write_mdif(nf_out_mdif, blocks=nf_blocks, header_tokens=NF_HEADER)
        print(f"Written sorted NF data to {nf_out_mdif}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sort RDI net S-param (and optionally NF) MDIF by ambient gain."
    )
    p.add_argument("--input",     type=Path, help="Input S-parameter MDIF file.")
    p.add_argument("--output",    type=Path, help="Output S-parameter MDIF file.")
    p.add_argument("--input-nf",  type=Path, help="Input NF MDIF file (optional).")
    p.add_argument("--output-nf", type=Path, help="Output NF MDIF file (optional).")
    return p.parse_args()


if __name__ == "__main__":
    print("=" * 40)
    print(" RDI Net Sorting")
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
