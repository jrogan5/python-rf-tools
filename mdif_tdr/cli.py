
#!/usr/bin/env python3
"""TDR analysis tool for MDIF S11 files.

Usage
-----
  rf-mdif-tdr  input.mdif
  rf-mdif-tdr  input.mdif  -o out_tdr.mdif  --vf 0.66  --t-max-ns 20
  rf-mdif-tdr  input.mdif  -p s11  --npad 40  --window-beta 13

Run with no arguments for an interactive file prompt.
"""

import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mdif_tdr.converter import run, _validate_block
from utils.mdif import read_mdif
from utils.cli import prompt_validated


# ── interactive helpers ───────────────────────────────────────────────────────

def _prompt_existing_file(label: str) -> Path:
    def validate(s):
        p = Path(s)
        return (True, p) if p.is_file() else (False, f"File not found: {p}")
    return prompt_validated(label, validate)


def _select_param(data_blocks) -> str:
    """
    If every block has s11_db/s11_deg, proceed silently.
    Otherwise list available S-param pairs and prompt.
    """
    import re
    # Collect all distinct S-param base names across all blocks
    all_params: set = set()
    for block in data_blocks:
        for col in block:
            m = re.match(r"(s\d+)_db$", col, re.IGNORECASE)
            if m and f"{m.group(1)}_deg" in block:
                all_params.add(m.group(1).lower())

    if not all_params:
        print("[ERROR] No S-parameter column pairs (sXX_db / sXX_deg) found.")
        sys.exit(1)

    if len(all_params) == 1:
        return all_params.pop()

    params = sorted(all_params)
    print("\nMultiple S-parameters found:")
    for i, p in enumerate(params, 1):
        print(f"  {i}  {p}")

    while True:
        raw = input("Choose parameter (number or name): ").strip().lower()
        if raw in params:
            return raw
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(params):
                return params[idx]
        except ValueError:
            pass
        print(f"  Enter a number 1–{len(params)} or one of {params}")


def _print_summary(s: dict) -> None:
    c = 2.998e8
    vp = s["vf"] * c
    print()
    print("=" * 60)
    print(f"  Input  : {s['input_path'].name}  ({s['n_blocks']} block(s))")
    print(f"  Output : {s['output_path']}")
    print()
    print(f"  Freq range : {s['f_min_GHz']:.4f} – {s['f_max_GHz']:.4f} GHz")
    print(f"  Points     : {s['N']}   step = {s['df_MHz']:.4f} MHz")
    print()
    if s["vf"] != 1.0:
        print(f"  Spatial resolution (vf=1.0) : {s['res_mm'] / s['vf']:.2f} mm")
        print(f"  Spatial resolution (vf={s['vf']:.2f}): {s['res_mm']:.2f} mm")
        print(f"  Max range          (vf=1.0) : {s['range_m'] / s['vf']:.3f} m")
        print(f"  Max range          (vf={s['vf']:.2f}): {s['range_m']:.3f} m")
    else:
        print(f"  Spatial resolution : {s['res_mm']:.2f} mm")
        print(f"  Max range          : {s['range_m']:.3f} m")
    print()
    print(f"  Largest impulse peak:")
    print(f"    t      = {s['peak_t_ns']:.4f} ns")
    print(f"    Γ(imp) = {s['peak_impulse']:.4f}")
    print(f"    Γ(step)= {s['peak_step']:.4f}")
    print("=" * 60)
    print()


# ── argparse ──────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rf-mdif-tdr",
        description="TDR analysis: convert an S11 MDIF to impulse / step / impedance vs time.",
    )
    p.add_argument("input", nargs="?", type=Path,
                   help="Input MDIF file (omit for interactive file prompt).")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Output MDIF path (default: <input_stem>_tdr.mdif).")
    p.add_argument("-p", "--param", default=None,
                   help="S-parameter to use, e.g. s11 (default: auto-select / prompt).")
    p.add_argument("--vf", type=float, default=1.0,
                   help="Velocity factor vp/c for distance axis (default: 1.0).")
    p.add_argument("--window-beta", type=float, default=6.0, dest="beta",
                   help="Kaiser window beta (default: 6).")
    p.add_argument("--npad", type=int, default=20,
                   help="Zero-padding factor (default: 20).")
    p.add_argument("--z0", type=float, default=50.0,
                   help="Reference impedance in Ohms (default: 50).")
    p.add_argument("--t-max-ns", type=float, default=10, dest="t_max_ns",
                   help="Truncate output to first N nanoseconds (default: 10ns).")
    return p


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = _build_parser().parse_args()

    # Resolve input path (prompt if not supplied)
    if args.input is None:
        input_path = _prompt_existing_file("Input MDIF file")
    else:
        input_path = args.input
        if not input_path.is_file():
            sys.exit(f"[ERROR] File not found: {input_path}")

    # Validate vf
    if not (0 < args.vf <= 1.0):
        print(f"[WARNING] --vf {args.vf} is outside (0, 1]. Results may be unphysical.")

    # Resolve output path
    output_path = args.output or input_path.with_name(input_path.stem + "_tdr.mdif")

    # Peek at the file to do param selection before the main run
    try:
        _, data_blocks = read_mdif(input_path)
    except Exception as exc:
        sys.exit(f"[ERROR] Could not read {input_path}: {exc}")

    if not data_blocks:
        sys.exit(f"[ERROR] No data blocks found in {input_path}")

    # Param selection (may prompt interactively)
    param = args.param or _select_param(data_blocks)

    # Validate the first block has the expected columns
    block0 = data_blocks[0]
    # Remap generic param name to actual columns expected by _validate_block
    if param != "s11":
        # Remap: rename the chosen param's columns to s11_db/s11_deg for the converter
        # (converter currently only handles s11; extend here if multi-param support needed)
        db_col  = f"{param}_db"
        deg_col = f"{param}_deg"
        if db_col not in block0 or deg_col not in block0:
            print(f"[ERROR] Columns {db_col!r} and/or {deg_col!r} not found.")
            print(f"  Available: {sorted(block0.keys())}")
            sys.exit(1)
        # Alias the chosen param into s11_db / s11_deg so the converter works
        data_blocks = [
            {**blk, "s11_db": blk[db_col], "s11_deg": blk[deg_col]}
            for blk in data_blocks
        ]

    try:
        _validate_block(data_blocks[0])
    except ValueError as exc:
        sys.exit(f"[ERROR] {exc}")

    # Run
    try:
        summary = run(
            input_path,
            output_path,
            vf=args.vf,
            beta=args.beta,
            npad=args.npad,
            z0=args.z0,
            t_max_ns=args.t_max_ns,
        )
    except ValueError as exc:
        sys.exit(f"[ERROR] {exc}")

    summary["input_path"]  = input_path
    summary["output_path"] = output_path
    summary["vf"]          = args.vf
    _print_summary(summary)


if __name__ == "__main__":
    main()
