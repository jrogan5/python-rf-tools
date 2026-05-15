"""Net folder helpers."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import List


@dataclass(frozen=True)
class NetFolder:
    """Simple container for a net folder (e.g. E12 → net 12)."""
    name: str
    path: Path


def _net_number_from_folder(name: str) -> int:
    """Extract the integer part from a folder name like “E12”."""
    m = re.fullmatch(r"E(\d+)", name, re.IGNORECASE)
    if not m:
        raise ValueError(f"Folder name '{name}' does not match pattern 'E<number>'.")
    return int(m.group(1))


def discover_nets(root: Path) -> List[NetFolder]:
    """Return a sorted list of NetFolder objects for every E* sub‑folder."""
    candidates = [p for p in root.glob("E*") if p.is_dir()]
    sorted_paths = sorted(candidates, key=lambda p: _net_number_from_folder(p.name))
    return [NetFolder(name=p.name, path=p) for p in sorted_paths]