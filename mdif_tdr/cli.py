#!/usr/bin/env python3
"""CLI for MDIF time-domain transform (TDR) and gating.

Usage examples
--------------
TDR:
  rf-mdif-tdr tdr input.mdif output_tdr.mdif
  rf-mdif-tdr tdr input.mdif output_tdr.mdif --zpad 16 --window hann

Gate:
  rf-mdif-tdr gate input.mdif output_gated.mdif --t-start 0.2 --t-stop 1.5
  rf-mdif-tdr gate input.mdif output_gated.mdif --t-start 0.2 --t-stop 1.5 --taper 0.05
  (all times in nanoseconds)

Run with no arguments for an interactive prompt.
"""

import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mdif_tdr.converter import run_tdr, run_gate
from utils.cli import prompt_missing, prompt_validated

_MENU = """
Select operation:

  1  TDR   – IFFT of S-parameters → reflection magnitude vs time.
             Use this to locate impedance mismatches along a transmission path.
             Output is a time-domain MDIF (independent variable: time in seconds).

  2  Gate  – Apply a time-domain gate to isolate one reflection, then transform
             back to frequency domain.  Use this to strip fixture reflections and
             recover the DUT's intrinsic S-parameters.
             Output is a frequency-domain MDIF (same structure as the input).

Enter 1 or 2: """


def _prompt_existing_file(label: str) -> Path:
    def validate(s):
        p = Path(s)
        return (True, p) if p.is_file() else (False, f"File not found: {p}")
    return prompt_validated(label, validate)


def _prompt_output_path(label: str) -> Path:
    def validate(s):
        if not s:
            return (False, "Path cannot be empty.")
        return (True, Path(s))
    return prompt_validated(label, validate)


def _prompt_float_positive(label: str) -> float:
    def validate(s):
        try:
            v = float(s)
            if v < 0:
                return (False, "Value must be >= 0.")
            return (True, v)
        except ValueError:
            return (False, f"Not a valid number: {s!r}")
    return prompt_validated(label, validate)


def _prompt_common() -> dict:
    input_path  = _prompt_existing_file("Input MDIF file")
    output_path = _prompt_output_path("Output MDIF file")

    print("\nAdvanced options (press Enter to accept defaults):")

    raw_zpad = input("  Zero-padding factor [8]: ").strip()
    zpad = int(raw_zpad) if raw_zpad else 8

    raw_window = input("  Window function — kaiser / hann [kaiser]: ").strip().lower()
    window = raw_window if raw_window in ("kaiser", "hann") else "kaiser"

    beta = 6.0
    if window == "kaiser":
        raw_beta = input("  Kaiser beta [6.0]: ").strip()
        beta = float(raw_beta) if raw_beta else 6.0

    return dict(input_path=input_path, output_path=output_path,
                zpad=zpad, window=window, beta=beta)


def _run_interactive() -> None:
    choice = input(_MENU).strip()
    if choice not in ("1", "2"):
        sys.exit(f"[ERROR] Unknown option: '{choice}'")

    common = _prompt_common()

    if choice == "1":
        print(f"\nComputing TDR: {common['input_path'].name} → {common['output_path'].name}")
        run_tdr(
            common["input_path"],
            common["output_path"],
            zpad=common["zpad"],
            window=common["window"],
            beta=common["beta"],
        )
        print("Done.")

    else:
        print("\nGate time range (nanoseconds):")
        t_start = _prompt_float_positive("  Gate start (ns)")
        t_stop  = _prompt_float_positive("  Gate stop  (ns)")

        raw_taper = input("  Taper width on each edge (ns) [0.1]: ").strip()
        taper = float(raw_taper) if raw_taper else 0.1

        print(
            f"\nGating: {common['input_path'].name} → {common['output_path'].name}  "
            f"[{t_start} ns … {t_stop} ns, taper={taper} ns]"
        )
        run_gate(
            common["input_path"],
            common["output_path"],
            t_start=t_start * 1e-9,
            t_stop=t_stop   * 1e-9,
            taper=taper     * 1e-9,
            zpad=common["zpad"],
            window=common["window"],
            beta=common["beta"],
        )
        print("Done.")


# ── argparse helpers ──────────────────────────────────────────────────────────

def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("input",  type=Path, help="Input MDIF file (frequency-domain S-parameters).")
    p.add_argument("output", type=Path, help="Output MDIF file path.")
    p.add_argument("--zpad",   type=int,   default=8,      metavar="N",
                   help="Zero-padding factor (default: 8).")
    p.add_argument("--window", choices=["kaiser", "hann"], default="kaiser",
                   help="Spectral window function (default: kaiser).")
    p.add_argument("--beta",   type=float, default=6.0,
                   help="Kaiser beta parameter (default: 6.0, ignored for hann).")


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="rf-mdif-tdr",
        description="Time-domain transform and gating for MDIF S-parameter files.",
    )
    sub = root.add_subparsers(dest="command")

    p_tdr = sub.add_parser("tdr",  help="IFFT each S-parameter block → magnitude (dB) vs time MDIF.")
    _add_common_args(p_tdr)

    p_gate = sub.add_parser("gate", help="Time-domain gate each S-parameter → gated frequency-domain MDIF.")
    _add_common_args(p_gate)
    p_gate.add_argument("--t-start", type=float, required=True, metavar="NS",
                        help="Gate start time in nanoseconds.")
    p_gate.add_argument("--t-stop",  type=float, required=True, metavar="NS",
                        help="Gate stop time in nanoseconds.")
    p_gate.add_argument("--taper",   type=float, default=0.1, metavar="NS",
                        help="Raised-cosine taper width on each gate edge in ns (default: 0.1).")

    return root


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = _build_parser().parse_args()

    if args.command is None:
        try:
            _run_interactive()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
        return

    if not args.input.is_file():
        sys.exit(f"[ERROR] Input file not found: {args.input}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.command == "tdr":
            print(f"Computing TDR: {args.input.name} → {args.output.name}")
            run_tdr(args.input, args.output, zpad=args.zpad, window=args.window, beta=args.beta)
            print("Done.")

        elif args.command == "gate":
            print(
                f"Gating: {args.input.name} → {args.output.name}  "
                f"[{args.t_start} ns … {args.t_stop} ns, taper={args.taper} ns]"
            )
            run_gate(
                args.input, args.output,
                t_start=args.t_start * 1e-9,
                t_stop=args.t_stop   * 1e-9,
                taper=args.taper     * 1e-9,
                zpad=args.zpad, window=args.window, beta=args.beta,
            )
            print("Done.")

    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
