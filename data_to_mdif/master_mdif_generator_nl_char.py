#!/usr/bin/env python3
"""
master_mdif.py

* Accept a base‑path (the folder that contains the net sub‑folders E1, E2, …)
* temperature argument passed by user
* Run the IMD‑sweep converter, then the gain‑compression converter.
* Propagate any error from the children and give a concise summary.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# -------------------------------------------------------------------------
# Helper: invoke a sub‑script and forward its exit‑code
# -------------------------------------------------------------------------
def _run_script(script: Path, base_path: Path, temperature: float) -> None:
    """Run *script* with the same CLI that the script itself expects."""
    cmd = [
        sys.executable,               # the same Python interpreter
        str(script),
        "--base-path", str(base_path),
        "--temperature", str(temperature),
    ]

    # If you want the child scripts to be noisy, add "--verbose" for the IMD one
    if script.name.startswith("imd"):
        cmd.append("--verbose")

    print(f"\n=== Running {script.name} ===")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Echo the child’s stdout / stderr so the user can see the same logs
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"{script.name} failed with exit code {result.returncode}"
        )

# fall-back to user input values in case CLI arguments missing
def _prompt_missing(prompt: str, cast_type):
    """Ask the user for a value when the CLI argument was omitted."""
    while True:
        raw = input(f"{prompt}: ").strip()

        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1].strip()

        if cast_type is float:
            try:
                int_val = int(raw)
                return float(int_val)
            except ValueError:
                try:
                    return float(raw)
                except ValueError as exc:
                    print(f"Invalid number – {exc}")
                    continue
        try:
            return cast_type(raw)
        except ValueError as exc:
            print(f"Invalid input – {exc}")

# -------------------------------------------------------------------------
# CLI of the master script
# -------------------------------------------------------------------------
def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate both IMD‑sweep and gain‑compression MDIF files "
            "from a common base‑path containing net folders."
        )
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        help="Root directory that already contains the net sub‑folders (E1, E2, …).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Test temperature in °C (must be inside the allowed range).",
    )
    parser.add_argument(
        "--imd-script",
        type=Path,
        default=Path(__file__).parent / "scripts" / "imd_sweep_to_mdif.py",
        help="Path to the IMD‑sweep converter script.",
    )
    parser.add_argument(
        "--gain-script",
        type=Path,
        default=Path(__file__).parent / "scripts" / "gain_compression_to_mdif.py",
        help="Path to the gain‑compression converter script.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_cli()

    base_path: Path = args.base_path
    if base_path is None:
        base_path = _prompt_missing("Base directory containing net folders (E1, E2, …)", Path)

    if not base_path.is_dir():
        raise NotADirectoryError(f"The supplied base_path does not exist: {base_path}")
    
    temperature: float = args.temperature
    if temperature is None:
        temperature = _prompt_missing("Temperature that measuremetns were taken at (°C)", float)

    try:
        _run_script(args.imd_script, base_path, temperature)
        _run_script(args.gain_script, base_path, temperature)
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== All MDIF files have been generated successfully ===")


if __name__ == "__main__":
    main()