"""Parse an IMD‑sweep CSV into a list of row dictionaries."""

import csv
from pathlib import Path
from typing import List, Dict

def parse_imd_csv(csv_path: Path, *, freq_col: str = "FrequencyFC") -> List[Dict[str, float]]:
    """Return a list of dicts with keys: frequency_hz, pout_dbm, pin_dbm, p3f, gain_db, imd3, oip3, iip3."""
    with csv_path.open("r", newline="") as f:
        lines = f.readlines()

    header_idx = next(i for i, l in enumerate(lines) if l.strip().startswith(freq_col))
    header_line = lines[header_idx].strip()
    field_names = [h.strip() for h in header_line.split(",")]
    reader = csv.DictReader(lines[header_idx + 2 :], fieldnames=field_names)

    rows: List[Dict[str, float]] = []
    for i, row in enumerate(reader, start=1):
        try:
            freq_hz = int(float(row[freq_col]))
            pout = float(row["PwrMain"])
            pin = float(row["PwrMainIn"])
            p3f = float(row["Pwr3"])
        except KeyError as e:
            raise KeyError(f"Missing column {e} in {csv_path.name}") from e
        except ValueError as e:
            raise ValueError(f"Non‑numeric value at row {i} in {csv_path.name}: {e}") from e

        gain_db = pout - pin
        imd3 = pout - p3f
        oip3 = pout + imd3 / 2.0
        iip3 = oip3 - gain_db

        rows.append(
            {
                "frequency_hz": freq_hz,
                "pout_dbm": pout,
                "pin_dbm": pin,
                "p3f": p3f,
                "gain_db": gain_db,
                "imd3": imd3,
                "oip3": oip3,
                "iip3": iip3,
            }
        )
    if not rows:
        raise ValueError(f"No valid rows found in {csv_path.name}")
    return rows