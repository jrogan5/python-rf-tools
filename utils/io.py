"""I/O helpers that are used by the converters."""

from pathlib import Path
import logging
from typing import List, Tuple, Dict, Optional

def ensure_plots_dir(root: Path) -> Path:
    """Create (if needed) a plots sub‑folder under root and return its Path."""
    plots = root / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    return plots

def setup_logging(verbose: bool) -> None:
    """Configure a simple console logger (DEBUG if *verbose*, else INFO)."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def write_bad_report(
    base_path: Path,
    *,
    nets_without_csv: Optional[List[str]] = None,
    bad_files: Optional[List[str]] = None,
    bad_files_by_net: Optional[Dict[str, List[Tuple[str, str]]]] = None,
    kind: str = "",
) -> None:
    """
    Write a human‑readable bad‑measurement report to ``<base_path>/plots/``.

    The file is named ``<kind>_bad_measurements.txt`` (or ``bad_measurements.txt``
    when *kind* is empty).  Nothing is written if all inputs are empty.
    """
    plots = base_path / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    name = f"{kind.replace(' ', '_')}_bad_measurements.txt" if kind else "bad_measurements.txt"
    report_path = plots / name

    lines: List[str] = []

    if nets_without_csv:
        lines.append(f"! Nets with no {kind} files (omitted from MDIF):\n")
        for n in sorted(nets_without_csv):
            lines.append(f"!   {n}\n")
        lines.append("\n")

    if bad_files_by_net:
        lines.append("! Nets that contain malformed files (entire net omitted):\n")
        for net, entries in sorted(bad_files_by_net.items()):
            lines.append(f"!   Net {net}:\n")
            for fp, msg in entries:
                safe = msg.replace("\n", " | ")
                lines.append(f"!     {fp}\n")
                lines.append(f"!     Reason: {safe}\n")
            lines.append("\n")

    if bad_files:
        lines.append("! Flat list of all bad files (for scripts):\n")
        for p in bad_files:
            lines.append(f"{p}\n")

    if not lines:
        return

    report_path.write_text("".join(lines))
    logging.getLogger(__name__).info(
        f"Bad‑measurement report written to: {report_path}"
    )
