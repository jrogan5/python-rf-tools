#!/usr/bin/env python3
"""CLI for MDIF time-domain transform (TDR) and gating.

Usage examples
--------------
TDR:
  rf-mdif-tdr tdr input.mdif output_tdr.mdif
  rf-mdif-tdr tdr input.mdif output_tdr.mdif --zpad 16 --window hann --debug

Gate (start/stop):
  rf-mdif-tdr gate input.mdif output_gated.mdif --t-start 0.2 --t-stop 1.5
  rf-mdif-tdr gate input.mdif output_gated.mdif --t-start 0.2 --t-stop 1.5 --taper 0.05 --debug

Gate (center/span, scikit-rf style):
  rf-mdif-tdr gate input.mdif output_gated.mdif --center 0.85 --span 1.3

All times in nanoseconds.  Run with no arguments for an interactive prompt.
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

  1  TDR   – IFFT of S-parameters → impulse magnitude (dB) vs time.
             Peaks in the output correspond to reflections along the signal path.
             Use this to locate impedance mismatches, connector faults, or cable
             discontinuities.  Output: time-domain MDIF.

             Debug mode also writes:
               *_step.mdif  – step response (ρ, linear reflection coefficient)
               *_zc.mdif    – characteristic impedance profile (Ohms)

  2  Gate  – Apply a time-domain gate to isolate one specific reflection, then
             transform back to frequency domain.  Use this to strip fixture or
             cable reflections and recover the DUT's intrinsic S-parameters.
             Gate position can be entered as start/stop or as centre + span.
             Output: frequency-domain MDIF (same structure as the input).

             Debug mode also writes:
               *_pregated_impulse.mdif  – impulse before gating
               *_gated_impulse.mdif     – impulse after gating (verify gate placement)

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
            return (True, v) if v >= 0 else (False, "Value must be >= 0.")
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

    raw_debug = input("  Write debug intermediate files? y / [n]: ").strip().lower()
    debug = raw_debug in ("y", "yes")

    return dict(input_path=input_path, output_path=output_path,
                zpad=zpad, window=window, beta=beta, debug=debug)


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
            debug=common["debug"],
        )
        if common["debug"]:
            stem = common["output_path"].stem
            print(f"  Debug files: {stem}_step.mdif, {stem}_zc.mdif")
        print("Done.")

    else:
        print("\nGate specification — enter start/stop OR centre/span (nanoseconds).")
        print("  Leave centre blank to use start/stop.")
        raw_centre = input("  Centre (ns) [blank = use start/stop]: ").strip()

        if raw_centre:
            center = float(raw_centre)
            span   = _prompt_float_positive("  Span (ns)")
            t_start_s = (center - span / 2.0) * 1e-9
            t_stop_s  = (center + span / 2.0) * 1e-9
            print(f"  → start={center - span/2:.3f} ns  stop={center + span/2:.3f} ns")
        else:
            t_start_ns = _prompt_float_positive("  Gate start (ns)")
            t_stop_ns  = _prompt_float_positive("  Gate stop  (ns)")
            t_start_s  = t_start_ns * 1e-9
            t_stop_s   = t_stop_ns  * 1e-9

        raw_taper = input("  Taper width on each edge (ns) [0.1]: ").strip()
        taper = float(raw_taper) * 1e-9 if raw_taper else 0.1e-9

        print(
            f"\nGating: {common['input_path'].name} → {common['output_path'].name}  "
            f"[{t_start_s*1e9:.3f} ns … {t_stop_s*1e9:.3f} ns, "
            f"taper={taper*1e9:.3f} ns]"
        )
        run_gate(
            common["input_path"],
            common["output_path"],
            t_start=t_start_s,
            t_stop=t_stop_s,
            taper=taper,
            zpad=common["zpad"],
            window=common["window"],
            beta=common["beta"],
            debug=common["debug"],
        )
        if common["debug"]:
            stem = common["output_path"].stem
            print(f"  Debug files: {stem}_pregated_impulse.mdif, {stem}_gated_impulse.mdif")
        print("Done.")


# ── argparse ──────────────────────────────────────────────────────────────────

def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("input",  type=Path, help="Input MDIF file.")
    p.add_argument("output", type=Path, help="Output MDIF file path.")
    p.add_argument("--zpad",   type=int,   default=8,  metavar="N",
                   help="Zero-padding factor (default: 8).")
    p.add_argument("--window", choices=["kaiser", "hann"], default="kaiser",
                   help="Spectral window (default: kaiser).")
    p.add_argument("--beta",   type=float, default=6.0,
                   help="Kaiser beta (default: 6.0, ignored for hann).")
    p.add_argument("--debug",  action="store_true",
                   help="Write intermediate debug MDIF files alongside the output.")


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="rf-mdif-tdr",
        description="Time-domain transform and gating for MDIF S-parameter files.",
    )
    sub = root.add_subparsers(dest="command")

    # tdr
    p_tdr = sub.add_parser("tdr", help="Impulse response (dB) vs time.")
    _add_common_args(p_tdr)
    p_tdr.add_argument("--z0", type=float, default=50.0,
                       help="Reference impedance in Ohms for Zc debug output (default: 50).")

    # gate
    p_gate = sub.add_parser("gate", help="Time-domain gate → gated frequency-domain MDIF.")
    _add_common_args(p_gate)
    p_gate.add_argument("--taper", type=float, default=0.1, metavar="NS",
                        help="Raised-cosine taper on each gate edge in ns (default: 0.1).")

    grp = p_gate.add_mutually_exclusive_group(required=True)
    grp.add_argument("--start-stop", nargs=2, type=float, metavar=("T_START", "T_STOP"),
                     help="Gate start and stop in nanoseconds.")
    grp.add_argument("--center-span", nargs=2, type=float, metavar=("CENTER", "SPAN"),
                     help="Gate centre and full span in nanoseconds (scikit-rf style).")

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
            run_tdr(
                args.input, args.output,
                zpad=args.zpad, window=args.window, beta=args.beta,
                z0=args.z0, debug=args.debug,
            )
            if args.debug:
                print(f"  Debug: {args.output.stem}_step.mdif, {args.output.stem}_zc.mdif")
            print("Done.")

        elif args.command == "gate":
            if args.start_stop:
                t_start_s = args.start_stop[0] * 1e-9
                t_stop_s  = args.start_stop[1] * 1e-9
                label = f"{args.start_stop[0]} ns … {args.start_stop[1]} ns"
            else:
                c, sp = args.center_span
                t_start_s = (c - sp / 2.0) * 1e-9
                t_stop_s  = (c + sp / 2.0) * 1e-9
                label = f"center={c} ns, span={sp} ns"

            print(f"Gating: {args.input.name} → {args.output.name}  [{label}]")
            run_gate(
                args.input, args.output,
                t_start=t_start_s, t_stop=t_stop_s,
                taper=args.taper * 1e-9,
                zpad=args.zpad, window=args.window, beta=args.beta,
                debug=args.debug,
            )
            if args.debug:
                stem = args.output.stem
                print(f"  Debug: {stem}_pregated_impulse.mdif, {stem}_gated_impulse.mdif")
            print("Done.")

    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
