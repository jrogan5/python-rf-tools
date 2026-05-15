"""Parse a gain‑compression CSV into a dict of column lists."""

import csv
import math
from pathlib import Path
from typing import Dict, List


def _norm(col: str) -> str:
    return col.replace('"', "").replace(" ", "").strip().lower()


def parse_gain_csv(csv_path: Path) -> Dict[str, List[float]]:
    """
    Return a dict with six lists: pin_dbm, s21_db, s21_deg, pin_deg, pout_dbm, pout_deg.

    Handles three column styles emitted by Keysight VNAs:
      - DB / DEG  (e.g. S21(DB), S21(DEG))
      - Log‑mag only  (e.g. S21 log mag(dB))
      - REAL / IMAG  (complex, converted to dB/degrees)

    Pin phase is read from "R1,1"(DEG) (preferred) or "R1,1" REAL/IMAG.
    If neither is present the column is filled with NaN.
    """
    with csv_path.open("r", newline="") as f:
        lines = f.readlines()

    begin = next(i for i, l in enumerate(lines) if "BEGIN" in l)
    header = next(csv.reader([lines[begin + 1].strip()], skipinitialspace=True))
    header = [_norm(c) for c in header if c]
    idx = {n: i for i, n in enumerate(header)}

    # ---- Pin power -------------------------------------------------------
    pin_idx = idx.get(_norm("Power(dBm)"))
    if pin_idx is None:
        raise KeyError("Power(dBm) column missing")

    # ---- S21 – DB/DEG, Log‑Mag, or REAL/IMAG ----------------------------
    if _norm("S21(db)") in idx and _norm("S21(deg)") in idx:
        s21_db_idx, s21_deg_idx = idx[_norm("S21(db)")], idx[_norm("S21(deg)")]
        s21_real_idx = s21_imag_idx = None
    elif _norm("S21 log mag(dB)") in idx:
        s21_db_idx = idx[_norm("S21 log mag(dB)")]
        s21_deg_idx = s21_real_idx = s21_imag_idx = None
    else:
        s21_real_idx = idx.get(_norm("S21(real)"))
        s21_imag_idx = idx.get(_norm("S21(imag)"))
        if s21_real_idx is None or s21_imag_idx is None:
            raise KeyError("S21 columns missing (expected DB/DEG, Log‑Mag, or REAL/IMAG)")
        s21_db_idx = s21_deg_idx = None

    # ---- Pin phase – "R1,1"(DEG) preferred, then REAL/IMAG, else NaN ---
    pin_deg_idx = idx.get(_norm("R1,1(deg)"))
    pin_deg_real_idx = pin_deg_imag_idx = None
    if pin_deg_idx is None:
        pin_deg_real_idx = idx.get(_norm("R1,1(real)"))
        pin_deg_imag_idx = idx.get(_norm("R1,1(imag)"))

    # ---- Pout – "B,1" DB/DEG, Log‑Mag, or REAL/IMAG --------------------
    if _norm("b,1(db)") in idx and _norm("b,1(deg)") in idx:
        pout_db_idx, pout_deg_idx = idx[_norm("b,1(db)")], idx[_norm("b,1(deg)")]
        pout_real_idx = pout_imag_idx = None
    elif _norm("b,1 log mag(dbm)") in idx:
        pout_db_idx = idx[_norm("b,1 log mag(dbm)")]
        pout_deg_idx = pout_real_idx = pout_imag_idx = None
    else:
        pout_real_idx = idx.get(_norm("b,1(real)"))
        pout_imag_idx = idx.get(_norm("b,1(imag)"))
        if pout_real_idx is None or pout_imag_idx is None:
            raise KeyError("B,1 columns missing (expected DB/DEG, Log‑Mag, or REAL/IMAG)")
        pout_db_idx = pout_deg_idx = None

    data_start = begin + 2
    pin_dbm, s21_db, s21_deg, pin_deg, pout_dbm, pout_deg = ([] for _ in range(6))
    reader = csv.reader(lines[data_start:], skipinitialspace=True)

    for row in reader:
        if not row or row[0].strip().upper() == "END":
            break

        pin_dbm.append(float(row[pin_idx]))

        if s21_db_idx is not None and s21_deg_idx is not None:
            s21_db.append(float(row[s21_db_idx]))
            s21_deg.append(float(row[s21_deg_idx]))
        elif s21_db_idx is not None:
            s21_db.append(float(row[s21_db_idx]))
            s21_deg.append(float("nan"))
        else:
            r, i = float(row[s21_real_idx]), float(row[s21_imag_idx])
            s21_db.append(20.0 * math.log10(math.hypot(r, i)))
            s21_deg.append(math.degrees(math.atan2(i, r)))

        if pin_deg_idx is not None:
            pin_deg.append(float(row[pin_deg_idx]))
        elif pin_deg_real_idx is not None and pin_deg_imag_idx is not None:
            r, i = float(row[pin_deg_real_idx]), float(row[pin_deg_imag_idx])
            pin_deg.append(math.degrees(math.atan2(i, r)))
        else:
            pin_deg.append(float("nan"))

        if pout_db_idx is not None and pout_deg_idx is not None:
            pout_dbm.append(float(row[pout_db_idx]))
            pout_deg.append(float(row[pout_deg_idx]))
        elif pout_db_idx is not None:
            pout_dbm.append(float(row[pout_db_idx]))
            pout_deg.append(float("nan"))
        else:
            r, i = float(row[pout_real_idx]), float(row[pout_imag_idx])
            pout_dbm.append(20.0 * math.log10(math.hypot(r, i)))
            pout_deg.append(math.degrees(math.atan2(i, r)))

    if not pin_dbm:
        raise ValueError(f"No data rows found in {csv_path.name}")

    return {
        "pin_dbm": pin_dbm,
        "s21_db": s21_db,
        "s21_deg": s21_deg,
        "pin_deg": pin_deg,
        "pout_dbm": pout_dbm,
        "pout_deg": pout_deg,
    }
