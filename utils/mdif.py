"""MDIF‑writing helper used by all converters."""

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import numpy as np


def _calc_col_widths(header: List[str],
                     rows: List[Dict[str, Any]],
                     padding: int = 2) -> List[int]:
    """Column widths wide enough for the header and the longest formatted value."""
    widths = [len(tok) + padding for tok in header]
    for row in rows:
        vals = []
        for tok in header:
            key = re.sub(r"[^\w]", "", tok).lower().replace("real", "")
            val = row.get(key, "")
            if isinstance(val, float):
                vals.append(f"{val:.6g}")
            else:
                vals.append(str(val))
        widths = [max(w, len(v) + padding) for w, v in zip(widths, vals)]
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

    ``blocks`` – list of ``(meta_dict, rows)`` tuples.
    ``meta_dict`` can contain **any** VAR you need (SN, Temperature,
    SortIndex, …).  The writer iterates over the dict and writes a VAR line
    for each entry – no VAR names are hard‑coded.
    ``header_tokens`` – column names that will appear in the ACDATA section.
    """
    lines: List[str] = []

    if comments:
        for c in comments:
            lines.append(f"! {c}\n")
        lines.append("\n")                     # blank line separates comments from data

    for meta, rows in blocks:
        # ----- VAR lines (all entries) ---------------------------------
        for var_name, value in meta.items():
            if var_name.startswith("!"): # deactivate it
                lines.append(f"! VAR {var_name[1:]}(real) = {value}\n") # strip off !
            else: 
                lines.append(f"VAR {var_name}(real) = {value}\n")

        lines.append("BEGIN ACDATA\n")

        # ----- column header --------------------------------------------
        col_widths = _calc_col_widths(header_tokens, rows, padding=2)
        header_line = "".join(tok.ljust(w) for tok, w in zip(header_tokens, col_widths))
        lines.append(header_line.rstrip() + "\n")

        # ----- data rows ------------------------------------------------
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
    

##############
# Read utilities
##############


def _clean_header(tok: str) -> str:
    """Remove leading ‘%’ and optional “(real)” suffix."""
    if tok.startswith("%"):
        tok = tok[1:]
    return re.sub(r"\(real\)", "", tok, flags=re.IGNORECASE).strip()


def read_mdif(file_path: Path) -> Tuple[np.ndarray, List[Dict[str, np.ndarray]]]:
    """
    Read an MDIF file.

    Returns
    -------
    meta : np.ndarray (object dtype)
        1‑D array where each element is a dict of the VAR entries for a block
        (the “(real)” suffix is stripped from the VAR names).

    data_blocks : list of dict
        One dict per BEGIN … END block.  Each dict maps a **cleaned**
        column header name (e.g. ``freq``, ``s21_db``) to a 1‑D ``np.ndarray``
        of the column values for that block.  The order of the list matches
        the order of the VAR blocks in the file.
    """
    lines = Path(file_path).read_text().splitlines()

    meta: List[Dict[str, Any]] = []                # VAR dictionaries
    data_blocks: List[Dict[str, np.ndarray]] = [] # per‑block column data

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # ----- VAR block -------------------------------------------------
        if line.startswith("VAR"):
            cur: Dict[str, Any] = {}
            while not line.upper().startswith("BEGIN"):
                m = re.match(r"VAR\s+([\w]+)(?:\s*\(.*?\))?\s*=\s*(.+)", line)
                if m:
                    name = re.sub(r"\(.*\)", "", m.group(1)).strip()
                    cur[name] = float(m.group(2))
                i += 1
                if i >= len(lines):
                    break
                line = lines[i].strip()
            meta.append(cur)
            continue

        # ----- DATA block (BEGIN … END) ---------------------------------
        if line.upper().startswith("BEGIN"):
            i += 1                                 # header line
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
                    block_arr[:, idx] if block_arr.size else np.array([], dtype=float)
                )
            data_blocks.append(block_dict)

        i += 1

    meta_arr = np.array(meta, dtype=object)
    return meta_arr, data_blocks