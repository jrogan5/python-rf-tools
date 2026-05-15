"""S‑parameter (*.s2p) converter."""

from pathlib import Path
from typing import Dict, List, Tuple

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
    """Generate a combined MDIF file for all matching *.s2p measurements."""
    from .parser import parse_s2p_file
    from utils.net import discover_nets
    from utils.mdif import write_mdif
    from utils.io import write_bad_report, ensure_plots_dir
    from utils.cli import validate_temperature

    validate_temperature(temperature)

    nets = discover_nets(base_path)
    key = key.strip()
    pattern = f"*{key}*.s2p" if not key.lower().endswith(".s2p") else f"*{key}"
    good_blocks: List[Tuple[int, List[Dict]]] = []
    nets_without_csv: List[str] = []
    bad_files: List[str] = []
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        matches = sorted(net.path.glob(pattern))
        if not matches:
            nets_without_csv.append(net.name)
            continue

        net_number = int(net.name.lstrip("Ee"))
        s2p_path = matches[0]
        try:
            rows = parse_s2p_file(s2p_path)
            good_blocks.append((net_number, rows))
        except Exception as exc:
            bad_files.append(str(s2p_path))
            bad_files_by_net.setdefault(net.name, []).append((str(s2p_path), str(exc)))

    mdif_blocks = [
        (
            {"Net": net_number, "Temperature": temperature},
            [
                {
                    "freq": r["freq_hz"],
                    "s11_db": r["s11_mag"],
                    "s11_deg": r["s11_phase"],
                    "s21_db": r["s21_mag"],
                    "s21_deg": r["s21_phase"],
                    "s12_db": r["s12_mag"],
                    "s12_deg": r["s12_phase"],
                    "s22_db": r["s22_mag"],
                    "s22_deg": r["s22_phase"],
                }
                for r in rows
            ],
        )
        for net_number, rows in good_blocks
    ]

    plots_dir = ensure_plots_dir(base_path)
    mdif_name = out_name or f"measured_{key.replace('.s2p', '')}.mdif"
    write_mdif(plots_dir / mdif_name, mdif_blocks, header_tokens=MDIF_HEADER_TOKENS)

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_csv,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="s2p",
    )
