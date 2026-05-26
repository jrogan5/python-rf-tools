"""Convert DBF .mat measurement files to a combined MDIF file."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MDIF_HEADER_TOKENS = ["%freq(real)", "s11_db(real)", "s11_deg(real)"]


# ── directory helpers ─────────────────────────────────────────────────────────

def _parse_path_id(stem: str) -> Optional[Dict]:
    """
    Parse 'ADC0-P1-J201' into {ADC, RefDesDBF}.
    Returns None if the filename does not match the expected pattern.
    """
    m = re.match(r"ADC(\d+)-P(\d+)-J(\d+)", stem, re.IGNORECASE)
    if not m:
        return None
    return {
        "ADC": int(m.group(1)),
        "RefDesDBF": int(m.group(3)),
    }


def _find_acq_dir(test_dir: Path, powered: bool) -> Optional[Path]:
    """
    Find the most-recent acq_* sub-directory inside the powered or unpowered
    measurement folder.  Identified by 'powered'/'unpowered' in folder name.
    When searching for 'powered', folders that also contain 'unpowered' are skipped.
    """
    keyword = "powered" if powered else "unpowered"

    for folder in sorted(test_dir.iterdir()):
        if not folder.is_dir():
            continue
        name_lower = folder.name.lower()
        if keyword not in name_lower:
            continue
        if powered and "unpowered" in name_lower:
            continue
        acq_dirs = sorted(folder.glob("acq_*"))
        if acq_dirs:
            return acq_dirs[-1]  # most recent acquisition
    return None


# ── public API ────────────────────────────────────────────────────────────────

def run(
    top_dir: Path,
    powered: bool,
    *,
    out_name: Optional[str] = None,
) -> Path:
    """
    Walk *top_dir* (e.g. RX_Meas/), treating each sub-directory as one test
    session that contains:
      - exactly one  ADC*-P*-J*.txt  path-identifier file
      - a powered or unpowered measurement folder with an acq_*/ sub-directory
        containing one or more .mat files

    All sessions are combined into a single MDIF file written to
    <top_dir>/plots/<out_name>.

    Returns the path of the written MDIF file.
    Skipped sessions are reported in <top_dir>/plots/dbf_skipped.txt.
    """
    from .parser import parse_mat_file
    from utils.mdif import write_mdif
    from utils.io import ensure_plots_dir

    test_dirs = sorted(d for d in top_dir.iterdir() if d.is_dir() and d.name != "plots")
    if not test_dirs:
        raise FileNotFoundError(f"No test sub-directories found under {top_dir}")

    blocks: List[Tuple[Dict, List[Dict]]] = []
    skipped: List[Tuple[str, str]] = []

    for test_dir in test_dirs:
        # ── find the path-identifier txt file ────────────────────
        txt_files = [
            f for f in test_dir.glob("*.txt")
            if re.match(r"ADC\d+-P\d+-J\d+", f.stem, re.IGNORECASE)
        ]
        if not txt_files:
            skipped.append((test_dir.name, "no ADC*-P*-J*.txt path-identifier file found"))
            continue

        id_file = txt_files[0]
        info = _parse_path_id(id_file.stem)
        if info is None:
            skipped.append((test_dir.name, f"'{id_file.name}' did not match ADC*-P*-J* pattern"))
            continue

        label = id_file.stem  # e.g. "ADC0-P1-J201"

        # ── find the acquisition directory ────────────────────────
        acq_dir = _find_acq_dir(test_dir, powered)
        if acq_dir is None:
            kind = "powered" if powered else "unpowered"
            skipped.append((test_dir.name, f"no {kind} acq_* directory found"))
            continue

        # ── find the mat file (take the first; one per session) ───
        mat_files = list(acq_dir.glob("*.mat"))
        if not mat_files:
            skipped.append((test_dir.name, f"no .mat file found in {acq_dir.name}"))
            continue

        mat_path = mat_files[0]

        # ── parse measurement data ────────────────────────────────
        try:
            rows = parse_mat_file(mat_path)
        except Exception as exc:
            skipped.append((test_dir.name, f"{mat_path.name}: {exc}"))
            continue

        meta = {"ADC": info["ADC"], "RefDesDBF": info["RefDesDBF"]}
        data_rows = [
            {"freq": r["freq_ghz"], "s11_db": r["s11_db"], "s11_deg": r["s11_deg"]}
            for r in rows
        ]
        blocks.append((meta, data_rows))

    # ── write outputs ─────────────────────────────────────────────
    plots_dir = ensure_plots_dir(top_dir)

    if skipped:
        report = plots_dir / "dbf_skipped.txt"
        report.write_text("\n".join(f"{name}: {reason}" for name, reason in skipped))
        print(f"  [WARN] {len(skipped)} session(s) skipped — see {report}")

    if not blocks:
        reasons = "\n  ".join(f"{n}: {r}" for n, r in skipped)
        raise RuntimeError(f"No data blocks could be converted.\n  {reasons}")

    power_label = "powered" if powered else "unpowered"
    mdif_name = out_name or f"dbf_s11_{power_label}.mdif"
    out_path = plots_dir / mdif_name
    write_mdif(out_path, blocks, header_tokens=MDIF_HEADER_TOKENS)

    return out_path
