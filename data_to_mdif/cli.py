#!/usr/bin/env python3
"""
RF Measurements MDIF Generator
Unified interactive CLI that drives all four converters.

Run directly:  python data_to_mdif/cli.py
Or as module:  python -m data_to_mdif.cli
After install: rf-mdif
"""

import sys
from pathlib import Path

# Ensure the package root is importable when run directly (not needed when frozen).
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.cli import prompt_missing, validate_temperature, TEMP_MIN, TEMP_MAX
from _version import __version__ as VERSION

_BANNER = f"""
╔══════════════════════════════════════════════════════╗
║       RF Measurements MDIF Generator  v{VERSION}         ║
║                                                      ║
║  Combines measurement files into MDIF format for     ║
║  use with ADS and similar EDA tools.                 ║
╚══════════════════════════════════════════════════════╝
"""

_DUT_MENU = """
Select device under test:

  1  RDI
  2  4‑pack

Enter one number: """

_MENU = """
Select measurement type(s) to process:

  1  Gain compression
  2  IMD sweep
  3  S‑parameters (single key, e.g. NB or WB)
  4  Noise figure
  5  Linear characterisation   (S‑params NB + S‑params WB + NF)
  6  Nonlinear characterisation (Gain compression + IMD sweep)
  7  Full characterisation      (all of the above)

Enter one number: """


def _prompt_base_path(hint: str) -> Path:
    while True:
        raw = prompt_missing(f"Data directory ({hint})", Path)
        if raw.is_dir():
            return raw
        print(f"  Directory not found: {raw}")


def _prompt_temperature() -> float:
    return prompt_missing(f"Test temperature in °C ({TEMP_MIN}…{TEMP_MAX})", float)


def _prompt_key(label: str, default: str) -> str:
    raw = input(f"Filename keyword for {label} [{default}]: ").strip()
    return raw or default


def _run_gain(base_path: Path, temperature: float) -> None:
    from data_to_mdif.gain.converter import run
    print("\n  → Running gain‑compression converter …")
    run(base_path, temperature)
    print("    Done.")


def _run_imd(base_path: Path, temperature: float) -> None:
    from data_to_mdif.imd.converter import run
    print("\n  → Running IMD‑sweep converter …")
    run(base_path, temperature)
    print("    Done.")


def _run_s2p(base_path: Path, temperature: float, key: str) -> None:
    from data_to_mdif.s2p.converter import run
    print(f"\n  → Running S‑parameter converter (key='{key}') …")
    run(base_path, temperature, key=key)
    print("    Done.")


def _run_nf(base_path: Path, temperature: float, key: str) -> None:
    from data_to_mdif.nf.converter import run
    print(f"\n  → Running NF‑sweep converter (key='{key}') …")
    run(base_path, temperature, key=key)
    print("    Done.")


def _run_4pack(base_path: Path) -> None:
    from data_to_mdif.s2p.sparam_nf_to_mdif import convert
    output_path = base_path / "plots"
    print("\n  → Running 4‑pack S‑parameter + NF converter …")
    convert(base_path, output_path)
    print("    Done.")


def _main_rdi() -> None:
    base_path = _prompt_base_path("containing E1, E2, … sub‑folders")
    temperature = _prompt_temperature()

    try:
        validate_temperature(temperature)
    except ValueError as exc:
        sys.exit(f"[ERROR] {exc}")

    choice = input(_MENU).strip()

    errors = []

    def _safe(fn, *a, **kw):
        try:
            fn(*a, **kw)
        except Exception as exc:
            errors.append(str(exc))
            print(f"    [WARN] {exc}")

    if choice == "1":
        _safe(_run_gain, base_path, temperature)

    elif choice == "2":
        _safe(_run_imd, base_path, temperature)

    elif choice == "3":
        key = _prompt_key("S‑parameter files", "NB")
        _safe(_run_s2p, base_path, temperature, key)

    elif choice == "4":
        key = _prompt_key("NF files", "NF")
        _safe(_run_nf, base_path, temperature, key)

    elif choice == "5":
        nb_key  = _prompt_key("narrowband S‑parameter files", "NB")
        wb_key  = _prompt_key("wideband S‑parameter files", "WB")
        nf_key  = _prompt_key("NF files", "NF")
        _safe(_run_s2p, base_path, temperature, nb_key)
        _safe(_run_s2p, base_path, temperature, wb_key)
        _safe(_run_nf,  base_path, temperature, nf_key)

    elif choice == "6":
        _safe(_run_gain, base_path, temperature)
        _safe(_run_imd,  base_path, temperature)

    elif choice == "7":
        nb_key  = _prompt_key("narrowband S‑parameter files", "NB")
        wb_key  = _prompt_key("wideband S‑parameter files", "WB")
        nf_key  = _prompt_key("NF files", "NF")
        _safe(_run_gain, base_path, temperature)
        _safe(_run_imd,  base_path, temperature)
        _safe(_run_s2p,  base_path, temperature, nb_key)
        _safe(_run_s2p,  base_path, temperature, wb_key)
        _safe(_run_nf,   base_path, temperature, nf_key)

    else:
        sys.exit(f"[ERROR] Unknown option: '{choice}'")

    plots_dir = base_path / "plots"
    print(f"\n{'='*54}")
    if errors:
        print(f"Finished with {len(errors)} error(s) — check the output above.")
    else:
        print("All conversions completed successfully.")
    print(f"Output files written to: {plots_dir}")
    print('='*54)


def _main_4pack() -> None:
    base_path = _prompt_base_path("containing RXEM sub‑folders")

    errors = []
    try:
        _run_4pack(base_path)
    except Exception as exc:
        errors.append(str(exc))
        print(f"    [WARN] {exc}")

    plots_dir = base_path / "plots"
    print(f"\n{'='*54}")
    if errors:
        print(f"Finished with {len(errors)} error(s) — check the output above.")
    else:
        print("All conversions completed successfully.")
    print(f"Output files written to: {plots_dir}")
    print('='*54)


def main() -> None:
    print(_BANNER)

    dut = input(_DUT_MENU).strip()

    if dut == "1":
        _main_rdi()
    elif dut == "2":
        _main_4pack()
    else:
        sys.exit(f"[ERROR] Unknown option: '{dut}'")


if __name__ == "__main__":
    main()
