# rf_measurements/gain/converter.py
"""
Gain‑compression converter.

Uses the shared utils package to discover nets, parse CSVs, write a
combined MDIF file and a bad‑measurement report.
"""

from pathlib import Path
from typing import List, Tuple, Dict

MDIF_HEADER_TOKENS = [
    "%Pin_dBm(real)",
    "S21_dB(real)",
    "S21_degree(real)",
    "Pin_degree(real)",
    "Pout_dBm(real)",
    "Pout_degree(real)",
]
CSV_GLOB = "*Gain_Comp*.csv"
FREQ_REGEX = r"!CW\s+Freq:\s*([0-9]+)\s*Hz"



def run(base_path: Path, temperature: float, *, out_name: str = "RDI_gain_compression.mdif") -> None:
    """Generate a combined MDIF file for all gain‑compression measurements."""
    from parser import parse_gain_csv
    from rf_measurements.utils.freq import extract_frequency          
    from rf_measurements.utils.net  import discover_nets 
    from rf_measurements.utils.mdif import write_mdif                
    from rf_measurements.utils.io   import write_bad_report, ensure_plots_dir

    nets = discover_nets(base_path)
    good_blocks: List[Tuple[int, int, Dict]] = []
    nets_without_csv: List[str] = []
    bad_files: List[str] = []
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        csv_paths = sorted(net.path.glob(CSV_GLOB))
        if not csv_paths:
            nets_without_csv.append(net.name)
            continue

        net_number = int(net.name.lstrip("E"))
        net_is_bad = False
        for csv_path in csv_paths:
            try:
                freq_hz = extract_frequency(csv_path, FREQ_REGEX)
                block = parse_gain_csv(csv_path)
                good_blocks.append((net_number, freq_hz, block))
            except Exception as exc:
                bad_files.append(str(csv_path))
                bad_files_by_net.setdefault(net.name, []).append((str(csv_path), str(exc)))
                net_is_bad = True
                break
        if net_is_bad:
            good_blocks = [b for b in good_blocks if b[0] != net_number]

    plots_dir = ensure_plots_dir(base_path)
    mdif_path = plots_dir / out_name
    write_mdif(mdif_path, temperature, good_blocks, header_tokens=MDIF_HEADER_TOKENS)

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_csv,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="gain‑compression",
    )