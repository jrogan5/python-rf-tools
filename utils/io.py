"""I/O helpers that are used by the converters."""

from pathlib import Path
import logging
from typing import List, Tuple, Dict

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
    problems: List[str] = None,
    bad_files: List[str] = None,
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = None,
    kind: str = "",
) -> None:
    """
    Write a human‑readable “bad‑measurement” report.

    The file is placed in ``<base_path>/plots`` and is named
    ``<kind>_bad_measurements.txt`` (or simply ``bad_measurements.txt`` when
    *kind* is empty).
    """
    plots = base_path / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    name = f"{kind.replace(' ', '_')}_bad_measurements.txt" if kind else "bad_measurements.txt"
    report_path = plots / name

    lines: List[str] = []

    if problems:
        lines.append("! Measurements with problems:\n")
        for n in sorted(problems):
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
        f"A detailed malformed measurement report has been written to: {report_path}"
    )

    