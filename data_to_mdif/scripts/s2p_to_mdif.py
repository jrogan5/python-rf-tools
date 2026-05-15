#!/usr/bin/env python3
"""
s2p_to_mdif.py

Read every *.s2p* file that lives under
<base_path>/E1 , <base_path>/E2 , … and produce one MDIF file per
user‑provided “key” (e.g. NB, WB, NF).

The script mirrors the logic of *imd_sweep_to_mdif.py*:
* discover net folders (E1, E2, …)
* read the matching CSV‑like *.s2p* files
* collect the rows, write a single MDIF per key
* generate a “bad‑measurement” report for missing / malformed files
* CLI arguments with interactive fall‑back
"""

# -------------------------------------------------------------------------
# Imports + logging (identical to the imd script)
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
class S2pRow:
    """One row of S‑parameter data that will be written to the MDIF."""
    freq_hz: int
    s11_mag: float
    s11_phase: float
    s21_mag: float
    s21_phase: float
    s12_mag: float
    s12_phase: float
    s22_mag: float
    s22_phase: float


# -------------------------------------------------------------------------
# Helper utilities (copied from the original script)
# -------------------------------------------------------------------------
def _net_number_from_folder(folder_name: str) -> int:
    """
    Expected folder names are 'E1', 'E2', … → returns the integer part.
    If you rename the folders later, adjust this function only.
    """
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
    """CLI parsing – identical to the imd script, plus a --key argument."""
    parser = argparse.ArgumentParser(
        description="Combine all *.s2p* files matching a key into a single MDIF file."
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
        help="Key that appears in the filename (e.g. NB, WB, NF).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed warnings / processing info.",
    )
    return parser.parse_args()                                         # [1]


# -------------------------------------------------------------------------
# Parsing a single *.s2p* file
# -------------------------------------------------------------------------
def _parse_s2p_file(s2p_path: Path) -> List[S2pRow]:
    """
    Reads a Touchstone *.s2p* file and returns a list of ``S2pRow`` objects.
    Lines that start with ‘!’ are comments and are ignored.
    The header line starts with ‘#’ (e.g. “# Hz S dB R 50”) – it is also ignored.
    All remaining lines must contain nine whitespace‑separated columns:

        freq  S11mag  S11phase  S21mag  S21phase  S12mag  S12phase  S22mag  S22phase
    """
    rows: List[S2pRow] = []
    with s2p_path.open("r", newline="") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("!"):
                continue            # comment or empty line
            if line.startswith("#"):
                continue            # header line
            parts = line.split()
            if len(parts) != 9:
                logger.debug(f"Skipping malformed line in {s2p_path}: {line}")
                continue
            try:
                rows.append(
                    S2pRow(
                        freq_hz=int(float(parts[0])),
                        s11_mag=float(parts[1]),
                        s11_phase=float(parts[2]),
                        s21_mag=float(parts[3]),
                        s21_phase=float(parts[4]),
                        s12_mag=float(parts[5]),
                        s12_phase=float(parts[6]),
                        s22_mag=float(parts[7]),
                        s22_phase=float(parts[8]),
                    )
                )
            except ValueError as exc:
                logger.debug(f"Could not convert values in {s2p_path}: {exc}")
                continue
    if not rows:
        raise ValueError(f"No valid data rows found in {s2p_path.name}")
    return rows


# -------------------------------------------------------------------------
# MDIF writing helpers
# -------------------------------------------------------------------------
_MDIF_HEADER_TOKENS = [
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


def _calc_col_widths(header_tokens: List[str], rows: List[S2pRow], padding: int = 1) -> List[int]:
    """Same algorithm as the imd script – make columns wide enough for data."""
    widths = [len(tok) + padding for tok in header_tokens]

    for r in rows:
        data_strs = [
            f"{r.freq_hz:,}",
            f"{r.s11_mag:.6g}",
            f"{r.s11_phase:.6g}",
            f"{r.s21_mag:.6g}",
            f"{r.s21_phase:.6g}",
            f"{r.s12_mag:.6g}",
            f"{r.s12_phase:.6g}",
            f"{r.s22_mag:.6g}",
            f"{r.s22_phase:.6g}",
        ]
        widths = [max(w, len(s) + padding) for w, s in zip(widths, data_strs)]
    return widths                                                   # [1]


def _write_mdif_section(
    out_lines: List[str],
    net_number: int,
    temperature: float,
    rows: List[S2pRow],
) -> None:
    """Append one net‑section (header + data) to the growing MDIF string."""
    out_lines.append(f"VAR Net(real) = {net_number}\n")
    out_lines.append(f"VAR Temperature(real) = {temperature}\n")
    out_lines.append("BEGIN ACDATA\n")
    
    col_widths = _calc_col_widths(_MDIF_HEADER_TOKENS, rows, padding=5)
    header_line = "".join(tok.ljust(w) for tok, w in zip(_MDIF_HEADER_TOKENS, col_widths))

    out_lines.append(header_line.rstrip() + "\n")

    for r in rows:
        values = [
            f"{r.freq_hz}",
            f"{r.s11_mag:.8g}",
            f"{r.s11_phase:.8g}",
            f"{r.s21_mag:.8g}",
            f"{r.s21_phase:.8g}",
            f"{r.s12_mag:.8g}",
            f"{r.s12_phase:.8g}",
            f"{r.s22_mag:.8g}",
            f"{r.s22_phase:.8g}",
        ]
        line = "".join(val.ljust(w) for val, w in zip(values, col_widths))
        out_lines.append(line.rstrip() + "\n")

    out_lines.append("END\n\n")   # blank line separates net sections


# -------------------------------------------------------------------------
# Main orchestration – mimics the imd script flow
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

    key: str = args.key or _prompt_missing("Key to search for (e.g. NB, WB)", str)
    # Normalise the key – allow user to type “NB” or “NB.s2p”
    key = key.strip()
    if not key.lower().endswith(".s2p"):
        pattern = f"*{key}*.s2p"
    else:
        pattern = f"*{key}"          # already contains the extension
    logger.info(f"Using filename pattern: {pattern}")

    if not base_path.is_dir():
        raise NotADirectoryError(f"The supplied base_path does not exist: {base_path}")

    # -----------------------------------------------------------------
    # Discover net folders
    # -----------------------------------------------------------------
    nets = _discover_net_folders(base_path)                              # [1]

    # -----------------------------------------------------------------
    # Containers for reporting
    # -----------------------------------------------------------------
    bad_files: List[str] = []                     # flat list of all bad files
    nets_without_files: List[str] = []            # nets that have no matching *.s2p*
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    # -----------------------------------------------------------------
    # Process every net
    # -----------------------------------------------------------------
    all_net_data: List[Tuple[int, List[S2pRow]]] = []
    for net in nets:
        # Find the first file that matches the pattern inside this net folder
        matches = sorted(net.path.glob(pattern))
        if not matches:
            logger.info(f"[INFO] No '{pattern}' file found in {net.path} – skipping")
            nets_without_files.append(net.name)
            continue

        s2p_path = matches[0]          # we assume one file per net per key
        logger.debug(f"Processing {s2p_path}")

        try:
            rows = _parse_s2p_file(s2p_path)
            net_number = _net_number_from_folder(net.name)
            all_net_data.append((net_number, rows))
        except Exception as exc:        # catch malformed files
            exc_msg = str(exc)
            bad_files.append(str(s2p_path))
            bad_files_by_net.setdefault(net.name, []).append((str(s2p_path), exc_msg))
            logger.info(
                f"[INFO] Skipping malformed S2P file {s2p_path} (net {net.name}): {exc_msg}"
            )
            continue

    # -----------------------------------------------------------------
    # Write the combined MDIF file for the given key
    # -----------------------------------------------------------------

    plots_dir = base_path / "plots"
    if not plots_dir.is_dir():
        plots_dir.mkdir(parents=True, exist_ok=True)

    mdif_path = plots_dir / f"measured_{key.replace('.s2p', '')}.mdif"
    out_lines: List[str] = []

    for net_number, rows in all_net_data:
        _write_mdif_section(out_lines, net_number, temperature, rows)

    # ---- optional bad‑measurement report (exactly like the imd script) ----
    if bad_files or nets_without_files:
        bad_report_path = plots_dir / "s2p_bad_measurements.txt"
        report_lines: List[str] = [
            "! ===========================\n",
            f"! S2P bad measurement report for pattern '{pattern}'\n",
            "! ===========================\n",
            "\n",
        ]

        if nets_without_files:
            report_lines.append("! Nets that have NO matching S2P file (omitted from MDIF):\n")
            for n in sorted(nets_without_files):
                report_lines.append(f"!    {n}\n")
            report_lines.append("\n")

        if bad_files_by_net:
            report_lines.append("! Nets that contain malformed S2P files (entire net omitted):\n")
            for net_name in sorted(bad_files_by_net):
                report_lines.append(f"!   Net {net_name}:\n")
                for file_path, err_msg in bad_files_by_net[net_name]:
                    safe_msg = err_msg.replace("\n", " | ")
                    report_lines.append(f"!         {file_path}\n")
                    report_lines.append(f"!         Reason: {safe_msg}\n")
                report_lines.append("\n")

            report_lines.append("\n!  Flat list of all bad S2P files (for scripts)\n")
            for p in bad_files:
                report_lines.append(f"{p}\n")

        bad_report_path.write_text("".join(report_lines))
        logger.info(f"A detailed bad measurement report has been written to: {bad_report_path}")

    # -----------------------------------------------------------------
    # Write the MDIF file
    # -----------------------------------------------------------------
    mdif_path.write_text("".join(out_lines))
    if mdif_path.stat().st_size == 0:
        raise IOError(f"Failed to write combined MDIF file {mdif_path}")

    # -----------------------------------------------------------------
    # Human‑readable summary (mirrors the imd script)
    # -----------------------------------------------------------------
    total_rows = sum(len(r) for _, r in all_net_data)
    logger.info("\n=== S2P → MDIF aggregation finished ===")
    logger.info(f"Base path          : {base_path}")
    logger.info(f"Temperature (°C)   : {temperature}")
    logger.info(f"Nets processed     : {len(all_net_data)}")
    logger.info(f"Total data rows    : {total_rows}")
    logger.info(f"Combined MDIF written to: {mdif_path}")
    # logger.info("\nGenerated sections -- net (rows):")
    # for net_number, rows in all_net_data:
    #     logger.info(f"  Net {net_number}  ({len(rows)} rows)")


if __name__ == "__main__":
    # Any unexpected exception aborts the script – the same behaviour as the
    # original imd utility.
    main()