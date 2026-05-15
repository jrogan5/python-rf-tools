#!/usr/bin/env python3
r"""
gain_compression_to_mdif.py
---------------------------

Read every gain‑compression CSV that lives under

    <base_path>\E1, <base_path>\E2, …

and produce **one** MDIF file named `RDI_gain_compression.mdif` in a
`plots` sub‑folder of the base path.

Features
--------
* CLI arguments `--base-path` and `--temperature` (interactive fallback).
* Temperature is validated against a configurable range (‑100 °C … +100 °C).
* The Net identifier is taken from the folder name (E1 → 1, E2 → 2, …).
* Frequency is read from the line that starts with “!CW Freq:” inside each CSV.
* The numeric table after the “BEGIN …_DATA” header is parsed with the
  standard‑library `csv` module.
* Column spacing in the data block exactly matches the header spacing
  (left‑aligned values). Widths are derived from the header strings.
* **If a net has no CSV files, or any CSV of the net is malformed,
  the whole net is omitted from the MDIF.**  
  A list of malformed CSV files and a list of nets without CSV files
  are printed and also written to `plots/bad_measurements.txt`.

Usage
-----
    python gain_compression_to_mdif.py --base-path "C:\RF\Measurements" --temperature 23
If the arguments are omitted the script will prompt for them.
"""

import datetime
import argparse
import csv
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import os

# -------------------------------------------------------------------------
# Temperature limits (user‑configurable)
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
class MeasurementBlock:
    """
    Holds the six columns required for the MDIF data block.
    All lists have the same length (the number of rows read from the CSV).
    """
    pin_dbm: List[float]
    s21_db: List[float]
    s21_deg: List[float]
    pin_deg: List[float]
    pout_dbm: List[float]
    pout_deg: List[float]

# -------------------------------------------------------------------------
# CLI handling (with interactive fallback)
# -------------------------------------------------------------------------
def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine all gain‑compression CSVs into a single MDIF file."
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
    return parser.parse_args()


def _prompt_missing(prompt: str, cast_type):
    """Ask the user for a value when the CLI argument was omitted."""
    while True:
        try:
            return cast_type(input(f"{prompt}: ").strip())
        except ValueError as exc:
            print(f"Invalid input – {exc}")


def _validate_temperature(temp: float) -> None:
    if not (TEMP_MIN <= temp <= TEMP_MAX):
        raise ValueError(
            f"Temperature {temp} °C is outside the allowed range [{TEMP_MIN}, {TEMP_MAX}]"
        )

# -------------------------------------------------------------------------
# Math helpers (used when the CSV stores REAL/IMAG instead of DB/DEG)
# -------------------------------------------------------------------------
def _mag_to_db(real: float, imag: float) -> float:
    """Convert a complex magnitude (real + j·imag) to dB (20·log10(|z|))."""
    mag = math.hypot(real, imag)
    if mag == 0:
        return float("-inf")          # avoid log(0)
    return 20.0 * math.log10(mag)


def _angle_deg(real: float, imag: float) -> float:
    """Return the phase angle of a complex number in degrees."""
    return math.degrees(math.atan2(imag, real))

# -------------------------------------------------------------------------
# Discover net folders (E1, E2, …) under the supplied base path
# -------------------------------------------------------------------------
def _discover_net_folders(root: Path) -> List[NetFolder]:
    candidate_paths = [p for p in root.glob("E*") if p.is_dir()]
    sorted_paths = sorted(candidate_paths, key=lambda p: _net_number_from_folder(p.name))
    nets = [NetFolder(name=p.name, path=p) for p in sorted_paths]

    if not nets:
        raise FileNotFoundError(f"No net folders (E1, E2, …) found under {root}")
    return nets


def _net_number_from_folder(folder_name: str) -> int:
    """E1 → 1, E2 → 2, … – change here if you need a different scheme."""
    match = re.fullmatch(r"E(\d+)", folder_name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Folder name '{folder_name}' does not match pattern 'E<number>'.")
    return int(match.group(1))

# -------------------------------------------------------------------------
# Frequency extraction – line looks like "!CW Freq: 27500000000 Hz"
# -------------------------------------------------------------------------
_FREQ_RE = re.compile(r"!CW\s+Freq:\s*([0-9]+)\s*Hz", re.IGNORECASE)


def _extract_frequency_hz(csv_path: Path) -> int:
    with csv_path.open("r", newline="") as f:
        for line in f:
            m = _FREQ_RE.search(line)
            if m:
                return int(m.group(1))
    raise ValueError(f"Frequency line not found in {csv_path.name}")

# -------------------------------------------------------------------------
# Normalise column names (lower‑case, no quotes, no spaces)
# -------------------------------------------------------------------------
def _norm(col_name: str) -> str:
    return col_name.replace('"', '').replace(' ', '').strip().lower()


# -------------------------------------------------------------------------
# Parse the numeric block that follows the "BEGIN …_DATA" header.
# -------------------------------------------------------------------------
def _parse_measurement_block(csv_path: Path) -> MeasurementBlock:
    """
    Reads the data block that appears after the line that contains
    "BEGIN …_DATA".  The CSV header is expected to contain at least the
    columns needed for the six MDIF columns.  The function automatically
    handles three possible column styles:
        * DB / DEG  (e.g. S21(DB), S21(DEG))
        * REAL / IMAG
        * “Log Mag” only (in which case the missing columns stay blank)
    """
    with csv_path.open("r", newline="") as f:
        lines = f.readlines()

    # --------------------------------------------------------------- #
    # Locate the line that contains “BEGIN” and grab the header line
    # --------------------------------------------------------------- #
    begin_idx = None
    for i, line in enumerate(lines):
        if "BEGIN" in line:
            begin_idx = i
            break
    if begin_idx is None:
        raise ValueError(f"'BEGIN' not found in {csv_path.name}")

    header_line = lines[begin_idx + 1].strip()
    data_start = begin_idx + 2          # numeric rows start two lines after BEGIN

    # Use csv.reader so commas *inside* quotes are NOT split.
    header_cells_raw = next(csv.reader([header_line], skipinitialspace=True))
    header_cells = [_norm(cell) for cell in header_cells_raw if cell]

    col_index = {name: idx for idx, name in enumerate(header_cells)}

    # --------------------------------------------------------------- #
    # Resolve which columns are present
    # --------------------------------------------------------------- #
    # ---- Pin (Power) ------------------------------------------------
    pin_idx = col_index[_norm("Power(dBm)")]

    # ---- S21 --------------------------------------------------------
    if _norm("S21(DB)") in col_index and _norm("S21(DEG)") in col_index:
        s21_db_idx, s21_deg_idx = col_index[_norm("S21(DB)")], col_index[_norm("S21(DEG)")]
        s21_real_idx = s21_imag_idx = None
    elif _norm("S21 Log Mag(dB)") in col_index:
        # Only a log‑mag column – the other columns will be left blank later
        s21_db_idx = col_index[_norm("S21 Log Mag(dB)")]
        s21_deg_idx = None
        s21_real_idx = s21_imag_idx = None
        print(f"[INFO] Incomplete log measurement file: {csv_path.name}. "
              "Only S21 Log Mag(dB) present.")
    else:
        # Complex representation (REAL / IMAG)
        s21_real_idx = col_index.get(_norm("S21(REAL)"))
        s21_imag_idx = col_index.get(_norm("S21(IMAG)"))
        if s21_real_idx is None or s21_imag_idx is None:
            raise KeyError("S21 columns missing (neither DB/DEG nor REAL/IMAG found)")
        s21_db_idx = s21_deg_idx = None

    # ---- Pin degree (R1,1) ------------------------------------------
    if _norm("R1,1(DEG)") in col_index:
        pin_deg_idx = col_index[_norm("R1,1(DEG)")]
        pin_real_idx = pin_imag_idx = None
    else:
        pin_real_idx = col_index.get(_norm("R1,1(REAL)"))
        pin_imag_idx = col_index.get(_norm("R1,1(IMAG)"))
        if pin_real_idx is None or pin_imag_idx is None:
            raise KeyError("R1,1 columns missing (neither DEG nor REAL/IMAG found)")
        pin_deg_idx = None

    # ---- Pout (B,1) -------------------------------------------------
    if _norm("B,1(DB)") in col_index and _norm("B,1(DEG)") in col_index:
        pout_dbm_idx, pout_deg_idx = col_index[_norm("B,1(DB)")], col_index[_norm("B,1(DEG)")]
        pout_real_idx = pout_imag_idx = None
    elif _norm("B,1 Log Mag(dBm)") in col_index:
        pout_dbm_idx = col_index[_norm("B,1 Log Mag(dBm)")]
        pout_deg_idx = None
        pout_real_idx = pout_imag_idx = None
        print(f"[INFO] Incomplete log measurement file: {csv_path.name}. "
              "Only B,1 Log Mag(dBm) present.")
    else:
        pout_real_idx = col_index.get(_norm("B,1(REAL)"))
        pout_imag_idx = col_index.get(_norm("B,1(IMAG)"))
        if pout_real_idx is None or pout_imag_idx is None:
            raise KeyError("B,1 columns missing (neither DB/DEG nor REAL/IMAG found)")
        pout_dbm_idx = pout_deg_idx = None

    # --------------------------------------------------------------- #
    # Read the numeric rows
    # --------------------------------------------------------------- #
    pin_dbm, s21_db, s21_deg, pin_deg, pout_dbm, pout_deg = ([] for _ in range(6))
    reader = csv.reader(lines[data_start:], skipinitialspace=True)

    for row_idx, raw_row in enumerate(reader, start=1):
        # Skip empty lines
        if not raw_row:
            continue
        # Stop at a literal "END" marker
        if raw_row[0].strip().upper() == "END":
            break

        # ---- Pin power ------------------------------------------------
        try:
            pin_dbm.append(float(raw_row[pin_idx]))
        except Exception as exc:
            raise ValueError(f"Pin dBm conversion error at row #{row_idx}: {raw_row}") from exc

        # ---- S21 ------------------------------------------------------
        if s21_db_idx is not None and s21_deg_idx is not None:          # DB / DEG
            s21_db.append(float(raw_row[s21_db_idx]))
            s21_deg.append(float(raw_row[s21_deg_idx]))
        elif s21_db_idx is not None and s21_deg_idx is None:            # Log‑mag only
            s21_db.append(float(raw_row[s21_db_idx]))
        else:                                                            # REAL / IMAG
            try:
                real = float(raw_row[s21_real_idx])
                imag = float(raw_row[s21_imag_idx])
            except Exception as exc:
                raise ValueError(f"S21 REAL/IMAG conversion error at row #{row_idx}: {raw_row}") from exc
            s21_db.append(_mag_to_db(real, imag))
            s21_deg.append(_angle_deg(real, imag))

        # ---- Pin degree (R1,1) ----------------------------------------
        if pin_deg_idx is not None:                                      # DEG
            pin_deg.append(float(raw_row[pin_deg_idx]))
        else:                                                            # REAL / IMAG
            try:
                real = float(raw_row[pin_real_idx])
                imag = float(raw_row[pin_imag_idx])
            except Exception as exc:
                raise ValueError(f"R1,1 REAL/IMAG conversion error at row #{row_idx}: {raw_row}") from exc
            pin_deg.append(_angle_deg(real, imag))

        # ---- Pout (B,1) -----------------------------------------------
        if pout_dbm_idx is not None and pout_deg_idx is not None:        # DB / DEG
            pout_dbm.append(float(raw_row[pout_dbm_idx]))
            pout_deg.append(float(raw_row[pout_deg_idx]))
        elif pout_dbm_idx is not None and pout_deg_idx is None:          # Log‑mag only
            pout_dbm.append(float(raw_row[pout_dbm_idx]))
        else:                                                            # REAL / IMAG
            try:
                real = float(raw_row[pout_real_idx])
                imag = float(raw_row[pout_imag_idx])
            except Exception as exc:
                raise ValueError(f"B,1 REAL/IMAG conversion error at row #{row_idx}: {raw_row}") from exc
            pout_dbm.append(_mag_to_db(real, imag))
            pout_deg.append(_angle_deg(real, imag))

    if not pin_dbm:
        raise ValueError(f"No data rows found in {csv_path.name}")

    return MeasurementBlock(
        pin_dbm=pin_dbm,
        s21_db=s21_db,
        s21_deg=s21_deg,
        pin_deg=pin_deg,
        pout_dbm=pout_dbm,
        pout_deg=pout_deg,
    )

# -------------------------------------------------------------------------
# Helper to compute column widths for the MDIF data block
# -------------------------------------------------------------------------
def _calc_col_widths(header_tokens: List[str],
                     block: MeasurementBlock,
                     padding: int = 2) -> List[int]:
    """
    Return a list of column widths wide enough for the header text and the
    longest formatted value in the block.  Padding adds a couple of blanks
    so columns are nicely separated.
    """
    widths = [len(tok) + padding for tok in header_tokens]

    for i in range(len(block.pin_dbm)):
        data_vals = [
            f"{block.pin_dbm[i]:.6g}",
            f"{block.s21_db[i]:.6g}",
            f"{block.s21_deg[i]:.6g}",
            f"{block.pin_deg[i]:.6g}",
            f"{block.pout_dbm[i]:.6g}",
            f"{block.pout_deg[i]:.6g}",
        ]
        widths = [max(w, len(v) + padding) for w, v in zip(widths, data_vals)]

    return widths

# -------------------------------------------------------------------------
# Write the combined MDIF file (only nets that survived the checks)
# -------------------------------------------------------------------------
def _write_combined_mdif(
    out_path: Path,
    temperature: float,
    net_blocks: List[Tuple[int, int, MeasurementBlock]],
) -> None:
    """
    `net_blocks` is a list of tuples ``(net_number, frequency_hz, block)``.
    The function writes one MDIF section per net, preserving the column
    spacing required by downstream tools.
    """
    header_tokens = [
        "%Pin_dBm(real)",
        "S21_dB(real)",
        "S21_degree(real)",
        "Pin_degree(real)",
        "Pout_dBm(real)",
        "Pout_degree(real)",
    ]

    lines: List[str] = []

    for net_number, freq_hz, block in net_blocks:
        # ---------- net‑specific header ----------
        lines.append(f"VAR Net(real) = {net_number}\n")
        lines.append(f"VAR Frequency(real)={freq_hz}\n")
        lines.append(f"VAR Temperature(real) = {temperature}\n")
        lines.append("BEGIN ACDATA\n")

        # ---------- column header ----------
        col_widths = _calc_col_widths(header_tokens, block, padding=2)
        header_line = "".join(tok.ljust(width) for tok, width in zip(header_tokens, col_widths))
        lines.append(header_line.rstrip() + "\n")

        # ---------- data rows ----------
        row_count = len(block.pin_dbm)
        for i in range(row_count):
            values = [
                f"{block.pin_dbm[i]:.6g}",
                f"{block.s21_db[i]:.6g}",
                f"{block.s21_deg[i]:.6g}",
                f"{block.pin_deg[i]:.6g}",
                f"{block.pout_dbm[i]:.6g}",
                f"{block.pout_deg[i]:.6g}",
            ]
            row_line = "".join(val.ljust(width) for val, width in zip(values, col_widths))
            lines.append(row_line.rstrip() + "\n")

        lines.append("END\n")
        lines.append("\n")               # blank line between net sections (optional)

    out_path.write_text("".join(lines))

    if out_path.stat().st_size == 0:
        raise IOError(f"Failed to write combined MDIF file {out_path}")

# -------------------------------------------------------------------------
# Main orchestration
# -------------------------------------------------------------------------
def main() -> None:
    args = _parse_cli()

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
    _validate_temperature(temperature)

    if not base_path.is_dir():
        raise NotADirectoryError(f"The supplied base_path does not exist: {base_path}")

    plots_dir = base_path / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------
    # Containers for problem reporting
    # -----------------------------------------------------------------
    bad_files: List[str] = []                     # flat list of all bad CSV paths
    nets_without_csv: List[str] = []              # nets that have no CSV at all
    # net name → list of (file_path, error_message)
    bad_files_by_net: dict[str, List[Tuple[str, str]]] = {}

    # -----------------------------------------------------------------
    # Discover net folders and process them
    # -----------------------------------------------------------------
    nets = _discover_net_folders(base_path)
    all_blocks: List[Tuple[int, int, MeasurementBlock]] = []

    for net in nets:
        csv_files = sorted(net.path.glob("*Gain_Comp*.csv"))

        # ---- No CSV at all for this net ----
        if not csv_files:
            nets_without_csv.append(net.name)
            print(f"[INFO] No CSV files found in {net.path} – net will be omitted")
            continue

        net_number = _net_number_from_folder(net.name)
        net_is_bad = False                     # becomes True on first malformed CSV

        for csv_path in csv_files:
            try:
                freq_hz = _extract_frequency_hz(csv_path)
                block   = _parse_measurement_block(csv_path)
                # We only add the block while we are still sure the net is good.
                all_blocks.append((net_number, freq_hz, block))
            except Exception as exc:
                # Record the offending file, the net it belongs to, and the reason
                exc_msg = str(exc)
                bad_files.append(str(csv_path))

                # ---- NEW: map the bad file + its error to the net ----
                bad_files_by_net.setdefault(net.name, []).append(
                    (str(csv_path), exc_msg)
                )

                net_is_bad = True
                print(
                    f"[INFO] Skipping malformed CSV file {csv_path} (net {net.name}): {exc_msg}",
                    file=sys.stderr,
                )
                break   # stop processing further CSVs of this net

        # If this net was flagged as bad, remove any blocks we may have already added
        if net_is_bad:
            all_blocks = [blk for blk in all_blocks if blk[0] != net_number]
            continue   # move on to the next net

    # -----------------------------------------------------------------
    # If after filtering we have nothing to write, exit gracefully
    # -----------------------------------------------------------------
    if not all_blocks:
        print("\n[WARN] No valid measurement data found – no MDIF will be generated.", file=sys.stderr)
        if bad_files:
            bad_list_path = plots_dir / "bad_measurements.txt"
            bad_list_path.write_text("\n".join(bad_files) + "\n")
            print(f"List of malformed CSV files written to: {bad_list_path}")
        if nets_without_csv:
            print("Nets without any CSV files:")
            for n in nets_without_csv:
                print(f"  - {n}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # Write the combined MDIF file
    # -----------------------------------------------------------------
    mdif_path = plots_dir / "RDI_gain_compression.mdif"
    _write_combined_mdif(mdif_path, temperature, all_blocks)

    # -----------------------------------------------------------------
    # Write the list of malformed CSV files (if any)
    # -----------------------------------------------------------------
    if bad_files:
        bad_list_path = plots_dir / "gain_comp_bad_measurements.txt"
        lines_to_write: List[str] = []

        lines_to_write.append("! !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        lines_to_write.append(f"! Gain compression bad measurement report\n")
        lines_to_write.append("! !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        lines_to_write.append("! This file lists all gain compression nets that could NOT be\n")
        lines_to_write.append("! incorporated into the final MDIF because of missing or\n")
        lines_to_write.append("! malformed CSV measurement files.\n")
        lines_to_write.append("! Each entry shows the CSV file path and the Python exception\n")
        lines_to_write.append("! message that triggered the rejection.\n")
        lines_to_write.append("! !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        lines_to_write.append("\n")
        
        if nets_without_csv:
            lines_to_write.append("! Nets that have no Gain Comp CSV files (omitted from MDIF):\n")
            for net_name in sorted(nets_without_csv):
                lines_to_write.append(f"!    {net_name}\n")
            lines_to_write.append("\n")

        lines_to_write.append("! Nets that contain malformed CSV files (entire net omitted):\n")
        for net_name in sorted(bad_files_by_net):
            lines_to_write.append(f"!   Net {net_name}:\n")
            for file_path, err_msg in bad_files_by_net[net_name]:
                # Escape any new‑lines that might be inside the exception text
                safe_msg = err_msg.replace("\n", " | ")
                lines_to_write.append(f"!         {file_path}\n")
                lines_to_write.append(f"!         Reason: {safe_msg}\n")
            lines_to_write.append("\n")
            
        lines_to_write.append("\n! Flat list of all bad CSV files (for scripts)\n")
        for p in bad_files:
            lines_to_write.append(f"{p}\n")

        bad_list_path.write_text("".join(lines_to_write))
        print(f"\nA detailed malformed measurement report has been written to: {bad_list_path}")

        
    # -----------------------------------------------------------------
    # Final human‑readable summary
    # -----------------------------------------------------------------
    print("\n=== Gain compression aggregation finished ===")
    print(f"Base path                : {base_path}")
    print(f"Temperature (°C)         : {temperature}")
    print(f"Nets discovered          : {len(nets)}")
    print(f"Nets used in MDIF       : {len({blk[0] for blk in all_blocks})}")
    print(f"Total CSV files read    : {len(all_blocks)}")
    print(f"Combined MDIF written to : {mdif_path}")

    if nets_without_csv:
        print("\nNets that had **no** GainComp CSV files and were omitted:")
        for n in nets_without_csv:
            print(f"  - {n}")

    if bad_files:
        print("\nCSV files that were malformed (their nets were omitted):")
        for f in bad_files:
            print(f"  - {f}")

        # Also show the nets that were affected, together with the reason
        print("\nNets that contained malformed data:")
        for net_name, entries in sorted(bad_files_by_net.items()):
            print(f"  Net {net_name}:")
            for file_path, err_msg in entries:
                short_msg = err_msg.splitlines()[0]   # first line is usually enough
                print(f"    • {file_path}")
                print(f"      Reason: {short_msg}")

    # print("\nGenerated MDIF sections -- net (frequency):")
    # for net_number, freq_hz, _ in all_blocks:
    #     print(f"  Net {net_number} ({freq_hz:,} Hz)")


if __name__ == "__main__":
    # Any unexpected exception propagates – “abort on exception”.
    main()