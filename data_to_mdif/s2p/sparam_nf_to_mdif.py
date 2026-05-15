#!/usr/bin/env python3
r"""
sparam_nf_to_mdif.py

Convert the S‑parameter CSV files (RAW & PROCESSED) together with their matching
NF CSV files into two MDIF files that follow the specified layout:

    VAR SN(real) = <serial‑number>
    VAR Path(real) = <path‑number>
    VAR Temperature(real) = <temperature>
    BEGIN ACDATA
    %freq(real) s11_db(real) s11_deg(real) s21_db(real) s21_deg(real) \
      s12_db(real) s12_deg(real) s22_db(real) s22_deg(real) nf_db(real)

"""

# -------------------------------------------------------------------------
# Imports + logging – exactly the same as the original script 
# -------------------------------------------------------------------------
import argparse
import csv
import datetime
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


_file_handler = logging.FileHandler("4pack_sparam_nf.log", mode="w")
_file_handler.setLevel(logging.WARNING)          # capture everything
_file_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_file_handler.setFormatter(_file_fmt)
logger.addHandler(_file_handler)
# -------------------------------------------------------------------------
# Simple immutable containers (unchanged)                              
# -------------------------------------------------------------------------
@dataclass(frozen=True)
class NetFolder:
    """Kept only because other helpers use the same type; we will never create it."""
    name: str
    path: Path


# -------------------------------------------------------------------------
# Data structures for the two CSV families
# -------------------------------------------------------------------------
@dataclass
class SParamRow:
    freq_hz: int
    s11_db: float
    s11_deg: float
    s21_db: float
    s21_deg: float
    s12_db: float
    s12_deg: float
    s22_db: float
    s22_deg: float


@dataclass
class NFRow:
    freq_hz: int
    nf_db: float


# -------------------------------------------------------------------------
# parsing CSVs
# -------------------------------------------------------------------------
def _parse_sparam_csv(csv_path: Path) -> Tuple[int, int, List[SParamRow]]:
    """
    Parse a S‑parameter CSV, RAW or PROCESSED.

    Returns
        path_num    – numeric RF path extracted from the “path” column
        temp        – temperature (int) extracted from the “temp” column
        rows        – list of SParamRow objects (one per frequency point)
    """
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)

        rows: List[SParamRow] = []
        temp = None

        stem = csv_path.stem                      # file name without extension
        m = re.search(r"PATH\s*[-_]?\s*(\d+)", stem, re.IGNORECASE)
        if not m:
            raise ValueError(f"Cannot parse Path from file name '{csv_path.name}'")
        path_num = int(m.group(1))
            

        for i, row in enumerate(reader, start=2):   # start=2 → line number w.r.t. file
            # ---------------------------------------------------------
            # Grab path and temperature – they are the same for all rows,
            # so we store them the first time we see them.
            # ---------------------------------------------------------

            if temp is None:
                raw_temp = row.get("temp")
                if raw_temp is None:
                    raise ValueError(f"Missing 'temp' column in {csv_path}")
                temp = int(float(raw_temp))

            # ---------------------------------------------------------
            # Frequency (mandatory)
            # ---------------------------------------------------------
            try:
                freq_hz = int(float(row["Freq"]))
            except Exception as exc:
                raise ValueError(f"Bad or missing 'Freq' on line {i} of {csv_path}") from exc

            # ---------------------------------------------------------
            # The eight S‑parameter columns – they are always present in the
            # files you posted.
            # ---------------------------------------------------------
            try:
                srow = SParamRow(
                    freq_hz=freq_hz,
                    s11_db=float(row["S11dB"]),
                    s11_deg=float(row["S11deg"]),
                    s21_db=float(row["S21dB"]),
                    s21_deg=float(row["S21deg"]),
                    s12_db=float(row["S12dB"]),
                    s12_deg=float(row["S12deg"]),
                    s22_db=float(row["S22dB"]),
                    s22_deg=float(row["S22deg"]),
                )
            except KeyError as exc:
                raise ValueError(
                    f"Missing column {exc} in {csv_path} (line {i})"
                ) from exc

            rows.append(srow)

        if path_num is None or temp is None:
            raise RuntimeError(f"Could not extract Path/Temp from {csv_path}")

        return path_num, temp, rows
    
def _parse_nf_csv(csv_path: Path) -> Tuple[int, int, List[NFRow]]:
    """
    Parse a *NF* CSV.  The header of the file you posted looks like:

        Freq (Hz),dB,sn,path,temp

    Returns
        path_num    – numeric RF path extracted from the “path” column
        temp        – temperature (int) extracted from the “temp” column
        rows        – list of NFRow objects
    """
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)

        rows: List[NFRow] = []
        temp = None

        stem = csv_path.stem                      # file name without extension
        m = re.search(r"PATH\s*[-_]?\s*(\d+)", stem, re.IGNORECASE)
        if not m:
            raise ValueError(f"Cannot parse Path from file name '{csv_path.name}'")
        path_num = int(m.group(1))

        for i, row in enumerate(reader, start=2):


            if temp is None:
                raw_temp = row.get("temp")
                if raw_temp is None:
                    raise ValueError(f"Missing 'temp' column in {csv_path}")
                temp = int(float(raw_temp))

            try:
                freq_hz = int(float(row["Freq (Hz)"]))
                nf_db = float(row["dB"])
            except Exception as exc:
                raise ValueError(
                    f"Bad or missing frequency/NF on line {i} of {csv_path}"
                ) from exc

            rows.append(NFRow(freq_hz=freq_hz, nf_db=nf_db))

        if path_num is None or temp is None:
            raise RuntimeError(f"Could not extract Path/Temp from {csv_path}")

        return path_num, temp, rows



def _calc_col_widths(
    header_tokens: List[str],
    rows: List[Tuple[int, List[float ]]],
    padding: int = 1,
) -> List[int]:
    """
    Return a list of column widths that are wide enough for the header *and*
    the longest formatted value in that column.  ``rows`` is a list of
    ``(freq_hz, [v1, v2, …])`` tuples; a value may be ``None`` (the NF column
    when no NF data exists).
    """
    widths = [len(tok) + padding for tok in header_tokens]

    for freq_hz, values in rows:
        # column 0 – frequency (always an int)
        freq_str = f"{freq_hz}"
        widths[0] = max(widths[0], len(freq_str) + padding)

        # remaining columns – format numbers, or an empty string if None
        for i, v in enumerate(values, start=1):
            val_str = "" if v is None else f"{v:.6g}"
            widths[i] = max(widths[i], len(val_str) + padding)

    return widths


# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
def _write_mdif_generic(
    out_path: Path,
    groups: Dict[Tuple[int, int, int], List[Tuple[int, List[float]]]],
    header_tokens: List[str],
) -> None:
    """
    Write a MDIF file for an arbitrary set of columns.

    * ``groups`` – keyed by (sn, path, temperature) → list of rows.
      Each row is ``(freq_hz, [col1, col2, …])`` where a column may be ``None``
      (e.g. missing NF value – the column will be left blank).

    * ``header_tokens`` – the list of column names that will appear after
      ``BEGIN ACDATA``.  The first token must be the frequency column
      (``%freq(real)``) – the function does not enforce it, it just uses the
      list you give it.

    The function uses the existing ``_calc_col_widths`` helper to compute a
    column‑width for each column and then left‑aligns every value under its
    header, exactly as you requested.
    """
    lines: List[str] = []

    for (sn, path_num, temp), rows in groups.items():
        # -----------------------------------------------------------
        # Block header
        # -----------------------------------------------------------
        lines.append(f"VAR SN(real) = {sn}\n")
        lines.append(f"VAR Path(real) = {path_num}\n")
        lines.append(f"VAR Temperature(real) = {temp}\n")
        lines.append("BEGIN ACDATA\n")

        # -----------------------------------------------------------
        # Column widths (once per block)
        # -----------------------------------------------------------
        col_widths = _calc_col_widths(header_tokens, rows, padding=2)

        # -----------------------------------------------------------
        # Header line – left‑aligned
        # -----------------------------------------------------------
        header_line = "".join(tok.ljust(w) for tok, w in zip(header_tokens, col_widths))
        lines.append(header_line.rstrip() + "\n")

        # -----------------------------------------------------------
        # Data rows – left‑aligned, blank for ``None``
        # -----------------------------------------------------------
        for freq_hz, values in rows:
            row_items = [f"{freq_hz}"]
            for v in values:
                row_items.append("" if v is None else f"{v:.6g}")

            row_line = "".join(item.ljust(w) for item, w in zip(row_items, col_widths))
            lines.append(row_line.rstrip() + "\n")

        lines.append("END\n\n")    # blank line between blocks

    out_path.write_text("".join(lines))
    if out_path.stat().st_size == 0:
        raise IOError(f"Failed to write MDIF file {out_path}")

# -------------------------------------------------------------------------
# CLI handling – temperature argument removed, interactive fallback kept
# -------------------------------------------------------------------------
def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert S‑parameter + NF CSVs into two MDIF files "
                    "(RAW and PROCESSED) with per‑file temperature."
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        help="Root directory that already contains the RXEM folders "
             "(RXEM1‑XXXXX, …)."
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        help="Directory where the two MDIF files will be written."
    )
    return parser.parse_args()


# -------------------------------------------------------------------------
# Main driver – **no net discovery any more**.  All CSVs are read directly
# from each RXEM folder.
# -------------------------------------------------------------------------
def main() -> None:
    args = _parse_cli()

    # -------------------------------------------------------------
    # Interactive fallback for mandatory arguments
    # -------------------------------------------------------------
    base_path: Path = args.base_path or Path(
        input("Base directory containing RXEM folders (e.g. …/RXEM1-000019): ").strip()
    )
    output_path: Path = args.output_path or Path(
        input("Directory where the MDIF files should be written: ").strip()
    )
    if not base_path.is_dir():
        raise NotADirectoryError(f"The supplied base_path does not exist: {base_path}")
    output_path.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # Find all RXEM folders – they follow the pattern RXEM<number>-<serial>
    # -------------------------------------------------------------
    rxem_dirs = [
        p for p in base_path.iterdir()
        if p.is_dir() and re.match(r"RXEM\d+-\d+$", p.name, re.IGNORECASE)
    ]
    if not rxem_dirs:
        raise FileNotFoundError("No RXEM folders (RXEM<...>) found under the base path.")
    logger.info(f"Found {len(rxem_dirs)} RXEM families.")

    # -----------------------------------------------------------------
    # Four containers: RAW/PROCESSED × (S‑parameter / NF)
    # key = (sn, path, temperature)  →  list of (freq_hz, [values])
    # -----------------------------------------------------------------
    sparam_raw:   Dict[Tuple[int, int, int], List[Tuple[int, List[float]]]] = {}
    sparam_proc:  Dict[Tuple[int, int, int], List[Tuple[int, List[float]]]] = {}
    nf_raw:       Dict[Tuple[int, int, int], List[Tuple[int, List[float]]]] = {}
    nf_proc:      Dict[Tuple[int, int, int], List[Tuple[int, List[float]]]] = {}

    # -------------------------------------------------------------
    # Walk every RXEM folder and process its CSV files
    # -------------------------------------------------------------
    for rxem in rxem_dirs:
        logger.info(f"Scanning {rxem.name}")

        # ----- SN comes from the folder name (strip leading zeros) -----
        try:
            folder_sn = int(rxem.name.split("-")[-1].lstrip("0") or "0")
        except Exception as exc:
            logger.error(f"Could not parse SN from folder name {rxem.name}: {exc}")
            continue

        # All CSV files that live directly in the RXEM folder
        csv_files = sorted(rxem.glob("*.csv"))
        if not csv_files:
            logger.debug(f"No CSV files in {rxem}")
            continue

        for csv_path in csv_files:
            name_up = csv_path.name.upper()

            if "S-PARAMETERS_RAW" in name_up:
                bucket = sparam_raw
                is_sparam = True
                is_raw = True
            elif "S-PARAMETERS_PROCESSED" in name_up:
                bucket = sparam_proc
                is_sparam = True
                is_raw = False
            elif "NF_RAW" in name_up:
                bucket = nf_raw
                is_sparam = False
                is_raw = True
            elif "NF_PROCESSED" in name_up:
                bucket = nf_proc
                is_sparam = False
                is_raw = False
            else:
                # Not a file we care about
                continue

            try:
                if is_sparam:
                    # S‑parameter CSV – we need *all eight* parameters
                    path_num, temp, s_rows = _parse_sparam_csv(csv_path)
                    # Convert each SParamRow to a flat list of 8 floats
                    for s in s_rows:
                        values = [
                            s.s11_db, s.s11_deg,
                            s.s21_db, s.s21_deg,
                            s.s12_db, s.s12_deg,
                            s.s22_db, s.s22_deg,
                        ]
                        key = (folder_sn, path_num, temp)
                        bucket.setdefault(key, []).append((s.freq_hz, values))
                else:
                    # NF CSV – only a single dB column
                    path_num, temp, nf_rows = _parse_nf_csv(csv_path)
                    for nf in nf_rows:
                        values = [nf.nf_db]            # one column
                        key = (folder_sn, path_num, temp)
                        bucket.setdefault(key, []).append((nf.freq_hz, values))
            except Exception as exc:
                # -------------------------------------------------
                # Any parsing problem → write a warning to the error log
                # -------------------------------------------------
                logger.warning(f"Skipping malformed CSV {csv_path}: {exc}")
                continue


    logger.setLevel(logging.INFO)
    # -----------------------------------------------------------------
    # Write the four MDIF files
    # -----------------------------------------------------------------
    # ---- S‑parameter RAW -------------------------------------------------
    if sparam_raw:
        out_path = output_path / "4PACKS_SPARAMS_RAW.mdif"
        logger.info(f"Writing S‑parameter RAW MDIF → {out_path}")
        header = [
            "%freq(real)",
            "s11_db(real)", "s11_deg(real)",
            "s21_db(real)", "s21_deg(real)",
            "s12_db(real)", "s12_deg(real)",
            "s22_db(real)", "s22_deg(real)",
        ]
        _write_mdif_generic(out_path, sparam_raw, header)
    else:
        logger.info("No S‑parameter RAW data found – file will not be created.")

    # ---- S‑parameter PROCESSED -----------------------------------------
    if sparam_proc:
        out_path = output_path / "4PACKS_SPARAMS_PROCESSED.mdif"
        logger.info(f"Writing S‑parameter PROCESSED MDIF → {out_path}")
        header = [
            "%freq(real)",
            "s11_db(real)", "s11_deg(real)",
            "s21_db(real)", "s21_deg(real)",
            "s12_db(real)", "s12_deg(real)",
            "s22_db(real)", "s22_deg(real)",
        ]
        _write_mdif_generic(out_path, sparam_proc, header)
    else:
        logger.info("No S‑parameter PROCESSED data found – file will not be created.")

    # ---- NF RAW ---------------------------------------------------------
    if nf_raw:
        out_path = output_path / "4PACKS_NF_RAW.mdif"
        logger.info(f"Writing NF RAW MDIF → {out_path}")
        header = ["%freq(real)", "nf_db(real)"]
        _write_mdif_generic(out_path, nf_raw, header)
    else:
        logger.info("No NF RAW data found – file will not be created.")

    # ---- NF PROCESSED ----------------------------------------------------
    if nf_proc:
        out_path = output_path / "4PACKS_NF_PROCESSED.mdif"
        logger.info(f"Writing NF PROCESSED MDIF → {out_path}")
        header = ["%freq(real)", "nf_db(real)"]
        _write_mdif_generic(out_path, nf_proc, header)
    else:
        logger.info("No NF PROCESSED data found – file will not be created.")

    logger.info("All MDIF files have been written.")


if __name__ == "__main__":
    main()