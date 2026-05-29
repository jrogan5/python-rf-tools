#!/usr/bin/env python3
"""Convert an S11 MDIF file to a folder of Touchstone .s1p files.

Each ACDATA block in the MDIF becomes one .s1p file.  The filename encodes
the block's VAR values so files are self-descriptive.

Usage (CLI):
  python -m utils.mdif_to_s1p input.mdif output_folder/
  python -m utils.mdif_to_s1p input.mdif output_folder/ --limit 10
  python -m utils.mdif_to_s1p input.mdif output_folder/ --limit 10 --freq-unit MHz

Programmatic:
  from utils.mdif_to_s1p import mdif_to_s1p_folder
  mdif_to_s1p_folder(Path("input.mdif"), Path("out/"), limit=10)
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.mdif import read_mdif


# ── Touchstone writer ─────────────────────────────────────────────────────────

_FREQ_SCALES = {
    "hz":  1.0,
    "khz": 1e3,
    "mhz": 1e6,
    "ghz": 1e9,
}


def _write_s1p(
    path: Path,
    freq_hz: np.ndarray,
    s11_db: np.ndarray,
    s11_deg: np.ndarray,
    freq_unit: str = "Hz",
    z0: float = 50.0,
    comments: Optional[List[str]] = None,
) -> None:
    scale = _FREQ_SCALES[freq_unit.lower()]
    lines = []

    if comments:
        for c in comments:
            lines.append(f"! {c}\n")

    lines.append(f"# {freq_unit} S DB R {z0:.6g}\n")
    lines.append("! freq             S11(dB)       S11(deg)\n")

    for f, db, deg in zip(freq_hz, s11_db, s11_deg):
        lines.append(f"{f / scale:<18.6g}{db:<14.6g}{deg:.6g}\n")

    path.write_text("".join(lines))


# ── filename builder ──────────────────────────────────────────────────────────

def _block_filename(idx: int, meta: dict) -> str:
    """Build a filename from block index and VAR metadata."""
    if not meta:
        return f"block_{idx:04d}.s1p"
    parts = [f"{k}{_fmt_var(v)}" for k, v in meta.items()]
    return "_".join(parts) + ".s1p"


def _fmt_var(v) -> str:
    """Format a VAR value for use in a filename (no spaces, no dots for integers)."""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).replace(".", "p").replace("-", "m")


# ── public API ────────────────────────────────────────────────────────────────

def mdif_to_s1p_folder(
    mdif_path: Path,
    out_dir: Path,
    *,
    limit: Optional[int] = None,
    freq_unit: str = "Hz",
    z0: float = 50.0,
) -> List[Path]:
    """
    Convert each block in an S11 MDIF to a .s1p Touchstone file.

    Parameters
    ----------
    mdif_path  : input MDIF (must contain freq, s11_db, s11_deg columns)
    out_dir    : output directory (created if it does not exist)
    limit      : maximum number of blocks to convert (None = all)
    freq_unit  : frequency unit in the .s1p header — Hz / KHz / MHz / GHz
    z0         : reference impedance written into the Touchstone header

    Returns
    -------
    List of Path objects for every .s1p file written.
    """
    if freq_unit.lower() not in _FREQ_SCALES:
        raise ValueError(f"freq_unit must be one of {list(_FREQ_SCALES)}; got {freq_unit!r}")

    meta_arr, data_blocks = read_mdif(mdif_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    blocks_to_write = data_blocks[:limit] if limit is not None else data_blocks
    written: List[Path] = []

    for idx, block in enumerate(blocks_to_write):
        freq   = block.get("freq")
        s11_db  = block.get("s11_db")
        s11_deg = block.get("s11_deg")

        if freq is None or s11_db is None or s11_deg is None:
            print(f"  [SKIP] Block {idx}: missing freq / s11_db / s11_deg columns.")
            continue

        meta = dict(meta_arr[idx]) if idx < len(meta_arr) else {}
        fname = _block_filename(idx, meta)
        out_path = out_dir / fname

        # Build a comment block with the VAR metadata so the file is self-documenting
        comments = [f"{k} = {_fmt_var(v)}" for k, v in meta.items()] if meta else []

        _write_s1p(out_path, freq, s11_db, s11_deg,
                   freq_unit=freq_unit, z0=z0, comments=comments)
        written.append(out_path)

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert an S11 MDIF file to a folder of .s1p Touchstone files."
    )
    p.add_argument("input",   type=Path, help="Input MDIF file.")
    p.add_argument("out_dir", type=Path, help="Output directory (created if needed).")
    p.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Only write the first N blocks (default: write all).",
    )
    p.add_argument(
        "--freq-unit", default="Hz", metavar="UNIT",
        choices=["Hz", "KHz", "MHz", "GHz"],
        help="Frequency unit in the Touchstone header (default: Hz).",
    )
    p.add_argument(
        "--z0", type=float, default=50.0,
        help="Reference impedance in Ohms (default: 50).",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.input.is_file():
        sys.exit(f"[ERROR] File not found: {args.input}")

    try:
        written = mdif_to_s1p_folder(
            args.input,
            args.out_dir,
            limit=args.limit,
            freq_unit=args.freq_unit,
            z0=args.z0,
        )
    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")

    print(f"Wrote {len(written)} .s1p file(s) to {args.out_dir}/")
    for p in written:
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
