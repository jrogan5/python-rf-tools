"""IMD‑sweep converter."""

from pathlib import Path
from typing import Dict, List, Tuple

MDIF_HEADER_TOKENS = [
    "%freq(real)",
    "Pout_dBm(real)",
    "Pin_dBm(real)",
    "P3f(real)",
    "Gain_dB(real)",
    "IMD3(real)",
    "OIP3(real)",
    "IIP3(real)",
]
CSV_GLOBS = ("*IMD_Swp*.csv", "*SWP_IMD*.csv")
FREQ_COLUMN_NAME = "FrequencyFC"


def run(base_path: Path, temperature: float, *, out_name: str = "RDI_IMD_sweep.mdif") -> None:
    """Generate a combined MDIF file for all IMD‑sweep measurements."""
    from .parser import parse_imd_csv
    from utils.net import discover_nets
    from utils.mdif import write_mdif
    from utils.io import write_bad_report, ensure_plots_dir
    from utils.cli import validate_temperature

    validate_temperature(temperature)

    nets = discover_nets(base_path)
    good_blocks: List[Tuple[int, List[Dict]]] = []
    nets_without_csv: List[str] = []
    bad_files: List[str] = []
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        csv_paths = []
        for pattern in CSV_GLOBS:
            csv_paths.extend(sorted(net.path.glob(pattern)))
        if not csv_paths:
            nets_without_csv.append(net.name)
            continue

        net_number = int(net.name.lstrip("Ee"))
        csv_path = csv_paths[0]
        try:
            rows = parse_imd_csv(csv_path, freq_col=FREQ_COLUMN_NAME)
            good_blocks.append((net_number, rows))
        except Exception as exc:
            bad_files.append(str(csv_path))
            bad_files_by_net.setdefault(net.name, []).append((str(csv_path), str(exc)))

    mdif_blocks = [
        (
            {"Net": net_number, "Temperature": temperature},
            [
                {
                    "freq": r["frequency_hz"],
                    "pout_dbm": r["pout_dbm"],
                    "pin_dbm": r["pin_dbm"],
                    "p3f": r["p3f"],
                    "gain_db": r["gain_db"],
                    "imd3": r["imd3"],
                    "oip3": r["oip3"],
                    "iip3": r["iip3"],
                }
                for r in rows
            ],
        )
        for net_number, rows in good_blocks
    ]

    plots_dir = ensure_plots_dir(base_path)
    write_mdif(plots_dir / out_name, mdif_blocks, header_tokens=MDIF_HEADER_TOKENS)

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_csv,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="imd-sweep",
    )
