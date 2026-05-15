# rf_measurements/s2p/converter.py
"""
S‑parameter (*.s2p*) converter.

Matches files that contain a user‑supplied key (e.g. “NB” or “WB”), parses
the Touchstone format, and creates a single MDIF file.
"""

from pathlib import Path
from typing import List, Tuple, Dict

MDIF_HEADER_TOKENS = [
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
DEFAULT_KEY = "NB"


def run(
    base_path: Path,
    temperature: float,
    *,
    key: str = DEFAULT_KEY,
    out_name: str = None,
) -> None:
    """Generate a combined MDIF file for all matching *.s2p* measurements."""
    import parser
    from rf_measurements.utils import (
        discover_nets,
        ensure_plots_dir,
        write_mdif,
        write_bad_report,
    )

    nets = discover_nets(base_path)
    key = key.strip()
    pattern = f"*{key}*.s2p" if not key.lower().endswith(".s2p") else f"*{key}"
    good_blocks: List[Tuple[int, List[Dict]]] = []
    nets_without_files: List[str] = []
    bad_files: List[str] = []
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        matches = sorted(net.path.glob(pattern))
        if not matches:
            nets_without_files.append(net.name)
            continue

        s2p_path = matches[0]
        try:
            rows = parse_s2p_file(s2p_path)
            net_number = int(net.name.lstrip("E"))
            good_blocks.append((net_number, rows))
        except Exception as exc:
            bad_files.append(str(s2p_path))
            bad_files_by_net.setdefault(net.name, []).append((str(s2p_path), str(exc)))
            continue

    plots_dir = ensure_plots_dir(base_path)
    mdif_name = out_name or f"measured_{key.replace('.s2p', '')}.mdif"
    mdif_path = plots_dir / mdif_name
    write_mdif(mdif_path, temperature, good_blocks, header_tokens=MDIF_HEADER_TOKENS, kind="s2p")

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_files,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="s2p",
    )