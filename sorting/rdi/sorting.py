#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
rf_measurements.4pack.sorting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Read an MDIF file that contains many “Net” blocks, group the nets
four‑by‑four (ordered by their Net number), average the *s21_db* column
inside each group and write the result into a new MDIF file.

The script can also be used as a tiny CLI – just run it without
arguments and answer the prompts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import numpy as np

# ----------------------------------------------------------------------
# MDIF writing utilities
# ----------------------------------------------------------------------


def _calc_col_widths(
    header: List[str],
    rows: List[Dict[str, Any]],
    padding: int = 2,
) -> List[int]:
    """
    Return a list of column widths that are wide enough for the header
    tokens *and* the longest formatted value in the rows.

    The ``header`` list contains the **raw** tokens that appear in the
    ACDATA header line (e.g. ``%freq(real)``).  ``rows`` is a list of
    ``dict`` objects whose keys are the *clean* column names (e.g.
    ``freq``).  The function therefore has to map a header token to the
    corresponding dictionary key – the same rule that is used later
    when writing the data rows.
    """
    widths = [len(tok) + padding for tok in header]

    for row in rows:
        formatted = []
        for tok in header:
            key = re.sub(r"[^\w]", "", tok).lower().replace("real", "")
            val = row.get(key, "")
            if isinstance(val, float):
                formatted.append(f"{val:.6g}")
            else:
                formatted.append(str(val))
        widths = [max(w, len(v) + padding) for w, v in zip(widths, formatted)]

    return widths


def write_mdif(
    out_path: Path,
    blocks: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]],
    header_tokens: List[str],
    comments: Optional[List[str]] = None,
    kind: str = "",
) -> None:
    """
    Write a combined MDIF file.

    Parameters
    ----------
    out_path
        Destination file.
    blocks
        List of ``(meta_dict, rows)`` tuples.  ``meta_dict`` may contain any
        VAR you need (Temperature, SortIndex, …).  If a key starts with
        ``!`` the line is written as a commented‑out VAR (this is used
        for the original Net number).
    header_tokens
        The *raw* tokens that appear in the ACDATA header line – they are
        kept verbatim in the output file.
    comments
        Optional free‑form comment lines that will be written at the very
        top of the file (each line prefixed with “! ”).
    kind
        Unused – kept for backward compatibility with the original
        helper.
    """
    lines: List[str] = []

    if comments:
        for c in comments:
            lines.append(f"! {c}\n")
        lines.append("\n")  # blank line separates comments from data

    for meta, rows in blocks:
        # ----- VAR lines -------------------------------------------------
        for var_name, value in meta.items():
            if var_name.startswith("!"):
                # keep the original Net number as a comment
                lines.append(f"! VAR {var_name[1:]}(real) = {value}\n")
            else:
                lines.append(f"VAR {var_name}(real) = {value}\n")

        lines.append("BEGIN ACDATA\n")

        # ----- column header ---------------------------------------------
        col_widths = _calc_col_widths(header_tokens, rows, padding=2)
        header_line = "".join(tok.ljust(w) for tok, w in zip(header_tokens, col_widths))
        lines.append(header_line.rstrip() + "\n")

        # ----- data rows -------------------------------------------------
        for row in rows:
            values: List[str] = []
            for tok in header_tokens:
                key = re.sub(r"[^\w]", "", tok).lower().replace("real", "")
                val = row.get(key, "")
                if isinstance(val, float):
                    values.append(f"{val:.6g}")
                else:
                    values.append(str(val))
            line = "".join(v.ljust(w) for v, w in zip(values, col_widths)).rstrip()
            lines.append(line + "\n")

        lines.append("END\n\n")

    out_path.write_text("".join(lines))
    if out_path.stat().st_size == 0:
        raise IOError(f"Failed to write combined MDIF file {out_path}")


# ----------------------------------------------------------------------
# MDIF reading utilities
# ----------------------------------------------------------------------


def _clean_header(tok: str) -> str:
    """Remove the leading “%” and an optional “(real)” suffix."""
    if tok.startswith("%"):
        tok = tok[1:]
    return re.sub(r"\(real\)", "", tok, flags=re.IGNORECASE).strip()


def read_mdif(file_path: Path) -> Tuple[np.ndarray, List[Dict[str, np.ndarray]]]:
    """
    Read an MDIF file.

    Returns
    -------
    meta
        1‑D ``np.ndarray`` (dtype=object) where each element is a dict with
        the VAR entries of a block (the “(real)” suffix has been stripped).
    data_blocks
        List – one dict per BEGIN … END block.  Each dict maps a *clean*
        column header name (e.g. ``freq`` or ``s21_db``) to a 1‑D
        ``np.ndarray`` containing the column values for that block.
    """
    lines = Path(file_path).read_text().splitlines()
    meta: List[Dict[str, Any]] = []                # VAR dictionaries
    data_blocks: List[Dict[str, np.ndarray]] = []  # per‑block column data

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # ------------------------------------------------- VAR block
        if line.upper().startswith("VAR"):
            cur: Dict[str, Any] = {}
            while i < len(lines) and lines[i].strip().upper().startswith("VAR"):
                m = re.match(r"VAR\s+([\w]+)(?:\s*\(.*?\))?\s*=\s*(.+)", lines[i].strip(), re.I)
                if m:
                    name = m.group(1)                     # already without “(real)”
                    cur[name] = float(m.group(2))
                i += 1
            meta.append(cur)
            continue

        # ------------------------------------------------- DATA block
        if line.upper().startswith("BEGIN"):
            i += 1  # the line *after* BEGIN is the header
            raw_header = lines[i].strip().split()
            header = [_clean_header(tok) for tok in raw_header]

            i += 1
            rows: List[List[float]] = []
            while i < len(lines) and not lines[i].strip().upper().startswith("END"):
                if lines[i].strip():
                    rows.append([float(v) for v in lines[i].split()])
                i += 1

            block_arr = np.array(rows, dtype=float) if rows else np.empty((0, len(header)))
            block_dict: Dict[str, np.ndarray] = {}
            for idx, name in enumerate(header):
                block_dict[name] = (
                    block_arr[:, idx] if block_arr.size else np.empty(0, dtype=float)
                )
            data_blocks.append(block_dict)

        i += 1

    return np.array(meta, dtype=object), data_blocks


# ----------------------------------------------------------------------
# Core processing helpers
# ----------------------------------------------------------------------


def _load(mdif_path: Path) -> Tuple[np.ndarray, Dict[float, List[Tuple[int, np.ndarray]]]]:
    """
    Convert the raw MDIF structure into a convenient representation:

    * ``freq`` – the (common) frequency vector (taken from the first block)
    * ``data`` – ``{temperature: [(net, s21_db), …]}``
    """
    meta, blocks = read_mdif(mdif_path)

    # All blocks are assumed to have the same frequency axis
    freq = blocks[0]["freq"]

    data: Dict[float, List[Tuple[int, np.ndarray]]] = {}
    for m, b in zip(meta, blocks):
        temperature = float(m["Temperature"])
        net = int(m["Net"])
        data.setdefault(temperature, []).append((net, b["s21_db"]))
    return freq, data


def _group_by_4(ordered_nets: List[Tuple[int, np.ndarray]]) -> List[List[Tuple[int, np.ndarray]]]:
    """
    Split a *sorted* list of ``(net, s21_array)`` into groups of four.
    The final chunk is kept even if it contains < 4 entries – the
    averaging code works for any size > 0.
    """
    ordered_nets.sort(key=lambda x: x[0])          # sort by Net number
    return [ordered_nets[i:i + 4] for i in range(0, len(ordered_nets), 4)]


def _avg_group(group: List[Tuple[int, np.ndarray]]) -> np.ndarray:
    """
    Element‑wise average of the *s21_db* arrays that belong to one 4‑Net group.
    """
    stack = np.vstack([s for _, s in group])
    return np.mean(stack, axis=0)


def _make_sort_index(
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]]
) -> Dict[Tuple[float, int], int]:
    ambient = {23.0, 25.0}
    ambient_means = {}
    for temp, groups in temp_groups.items():
        if temp not in ambient:
            continue
        for gid, group in enumerate(groups):
            ambient_means[(temp, gid)] = np.mean(_avg_group(group))

    if not ambient_means:
        return {}

    ordered = sorted(ambient_means.items(), key=lambda kv: kv[1])
    return {key: rank + 1 for rank, (key, _) in enumerate(ordered)}


def _flatten_and_sort(
    temp_groups: Dict[float, List[List[Tuple[int, np.ndarray]]]],
    idx_map: Dict[Tuple[float, int], int],
) -> List[Tuple[float, int, List[Tuple[int, np.ndarray]]]]:
    """
    Return a list ``[(temp, gid, group), …]`` ordered by the SortIndex
    (ambient groups first, lowest index → first).  Non‑ambient groups
    receive index 0 and therefore appear after the sorted ambient groups.
    """
    flat: List[Tuple[int, float, int, List[Tuple[int, np.ndarray]]]] = []
    max_idx = max(idx_map.values(), default=0) + 1            # index for “other”

    for temp, groups in temp_groups.items():
        for gid, group in enumerate(groups):
            idx = idx_map.get((temp, gid), max_idx)           # ambient → real idx,
                                                             # others → large idx
            flat.append((idx, temp, gid, group))

    flat.sort(key=lambda x: (x[0], x[1], x[2]))                # sort by idx first
    return [(temp, gid, group) for _, temp, gid, group in flat]

# ----------------------------------------------------------------------
# Main driver
# ----------------------------------------------------------------------


def main(in_mdif: Path, out_mdif: Path) -> None:
    freq, temp_data = _load(in_mdif)

    # split each temperature into groups of four nets
    temp_groups = {t: _group_by_4(lst) for t, lst in temp_data.items()}

    # compute SortIndex for ambient groups
    idx_map = _make_sort_index(temp_groups)

    # reorder groups so that iteration follows the SortIndex
    ordered = _flatten_and_sort(temp_groups, idx_map)

    # build blocks – they are already in the correct order
    blocks: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for temp, gid, group in ordered:
        avg_gain = _avg_group(group)
        rows = [{"freq": f, "s21_avg_db": g} for f, g in zip(freq, avg_gain)]

        meta: Dict[str, Any] = {
            "SortIndex": idx_map.get((temp, gid), 0),
            "!Net": group[0][0],          # keep the first Net as a commented VAR
            "Temperature": temp
        }
        blocks.append((meta, rows))

    write_mdif(
        out_mdif,
        blocks=blocks,
        header_tokens=["%freq(real)", "s21_avg_db(real)"],
    )


# ----------------------------------------------------------------------
# Small interactive CLI (kept identical to the original script)
# ----------------------------------------------------------------------


def clean(inp: str) -> str:
    """Remove surrounding quotes and surrounding whitespace."""
    s = inp.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def ask(prompt_msg: str, check) -> str:
    """Repeatedly ask until *check* returns (True, value)."""
    while True:
        ans = clean(input(prompt_msg + ": "))
        ok, val = check(ans)
        if ok:
            return val
        print(f"x  {val}")


# --------------------- validation helpers ---------------------


def must_be_dir(p: str):
    d = Path(p)
    if d.is_dir():
        return True, d
    return False, f"Directory does not exist → {d}"


def must_be_mdif_file(p: str):
    f = Path(p)
    if not f.is_file():
        return False, f"File not found → {f}"
    if f.suffix.lower() != ".mdif":
        return False, "File must end with .mdif"
    return True, f


def good_mdif_name(name: str):
    if not name:
        return False, "Filename cannot be empty"
    if any(c in name for c in "/\\"):
        return False, "Filename must not contain path separators"
    if not name.lower().endswith(".mdif"):
        name += ".mdif"
    return True, name


def safe_out_dir(p: str):
    d = Path(p)
    if d.is_dir():
        return True, d
    # ask to create it
    ans = input(f"Output directory '{d}' does not exist. Create it? [y/N]: ").strip().lower()
    if ans not in {"y", "yes"}:
        return False, f"Directory not created → {d}"
    try:
        d.mkdir(parents=True)
        return True, d
    except Exception as e:
        return False, f"Failed to create directory: {e}"


# ----------------------------------------------------------------------


if __name__ == "__main__":
    print("=============================")
    print("rf_measurements.rdi.sorting")
    print("=============================")

    # input directory
    in_dir = ask(
        "Enter base directory containing the input .mdif file",
        must_be_dir,
    )

    # input file name (joined with the directory)
    in_name = ask(
        "Enter file name of the input .mdif file",
        good_mdif_name,
    )
    in_path = Path(in_dir, in_name)

    ok, msg = must_be_mdif_file(str(in_path))
    if not ok:
        print(f"❌  {msg}")
        sys.exit(1)

    # output directory
    out_dir = ask(
        "Enter desired directory for the output .mdif file",
        safe_out_dir,
    )

    # output file name
    out_name = ask(
        "Enter file name of the output .mdif file",
        good_mdif_name,
    )
    out_path = Path(out_dir, out_name)

    main(in_path, out_path)
    print(f"Written averaged data to {out_path}")