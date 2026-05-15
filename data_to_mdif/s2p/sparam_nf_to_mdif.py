#!/usr/bin/env python3
r"""
sparam_nf_to_mdif.py

Convert the S‑parameter CSV files (RAW & PROCESSED) together with their matching
NF CSV files into MDIF files that follow the layout:

    VAR SN(real) = <serial‑number>
    VAR Path(real) = <path‑number>
    VAR Temperature(real) = <temperature>
    BEGIN ACDATA
    %freq(real) s11_db(real) ... nf_db(real)

Folder layout expected under --base-path:
    <base-path>/
        RXEM1-000019/
            S-Parameters_RAW_RXEM1-000019_PATH1_25.0C.csv
            S-Parameters_PROCESSED_RXEM1-000019_PATH1_25.0C.csv
            NF_RAW_RXEM1-000019_PATH1_25.0C.csv
            NF_PROCESSED_RXEM1-000019_PATH1_25.0C.csv
        RXEM1-000036/
            ...
"""

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.mdif import write_mdif
from utils.cli import prompt_missing

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_file_handler = logging.FileHandler("4pack_sparam_nf.log", mode="w")
_file_handler.setLevel(logging.WARNING)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(_file_handler)


# -------------------------------------------------------------------------
# Data containers
# -------------------------------------------------------------------------
@dataclass
class SParamRow:
    freq_hz: int
    s11_db: float; s11_deg: float
    s21_db: float; s21_deg: float
    s12_db: float; s12_deg: float
    s22_db: float; s22_deg: float


@dataclass
class NFRow:
    freq_hz: int
    nf_db: float


# -------------------------------------------------------------------------
# Parsers
# -------------------------------------------------------------------------
def _parse_sparam_csv(csv_path: Path) -> Tuple[int, int, List[SParamRow]]:
    """Return (path_num, temperature, rows) from an S‑parameter CSV."""
    m = re.search(r"PATH\s*[-_]?\s*(\d+)", csv_path.stem, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse Path from file name '{csv_path.name}'")
    path_num = int(m.group(1))

    rows: List[SParamRow] = []
    temp = None
    with csv_path.open(newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if temp is None:
                raw = row.get("temp")
                if raw is None:
                    raise ValueError(f"Missing 'temp' column in {csv_path}")
                temp = int(float(raw))
            try:
                rows.append(SParamRow(
                    freq_hz=int(float(row["Freq"])),
                    s11_db=float(row["S11dB"]),  s11_deg=float(row["S11deg"]),
                    s21_db=float(row["S21dB"]),  s21_deg=float(row["S21deg"]),
                    s12_db=float(row["S12dB"]),  s12_deg=float(row["S12deg"]),
                    s22_db=float(row["S22dB"]),  s22_deg=float(row["S22deg"]),
                ))
            except KeyError as exc:
                raise ValueError(f"Missing column {exc} in {csv_path} (line {i})") from exc

    if temp is None:
        raise RuntimeError(f"Could not extract Temp from {csv_path}")
    return path_num, temp, rows


def _parse_nf_csv(csv_path: Path) -> Tuple[int, int, List[NFRow]]:
    """Return (path_num, temperature, rows) from an NF CSV."""
    m = re.search(r"PATH\s*[-_]?\s*(\d+)", csv_path.stem, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse Path from file name '{csv_path.name}'")
    path_num = int(m.group(1))

    rows: List[NFRow] = []
    temp = None
    with csv_path.open(newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if temp is None:
                raw = row.get("temp")
                if raw is None:
                    raise ValueError(f"Missing 'temp' column in {csv_path}")
                temp = int(float(raw))
            try:
                rows.append(NFRow(
                    freq_hz=int(float(row["Freq (Hz)"])),
                    nf_db=float(row["dB"]),
                ))
            except Exception as exc:
                raise ValueError(f"Bad row {i} in {csv_path}") from exc

    if temp is None:
        raise RuntimeError(f"Could not extract Temp from {csv_path}")
    return path_num, temp, rows


# -------------------------------------------------------------------------
# Helpers to build write_mdif‑compatible structures
# -------------------------------------------------------------------------
_SPARAM_HEADER = [
    "%freq(real)",
    "s11_db(real)", "s11_deg(real)",
    "s21_db(real)", "s21_deg(real)",
    "s12_db(real)", "s12_deg(real)",
    "s22_db(real)", "s22_deg(real)",
]
_NF_HEADER = ["%freq(real)", "nf_db(real)"]

Key = Tuple[int, int, int]  # (sn, path, temperature)


def _sparam_to_mdif_blocks(
    groups: Dict[Key, List[SParamRow]]
) -> List[Tuple[Dict, List[Dict]]]:
    return [
        (
            {"SN": sn, "Path": path_num, "Temperature": temp},
            [
                {
                    "freq": r.freq_hz,
                    "s11_db": r.s11_db, "s11_deg": r.s11_deg,
                    "s21_db": r.s21_db, "s21_deg": r.s21_deg,
                    "s12_db": r.s12_db, "s12_deg": r.s12_deg,
                    "s22_db": r.s22_db, "s22_deg": r.s22_deg,
                }
                for r in rows
            ],
        )
        for (sn, path_num, temp), rows in groups.items()
    ]


def _nf_to_mdif_blocks(
    groups: Dict[Key, List[NFRow]]
) -> List[Tuple[Dict, List[Dict]]]:
    return [
        (
            {"SN": sn, "Path": path_num, "Temperature": temp},
            [{"freq": r.freq_hz, "nf_db": r.nf_db} for r in rows],
        )
        for (sn, path_num, temp), rows in groups.items()
    ]


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------
def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert S‑parameter + NF CSVs into MDIF files (RAW and PROCESSED)."
    )
    p.add_argument("--base-path", type=Path,
                   help="Root directory containing the RXEM folders.")
    p.add_argument("--output-path", type=Path,
                   help="Directory where the MDIF files will be written.")
    return p.parse_args()


def main() -> None:
    args = _parse_cli()

    base_path: Path = args.base_path or prompt_missing(
        "Base directory containing RXEM folders", Path
    )
    output_path: Path = args.output_path or prompt_missing(
        "Directory where MDIF files should be written", Path
    )
    if not base_path.is_dir():
        sys.exit(f"[ERROR] Directory not found: {base_path}")
    output_path.mkdir(parents=True, exist_ok=True)

    rxem_dirs = [
        p for p in base_path.iterdir()
        if p.is_dir() and re.match(r"RXEM\d+-\d+$", p.name, re.IGNORECASE)
    ]
    if not rxem_dirs:
        sys.exit("[ERROR] No RXEM folders found under the base path.")
    logger.info(f"Found {len(rxem_dirs)} RXEM folders.")

    sparam_raw:  Dict[Key, List[SParamRow]] = {}
    sparam_proc: Dict[Key, List[SParamRow]] = {}
    nf_raw:      Dict[Key, List[NFRow]] = {}
    nf_proc:     Dict[Key, List[NFRow]] = {}

    for rxem in rxem_dirs:
        try:
            folder_sn = int(rxem.name.split("-")[-1].lstrip("0") or "0")
        except Exception as exc:
            logger.error(f"Could not parse SN from {rxem.name}: {exc}")
            continue

        for csv_path in sorted(rxem.glob("*.csv")):
            name_up = csv_path.name.upper()
            try:
                if "S-PARAMETERS_RAW" in name_up:
                    path_num, temp, rows = _parse_sparam_csv(csv_path)
                    sparam_raw.setdefault((folder_sn, path_num, temp), []).extend(rows)
                elif "S-PARAMETERS_PROCESSED" in name_up:
                    path_num, temp, rows = _parse_sparam_csv(csv_path)
                    sparam_proc.setdefault((folder_sn, path_num, temp), []).extend(rows)
                elif "NF_RAW" in name_up:
                    path_num, temp, rows = _parse_nf_csv(csv_path)
                    nf_raw.setdefault((folder_sn, path_num, temp), []).extend(rows)
                elif "NF_PROCESSED" in name_up:
                    path_num, temp, rows = _parse_nf_csv(csv_path)
                    nf_proc.setdefault((folder_sn, path_num, temp), []).extend(rows)
            except Exception as exc:
                logger.warning(f"Skipping malformed CSV {csv_path}: {exc}")

    logger.setLevel(logging.INFO)

    for label, groups, header, fname in (
        ("S‑param RAW",       sparam_raw,  _SPARAM_HEADER, "4PACKS_SPARAMS_RAW.mdif"),
        ("S‑param PROCESSED", sparam_proc, _SPARAM_HEADER, "4PACKS_SPARAMS_PROCESSED.mdif"),
        ("NF RAW",            nf_raw,      _NF_HEADER,     "4PACKS_NF_RAW.mdif"),
        ("NF PROCESSED",      nf_proc,     _NF_HEADER,     "4PACKS_NF_PROCESSED.mdif"),
    ):
        if not groups:
            logger.info(f"No {label} data found – skipping.")
            continue
        out_path = output_path / fname
        convert = _sparam_to_mdif_blocks if "sparam" in fname.lower() else _nf_to_mdif_blocks
        write_mdif(out_path, convert(groups), header_tokens=header)
        logger.info(f"Wrote {label} MDIF → {out_path}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
