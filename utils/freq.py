"""Frequency extraction helper."""

import re
from pathlib import Path


def extract_single_frequency_csv(csv_path: Path, regex: str) -> int:
    """Read *csv_path* line‑by‑line and return the first integer matched by *regex*."""
    pattern = re.compile(regex, re.IGNORECASE)
    with csv_path.open("r", newline="") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                return int(m.group(1))
    raise ValueError(f"Frequency line not found in {csv_path.name}")