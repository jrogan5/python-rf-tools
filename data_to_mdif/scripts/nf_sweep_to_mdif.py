#!/usr/bin/env python3
r"""
nf_sweep_to_mdif.py

Read every NF‑sweep CSV that lives under
<base_path>/E1 , <base_path>/E2 , … and produce a **single** MDIF file
named `measured_<key>.mdif` in the base_path.

The script mirrors the structure of the original imd_sweep_to_mdif.py
so that anyone familiar with that tool will feel at home.
"""

# -------------------------------------------------------------------------
# Imports + logging (same as the original script)
# -------------------------------------------------------------------------
import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict

# -------------------------------------------------------------------------
# Logging configuration – mirrors the gain‑compression script
# -------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)   # ← added [1]

# -------------------------------------------------------------------------
# Configurable limits – edit here if you need a different temperature range
# -------------------------------------------------------------------------
TEMP_MIN: float = -100.0   # °C
TEMP_MAX: float = 100.0    # °C

# -------------------------------------------------------------------------
# Simple immutable containers
# -------------------------------------------------------------------------
@dataclass(frozen=True)
class NetFolder:
    """Folder that represents a net (e.g. E1 → net 1)."""
    name: str          # folder name, e.g. "E1"
    path: Path         # full path to the folder


@dataclass(frozen=True)
class NFRow:
    """One row of NF data that will be written to the MDIF."""
    frequency_hz: int
    nf_db: float


# -------------------------------------------------------------------------
# Helper utilities (identical to the imd script)
# -------------------------------------------------------------------------
def _net_number_from_folder(folder_name: str) -> int:
    """E1 → 1, E12 → 12 …"""
    match = re.fullmatch(r"E(\d+)", folder_name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Folder name '{folder_name}' does not match pattern 'E<number>'.")
    return int(match.group(1))                                           # [1]


def _prompt_missing(prompt: str, cast_type):
    """Ask the user for a value when the CLI argument was omitted."""
    while True:
        try:
            return cast_type(input(f"{prompt}: ").strip())
        except ValueError as exc:
            print(f"Invalid input – {exc}")


def _validate_temperature(temp: float) -> None:
    """Make sure the supplied temperature is inside the allowed range."""
    if not (TEMP_MIN <= temp <= TEMP_MAX):
        raise ValueError(
            f"Temperature {temp} °C is outside the allowed range "
            f"[{TEMP_MIN}, {TEMP_MAX}]"
        )                                                               # [1]


def _discover_net_folders(root: Path) -> List[NetFolder]:
    """Return a sorted list of NetFolder objects for every E* sub‑folder."""
    candidate_paths = [p for p in root.glob("E*") if p.is_dir()]
    sorted_paths = sorted(candidate_paths, key=lambda p: _net_number_from_folder(p.name))
    nets = [NetFolder(name=p.name, path=p) for p in sorted_paths]

    if not nets:
        raise FileNotFoundError(f"No net folders (E1, E2, …) found under {root}")
    return nets                                                       # [1]


def _parse_cli() -> argparse.Namespace:
    """CLI parser – same as the original, plus the optional “key”. """
    parser = argparse.ArgumentParser(
        description="Combine all NF‑sweep CSV files into a single MDIF file."
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        help="Root directory that already contains the net sub‑folders (E1, E2, …).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Test temperature in °C (must be inside the allowed range).",
    )
    parser.add_argument(
        "--key",
        type=str,
        default="NF",
        help="Key that appears in the CSV filename (default: NF).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed warnings / processing info.",
    )
    return parser.parse_args()                                         # [1]


# -------------------------------------------------------------------------
# Column names that belong to the NF‑CSV files (the original script used one)
# -------------------------------------------------------------------------
_FREQ_COL = "Freq(Hz)"                     # swept frequency (Hz)

# A small list of all NF‑column spellings we have ever seen.
# The parser will pick the first one that exists in the file.
_NF_COLUMN_CANDIDATES = (
    "NF(DB)",          # the “normal” name used by the original script
    "NF Log Mag(dB)", # the variant you posted in the question
    "NF(dB)",         # just in case
    "NF",             # very generic fallback
)

def _parse_nf_csv(csv_path: Path) -> List[NFRow]:
    """
    Reads a noise‑figure CSV (any of the formats you have) and returns a
    list of ``NFRow`` objects.

    The logic mirrors the original ``_parse_imd_csv``:
      * locate the header line that starts with the frequency column,
      * start reading data **one line after** the header (the NF files have
        no empty line between header and data),
      * build a ``csv.DictReader`` with the exact field names from the header,
      * figure out which column contains the NF value,
      * pull the required columns, skip malformed rows with a warning,
      * raise an error if no valid rows are found.
    """
    with csv_path.open("r", newline="") as f:
        all_lines = f.readlines()

    header_idx = None
    for i, line in enumerate(all_lines):
        # Strip leading comment characters (the “!” lines) and whitespace.
        if line.strip().startswith(_FREQ_COL):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(
            f"Header line starting with '{_FREQ_COL}' not found in {csv_path.name}"
        )  

    data_start = header_idx + 1

    # Build the list of column names exactly as they appear in the header.
    header_line = all_lines[header_idx].strip()
    field_names = [h.strip() for h in header_line.split(",")]

    reader = csv.DictReader(all_lines[data_start:], fieldnames=field_names)

    nf_column_name: str | None = None
    for cand in _NF_COLUMN_CANDIDATES:
        # Use case‑insensitive comparison because some files have different capitalisation.
        if any(cand.lower() == h.lower() for h in field_names):
            nf_column_name = next(h for h in field_names if h.lower() == cand.lower())
            break

    if nf_column_name is None:
        raise ValueError(
            f"None of the expected NF columns {list(_NF_COLUMN_CANDIDATES)} "
            f"found in {csv_path.name}. Available columns: {field_names}"
        )   # aborts the whole net if we cannot locate the NF column

    rows: List[NFRow] = []
    skipped = 0  

    for i, row in enumerate(reader, start=1):   # i = logical data‑line number 
        try:
            # ---- Frequency -------------------------------------------------
            # Some files store the frequency as an integer, some as a float string.
            freq_hz = int(float(row[_FREQ_COL]))

            # ---- NF value ---------------------------------------------------
            nf_db = float(row[nf_column_name])
        except KeyError as exc:

            logger.warning(
                f"{csv_path.name} – row {i}: missing column {exc}. Row skipped."
            )
            skipped += 1
            continue
        except (ValueError, TypeError) as exc:

            # logger.warning(
            #     f"{csv_path.name} – row {i}: non‑numeric value ({exc}). Row skipped."
            # )
            # skipped += 1
            continue

        rows.append(NFRow(freq_hz, nf_db))

    if skipped:
        logger.info(f"{csv_path.name}: skipped {skipped} malformed row(s).")
    if not rows:
        raise ValueError(f"No valid data rows found in {csv_path.name}")   # unchanged

    return rows

# -------------------------------------------------------------------------
# MDIF helpers (the column‑width logic is unchanged – see the original script)
# -------------------------------------------------------------------------
_MDIF_HEADER_TOKENS = ["%freq(real)", "nf_db(real)"]                     # [1]

def _calc_col_widths(
    header_tokens: List[str],
    rows: List[NFRow],
    padding: int = 1,
) -> List[int]:
    """Same algorithm as in the imd script – creates widths for header + data."""
    widths = [len(tok) + padding for tok in header_tokens]

    for r in rows:
        data_strs = [
            f"{r.frequency_hz}",
            f"{r.nf_db:.6g}",
        ]
        widths = [max(w, len(s) + padding) for w, s in zip(widths, data_strs)]
    return widths                                                   # [1]


def _write_combined_mdif(
    out_path: Path,
    temperature: float,
    net_data: List[Tuple[int, List[NFRow]]],
) -> None:
    """
    ``net_data`` is a list of tuples:
        (net_number, [NFRow, NFRow, …])
    The function writes **one** MDIF file that contains a section for each net.
    """
    lines: List[str] = []

    for net_number, rows in net_data:
        # ---------------------------------------------------------------
        # Net‑specific header
        # ---------------------------------------------------------------
        lines.append(f"VAR Net(real) = {net_number}\n")
        lines.append(f"VAR Temperature(real) = {temperature}\n")
        lines.append("BEGIN ACDATA\n")

        # ----- header line that aligns with the data columns -------------
        col_widths = _calc_col_widths(_MDIF_HEADER_TOKENS, rows, padding=2)
        header_line = "".join(tok.ljust(w) for tok, w in zip(_MDIF_HEADER_TOKENS, col_widths))
        lines.append(header_line.rstrip() + "\n")

        # ----- data rows ------------------------------------------------
        for r in rows:
            values = [
                f"{r.frequency_hz}",
                f"{r.nf_db:.6g}",
            ]
            row_line = "".join(val.ljust(w) for val, w in zip(values, col_widths))
            lines.append(row_line.rstrip() + "\n")

        lines.append("END\n")
        lines.append("\n")      # optional blank line between net sections

    out_path.write_text("".join(lines))
    if out_path.stat().st_size == 0:
        raise IOError(f"Failed to write combined MDIF file {out_path}")


# -------------------------------------------------------------------------
# Main orchestration – mirrors the imd script
# -------------------------------------------------------------------------
def main() -> None:
    args = _parse_cli()

    # -----------------------------------------------------------------
    # Logging level according to --verbose
    # -----------------------------------------------------------------
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # -----------------------------------------------------------------
    # Gather required information (CLI or interactive fallback)
    # -----------------------------------------------------------------
    base_path: Path = args.base_path or Path(
        _prompt_missing("Base directory containing net folders (E1, E2, …)", Path)
    )
    temperature: float = (
        args.temperature
        if args.temperature is not None
        else float(_prompt_missing("Temperature (°C)", float))
    )
    _validate_temperature(temperature)                                   # [1]

    key: str = args.key.strip()
    # Build a glob pattern that works whether the user supplied “NF” or “NF.csv”
    pattern = f"*{key}*.csv" if not key.lower().endswith(".csv") else f"*{key}"
    logger.info(f"Looking for files matching pattern: {pattern}")

    if not base_path.is_dir():
        raise NotADirectoryError(f"The supplied base_path does not exist: {base_path}")

    # --------------------------------------------------------------- #
    # Discover net folders
    # --------------------------------------------------------------- #
    nets = _discover_net_folders(base_path)                              # [1]

    # --------------------------------------------------------------- #
    # Containers for problem reporting (exactly what the imd script uses)
    # --------------------------------------------------------------- #
    bad_files: List[str] = []                     # flat list of all bad CSV paths
    nets_without_csv: List[str] = []              # nets that have no CSV at all
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    # --------------------------------------------------------------- #
    # Process every net
    # --------------------------------------------------------------- #
    all_net_data: List[Tuple[int, List[NFRow]]] = []
    for net in nets:
        csv_files = sorted(net.path.glob(pattern))
        if not csv_files:
            logger.info(f"[INFO] No '{pattern}' file found in {net.path} – skipping")
            nets_without_csv.append(net.name)
            continue

        csv_path = csv_files[0]          # we assume one file per net per key
        try:
            rows = _parse_nf_csv(csv_path)
            net_number = _net_number_from_folder(net.name)
            all_net_data.append((net_number, rows))
        except Exception as exc:
            exc_msg = str(exc)
            bad_files.append(str(csv_path))
            bad_files_by_net.setdefault(net.name, []).append((str(csv_path), exc_msg))
            logger.info(
                f"[INFO] Skipping malformed CSV file {csv_path} (net {net.name}): {exc_msg}"
            )
            continue

    # --------------------------------------------------------------- #
    # Write the combined MDIF file
    # --------------------------------------------------------------- #
    plots_dir = base_path / "plots"
    if not plots_dir.is_dir():
        plots_dir.mkdir(parents=True, exist_ok=True)

    mdif_path = plots_dir / f"measured_{key.replace('.csv', '')}.mdif"
    _write_combined_mdif(mdif_path, temperature, all_net_data)

    # --------------------------------------------------------------- #
    # Bad‑measurement report (exactly the same style as the imd script)
    # --------------------------------------------------------------- #
    if bad_files or nets_without_csv:
        bad_list_path = plots_dir / "nf_bad_measurements.txt"
        lines: List[str] = [
            "! ===========================\n",
            f"! NF sweep bad measurement report for pattern '{pattern}'\n",
            "! ===========================\n",
            "\n",
        ]

        if nets_without_csv:
            lines.append("! Nets that have NO NF CSV files (omitted from MDIF):\n")
            for net_name in sorted(nets_without_csv):
                lines.append(f"!    {net_name}\n")
            lines.append("\n")

        if bad_files_by_net:
            lines.append("! Nets that contain malformed NF CSV files (entire net omitted):\n")
            for net_name in sorted(bad_files_by_net):
                lines.append(f"!   Net {net_name}:\n")
                for file_path, err_msg in bad_files_by_net[net_name]:
                    safe_msg = err_msg.replace("\n", " | ")
                    lines.append(f"!         {file_path}\n")
                    lines.append(f"!         Reason: {safe_msg}\n")
                lines.append("\n")

            lines.append("\n!  Flat list of all bad CSV files (for scripts)\n")
            for p in bad_files:
                lines.append(f"{p}\n")

        bad_list_path.write_text("".join(lines))
        logger.info(f"A detailed bad measurement report has been written to: {bad_list_path}")

    # --------------------------------------------------------------- #
    # Human‑readable summary (mirrors the imd script)
    # --------------------------------------------------------------- #
    total_rows = sum(len(r) for _, r in all_net_data)
    logger.info("\n=== NF‑sweep aggregation finished ===")
    logger.info(f"Base path          : {base_path}")
    logger.info(f"Temperature (°C)   : {temperature}")
    logger.info(f"Nets processed     : {len(all_net_data)}")
    logger.info(f"Total CSV rows used: {total_rows}")
    logger.info(f"Combined MDIF written to: {mdif_path}")
    # logger.info("\nGenerated sections -- net (rows):")
    # for net_number, rows in all_net_data:
    #     logger.info(f"  Net {net_number}  ({len(rows)} rows)")


if __name__ == "__main__":
    # Any uncaught exception aborts the script – the same behaviour as the
    # original imd utility.
    main()