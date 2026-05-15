"""Parse a Touchstone *.s2p* file into a list of S‑parameter dictionaries."""

from pathlib import Path
from typing import List, Dict

def parse_s2p_file(s2p_path: Path) -> List[Dict[str, float]]:
    """Return a list of dicts with keys: freq_hz, s11_mag, s11_phase, s21_mag, s21_phase, s12_mag, s12_phase, s22_mag, s22_phase."""
    rows: List[Dict[str, float]] = []
    with s2p_path.open("r", newline="") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("!") or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 9:
                continue
            try:
                rows.append(
                    {
                        "freq_hz": int(float(parts[0])),
                        "s11_mag": float(parts[1]),
                        "s11_phase": float(parts[2]),
                        "s21_mag": float(parts[3]),
                        "s21_phase": float(parts[4]),
                        "s12_mag": float(parts[5]),
                        "s12_phase": float(parts[6]),
                        "s22_mag": float(parts[7]),
                        "s22_phase": float(parts[8]),
                    }
                )
            except ValueError as e:
                raise ValueError(f"Non‑numeric value in {s2p_path.name}: {e}") from e
    if not rows:
        raise ValueError(f"No data rows found in {s2p_path.name}")
    return rows