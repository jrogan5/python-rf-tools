#!/usr/bin/env python3
r"""
imd_sweep_to_mdif.py

Read every IMD‑sweep CSV that lives under
<base_path>\E1, <base_path>\E2, … and produce a **single** MDIF file named
`RDI_IMD_sweep.mdif` in the base_path.
"""

# -------------------------------------------------------------------------
# Imports + logging (new)
# -------------------------------------------------------------------------
import argparse
import csv
import datetime          # for the bad‑measurement time‑stamp
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# -------------------------------------------------------------------------
# Logging configuration – mirrors the gain‑compression script
# -------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)   # ← added

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
class SweepRow:
    """One row of processed data that will be written to the MDIF."""
    frequency_hz: int
    pout_dbm: float
    pin_dbm: float
    p3f: float
    gain_db: float
    imd3: float
    oip3: float
    iip3: float


# -------------------------------------------------------------------------
# CLI handling (with interactive fallback) – added --verbose flag
# -------------------------------------------------------------------------
def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine all IMD‑sweep CSVs into a single MDIF file."
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
        "--verbose",
        action="store_true",
        help="Print detailed warnings / processing info.",
    )
    return parser.parse_args()


def _prompt_missing(prompt: str, cast_type):
    """Ask the user for a value when the CLI argument was omitted."""
    while True:
        try:
            return cast_type(input(f"{prompt}: ").strip())
        except ValueError as exc:
            print(f"Invalid input – {exc}")


# -------------------------------------------------------------------------
# Temperature validation (already present)
# -------------------------------------------------------------------------
def _validate_temperature(temp: float) -> None:
    if not (TEMP_MIN <= temp <= TEMP_MAX):
        raise ValueError(
            f"Temperature {temp} °C is outside the allowed range "
            f"[{TEMP_MIN}, {TEMP_MAX}]"
        )


# -------------------------------------------------------------------------
# Net‑folder discovery (already present)
# -------------------------------------------------------------------------
def _discover_net_folders(root: Path) -> List[NetFolder]:
    candidate_paths = [p for p in root.glob("E*") if p.is_dir()]
    sorted_paths = sorted(candidate_paths, key=lambda p: _net_number_from_folder(p.name))
    nets = [NetFolder(name=p.name, path=p) for p in sorted_paths]

    if not nets:
        raise FileNotFoundError(f"No net folders (E1, E2, …) found under {root}")
    return nets


def _net_number_from_folder(folder_name: str) -> int:
    """
    Expected folder names are 'E1', 'E2', … → returns the integer part.
    If you rename the folders later, adjust this function only.
    """
    match = re.fullmatch(r"E(\d+)", folder_name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Folder name '{folder_name}' does not match pattern 'E<number>'.")
    return int(match.group(1))


# -------------------------------------------------------------------------
# CSV column names – change if your files use a different spelling
# -------------------------------------------------------------------------
_FREQ_COL = "FrequencyFC"   # swept frequency (Hz)
_PWR_MAIN = "PwrMain"       # → Pout_dBm
_PWR_IN   = "PwrMainIn"     # → Pin_dBm
_PWR_3    = "Pwr3"          # → P3f


# -------------------------------------------------------------------------
# Helper: calculate column widths (unchanged)
# -------------------------------------------------------------------------
def _calc_col_widths(
    header_tokens: List[str],
    rows: List[SweepRow],
    padding: int = 1,
) -> List[int]:
    """
    Return a list of column widths that are wide enough for the header *and*
    the longest formatted value in that column.
    """
    widths = [len(tok) + padding for tok in header_tokens]

    for r in rows:
        data_strs = [
            f"{r.frequency_hz:,}",
            f"{r.pout_dbm:.6g}",
            f"{r.pin_dbm:.6g}",
            f"{r.p3f:.6g}",
            f"{r.gain_db:.6g}",
            f"{r.imd3:.6g}",
            f"{r.oip3:.6g}",
            f"{r.iip3:.6g}",
        ]
        widths = [max(w, len(s) + padding) for w, s in zip(widths, data_strs)]

    return widths


# -------------------------------------------------------------------------
# Parse a single IMD‑sweep CSV – **new warning‑based handling**
# -------------------------------------------------------------------------
def _parse_imd_csv(csv_path: Path) -> List[SweepRow]:
    """
    Reads an IMD‑sweep CSV and returns a list of SweepRow objects.
    Malformed rows are reported as warnings and ignored – the script
    continues with the remaining good data (instead of aborting on the
    first problem).  This mirrors the behaviour of the gain‑compression script.
    """
    with csv_path.open("r", newline="") as f:
        all_lines = f.readlines()

    # -------------------------------------------------------------
    # Find the line that actually contains the column headers
    # -------------------------------------------------------------
    header_idx = None
    for i, line in enumerate(all_lines):
        if line.strip().startswith(_FREQ_COL):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(
            f"Header line starting with '{_FREQ_COL}' not found in {csv_path.name}"
        )                                            # unchanged

    data_start = header_idx + 2
    header_line = all_lines[header_idx].strip()
    field_names = [h.strip() for h in header_line.split(",")]
    reader = csv.DictReader(all_lines[data_start:], fieldnames=field_names)

    rows: List[SweepRow] = []
    skipped = 0  # ← counter of malformed rows

    for i, row in enumerate(reader):
        try:
            freq_hz = int(float(row[_FREQ_COL]))
            pout    = float(row[_PWR_MAIN])
            pin     = float(row[_PWR_IN])
            p3f     = float(row[_PWR_3])
        except KeyError as exc:
            logger.warning(
                f"{csv_path.name} – row {i+1}: missing column {exc}. Row skipped."
            )
            skipped += 1
            continue
        except ValueError as exc:
            logger.warning(
                f"{csv_path.name} – row {i+1}: non‑numeric value ({exc}). Row skipped."
            )
            skipped += 1
            continue

        gain_db = pout - pin
        imd3    = pout - p3f
        oip3    = pout + imd3 / 2.0
        iip3    = oip3 - gain_db

        rows.append(SweepRow(freq_hz, pout, pin, p3f, gain_db, imd3, oip3, iip3))

    if skipped:
        logger.info(f"{csv_path.name}: skipped {skipped} malformed row(s).")

    if not rows:
        raise ValueError(f"No valid data rows found in {csv_path.name}")   # unchanged
    return rows


# -------------------------------------------------------------------------
# Write the **single** combined MDIF file.
# -------------------------------------------------------------------------
def _write_combined_mdif(
    out_path: Path,
    temperature: float,
    net_data: List[Tuple[int, List[SweepRow]]],
) -> None:
    """
    ``net_data`` is a list of tuples:

        (net_number, [SweepRow, SweepRow, …])

    The function writes a separate MDIF section for each net, but all sections
    are concatenated into *one* file.
    """
    header_tokens = [
        "%freq(real)",
        "Pout_dBm(real)",
        "Pin_dBm(real)",
        "P3f(real)",
        "Gain_dB(real)",
        "IMD3(real)",
        "OIP3(real)",
        "IIP3(real)",
    ]

    lines: List[str] = []

    for net_number, rows in net_data:
        # ---------------------------------------------------------------
        # Net‑specific header
        # ---------------------------------------------------------------
        lines.append(f"VAR Net(real) = {net_number}\n")
        lines.append(f"VAR Temperature(real) = {temperature}\n")
        lines.append("BEGIN ACDATA\n")

        # ---------------------------------------------------------------
        # Compute column widths that fit *both* header and data
        # ---------------------------------------------------------------
        col_widths = _calc_col_widths(header_tokens, rows, padding=2)   # 2‑space gap

        # Header line – left‑aligned using the computed widths
        header_line = "".join(tok.ljust(w) for tok, w in zip(header_tokens, col_widths))
        lines.append(header_line.rstrip() + "\n")

        # ---------------------------------------------------------------
        # Data rows – left‑aligned with the *same* widths
        # ---------------------------------------------------------------
        for r in rows:
            values = [
                f"{int(r.frequency_hz)}",
                f"{r.pout_dbm:.6g}",
                f"{r.pin_dbm:.6g}",
                f"{r.p3f:.6g}",
                f"{r.gain_db:.6g}",
                f"{r.imd3:.6g}",
                f"{r.oip3:.6g}",
                f"{r.iip3:.6g}",
            ]
            row_line = "".join(val.ljust(w) for val, w in zip(values, col_widths))
            lines.append(row_line.rstrip() + "\n")

        lines.append("END\n")
        lines.append("\n")      # optional blank line between net sections

    out_path.write_text("".join(lines))
    if out_path.stat().st_size == 0:
        raise IOError(f"Failed to write combined MDIF file {out_path}")


# -------------------------------------------------------------------------
# Main orchestration – now mirrors the gain‑compression script’s summary
# -------------------------------------------------------------------------
def main() -> None:
    args = _parse_cli()

    # -----------------------------------------------------------------
    # Set logging level according to --verbose
    # -----------------------------------------------------------------
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # --------------------------------------------------------------- #
    # Gather required information (CLI or interactive fallback)       #
    # --------------------------------------------------------------- #
    base_path: Path = args.base_path or Path(
        _prompt_missing("Base directory containing net folders (E1, E2, …)", Path)
    )
    temperature: float = (
        args.temperature
        if args.temperature is not None
        else float(_prompt_missing("Temperature (°C)", float))
    )
    _validate_temperature(temperature)

    if not base_path.is_dir():
        raise NotADirectoryError(f"The supplied base_path does not exist: {base_path}")

    plots_dir = base_path / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------- #
    # Discover net folders and read each CSV
    # --------------------------------------------------------------- #
    nets = _discover_net_folders(base_path)

    # This list will hold all the data that goes into the final MDIF
    all_net_data: List[Tuple[int, List[SweepRow]]] = []

    # -----------------------------------------------------------------
    # Containers for problem reporting (exactly what the gain‑compression
    # script uses)
    # -----------------------------------------------------------------
    bad_files: List[str] = []                     # flat list of all bad CSV paths
    nets_without_csv: List[str] = []              # nets that have no CSV at all
    bad_files_by_net: dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        csv_files = (
            sorted(net.path.glob("*IMD_Swp*.csv"))
            + sorted(net.path.glob("*SWP_IMD*.csv"))
        )        
        if not csv_files:
            logger.info(f"[INFO] No CSV files found in {net.path} – skipping")
            nets_without_csv.append(net.name)
            continue

        net_number = _net_number_from_folder(net.name)
        csv_path = csv_files[0]                     # assuming one sweep per net

        try:
            rows = _parse_imd_csv(csv_path)        # tolerant to malformed rows
            all_net_data.append((net_number, rows))
        except Exception as exc:
            # ---------------------------------------------------------
            # Critical error for this net – record it and continue
            # ---------------------------------------------------------
            exc_msg = str(exc)
            bad_files.append(str(csv_path))
            bad_files_by_net.setdefault(net.name, []).append((str(csv_path), exc_msg))

            # *** FIXED *** – do NOT pass `file=` to logger.info()
            logger.info(
                f"[INFO] Skipping malformed CSV file {csv_path} (net {net.name}): {exc_msg}"
            )
            # Net is omitted, but processing continues
            continue

    if not all_net_data:
        raise RuntimeError("No sweep data found – nothing to write to MDIF.")

    # --------------------------------------------------------------- #
    # Write the combined MDIF file
    # --------------------------------------------------------------- #
    mdif_path = plots_dir / "RDI_IMD_sweep.mdif"
    _write_combined_mdif(mdif_path, temperature, all_net_data)

    # ---------------------------------------------------------------
    # Write a consolidated “bad‑measurement” report (dash‑free)
    # ---------------------------------------------------------------
    if bad_files:
        bad_list_path = plots_dir / "imd_sweep_bad_measurements.txt"
        lines: List[str] = [
            "! ===========================\n",
            f"! IMD sweep bad measurement report \n",
            "! ===========================\n",
            "! This file lists all IMD sweep nets that could NOT be\n",
            "! incorporated into the final MDIF because of missing or\n",
            "! malformed CSV measurement files.\n",
            "! Each entry shows the CSV file path and the Python exception\n",
            "! message that triggered the rejection.\n",
            "! ===========================\n",
            "\n",
        ]

        if nets_without_csv:
            lines.append("! Nets that have NO IMD SWP CSV files (omitted from MDIF):\n")
            for net_name in sorted(nets_without_csv):
                lines.append(f"!    {net_name}\n")
            lines.append("\n")

        lines.append("! Nets that contain malformed CSV files (entire net omitted):\n")
        for net_name in sorted(bad_files_by_net):
            lines.append(f"!   Net {net_name}:\n")
            for file_path, err_msg in bad_files_by_net[net_name]:
                safe_msg = err_msg.replace("\n", " | ")
                lines.append(f"!         {file_path}\n")
                lines.append(f"!         Reason: {safe_msg}\n")
            lines.append("\n")

        lines.append("\n!  Flat list of all bad CSV files (for scripts) n")
        for p in bad_files:
            lines.append(f"{p}\n")

        # No dash characters anywhere in the gathered lines → safe write
        bad_list_path.write_text("".join(lines))
        logger.info(f"A detailed bad measurement report has been written to: {bad_list_path}")

    # ---------------------------------------------------------------
    # Final human‑readable summary (mirrors gain‑compression script)
    # ---------------------------------------------------------------
    total_rows = sum(len(rows) for _, rows in all_net_data)
    logger.info("\n=== IMD‑sweep aggregation finished ===")
    logger.info(f"Base path          : {base_path}")
    logger.info(f"Temperature (°C)   : {temperature}")
    logger.info(f"Nets processed     : {len(all_net_data)}")
    logger.info(f"Total CSV rows used: {total_rows}")
    logger.info(f"Combined MDIF written to: {mdif_path}")
    # logger.info("\nGenerated sections -- net (rows):")
    # for net_number, rows in all_net_data:
    #     logger.info(f"  Net {net_number}  ({len(rows)} rows)")

    if nets_without_csv:
        logger.info("\nNets that had no (or malformatted) IMD‑SWP CSV files and were omitted:")
        for n in nets_without_csv:
            logger.info(f"  - {n}")

if __name__ == "__main__":
    # Any unexpected exception propagates – the script aborts on the first
    # *critical* error (e.g. no valid nets at all).
    main()