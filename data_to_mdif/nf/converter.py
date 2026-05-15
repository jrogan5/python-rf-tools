"""Noise‑Figure (NF) sweep converter."""

from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_KEY = "NF"
MDIF_HEADER_TOKENS = ["%freq(real)", "nf_db(real)"]
FREQ_COLUMN_NAME = "Freq(Hz)"
NF_COLUMN_CANDIDATES = ("NF(DB)", "NF Log Mag(dB)", "NF(dB)", "NF")


def run(
    base_path: Path,
    temperature: float,
    *,
    key: str = DEFAULT_KEY,
    out_name: str = None,
) -> None:
    """Generate a combined MDIF file for the NF sweep."""
    from .parser import parse_nf_csv
    from utils.net import discover_nets
    from utils.mdif import write_mdif
    from utils.io import write_bad_report, ensure_plots_dir
    from utils.cli import validate_temperature

    validate_temperature(temperature)

    nets = discover_nets(base_path)
    pattern = f"*{key}*.csv" if not key.lower().endswith(".csv") else f"*{key}"
    good_blocks: List[Tuple[int, List[Dict]]] = []
    nets_without_csv: List[str] = []
    bad_files: List[str] = []
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        csv_paths = sorted(net.path.glob(pattern))
        if not csv_paths:
            nets_without_csv.append(net.name)
            continue

        net_number = int(net.name.lstrip("Ee"))
        csv_path = csv_paths[0]
        try:
            rows = parse_nf_csv(
                csv_path,
                freq_col=FREQ_COLUMN_NAME,
                nf_candidates=NF_COLUMN_CANDIDATES,
            )
            good_blocks.append((net_number, rows))
        except Exception as exc:
            bad_files.append(str(csv_path))
            bad_files_by_net.setdefault(net.name, []).append((str(csv_path), str(exc)))

    mdif_blocks = [
        (
            {"Net": net_number, "Temperature": temperature},
            [{"freq": r["frequency_hz"], "nf_db": r["nf_db"]} for r in rows],
        )
        for net_number, rows in good_blocks
    ]

    plots_dir = ensure_plots_dir(base_path)
    mdif_name = out_name or f"measured_{key.replace('.csv', '')}.mdif"
    write_mdif(plots_dir / mdif_name, mdif_blocks, header_tokens=MDIF_HEADER_TOKENS)

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_csv,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="nf",
    )
