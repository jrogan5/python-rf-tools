"""Parse a Noise‑Figure CSV into a list of (frequency_hz, nf_db) dictionaries."""

import csv
from pathlib import Path
from typing import List, Dict, Tuple

def parse_nf_csv(csv_path: Path, *, freq_col: str, nf_candidates: Tuple[str, ...]) -> List[Dict[str, float]]:
    """Return a list of dicts with keys: frequency_hz and nf_db."""
    with csv_path.open("r", newline="") as f:
        lines = f.readlines()

    header_idx = next(i for i, l in enumerate(lines) if l.strip().startswith(freq_col))
    header_line = lines[header_idx].strip()
    field_names = [h.strip() for h in header_line.split(",")]
    reader = csv.DictReader(lines[header_idx + 2 :], fieldnames=field_names)

    # Locate the NF column (first candidate that exists, case‑insensitive)
    lower_fields = [h.lower() for h in field_names]
    nf_col = None
    for cand in nf_candidates:
        for i, h in enumerate(field_names):
            if cand.lower() == h.lower():
                nf_col = h
                break
        if nf_col:
            break
    if nf_col is None:
        raise KeyError(f"No NF column found in {csv_path.name}")

    rows: List[Dict[str, float]] = []
    for i, row in enumerate(reader, start=1):
        try:
            freq_hz = int(float(row[freq_col]))
            nf_db = float(row[nf_col])
        except KeyError as e:
            raise KeyError(f"Missing column {e} in {csv_path.name}") from e
        except ValueError as e:
            raise ValueError(f"Non‑numeric value at row {i} in {csv_path.name}: {e}") from e
        rows.append({"frequency_hz": freq_hz, "nf_db": nf_db})
    if not rows:
        raise ValueError(f"No valid rows found in {csv_path.name}")
    return rows