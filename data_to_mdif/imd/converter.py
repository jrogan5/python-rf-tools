# rf_measurements/imd/converter.py
"""
IMD‑sweep converter.

Collects one CSV per net (matching *IMD_Swp* or *SWP_IMD*),
parses the data rows, and writes a single MDIF file.
"""

from pathlib import Path
from typing import List, Tuple, Dict

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
    from parser import parse_imd_csv
    from rf_measurements.utils.net  import discover_nets
    from rf_measurements.utils.mdif import write_mdif
    from rf_measurements.utils.io   import write_bad_report, ensure_plots_dir

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

        net_number = int(net.name.lstrip("E"))
        csv_path = csv_paths[0]
        try:
            rows = parse_imd_csv(csv_path, freq_col=FREQ_COLUMN_NAME)
            good_blocks.append((net_number, rows))
        except Exception as exc:
            bad_files.append(str(csv_path))
            bad_files_by_net.setdefault(net.name, []).append((str(csv_path), str(exc)))
            continue

    plots_dir = ensure_plots_dir(base_path)
    mdif_path = plots_dir / out_name
    write_mdif(mdif_path, temperature, good_blocks, header_tokens=MDIF_HEADER_TOKENS, kind="imd")

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_csv,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="imd‑sweep",
    )