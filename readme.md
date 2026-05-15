# RF MDIF Tools

A set of Python tools for processing RF measurement data and generating MDIF files
for use with ADS and similar EDA tools.

Each tool collects per-net measurement files from a folder structure, parses
and validates them, and writes a single combined MDIF file with one block per net.
Nets with missing or malformed files are skipped and listed in a separate report.

---

## Repository structure

```
python-rf-tools/
|
|-- _version.py              # single source of truth for the version number
|-- build.ps1                # incremental release builder (PowerShell)
|-- pyproject.toml
|
|-- specs/                   # one PyInstaller spec file per executable
|   |-- rf_mdif.spec
|   |-- rf_sort_rdi.spec
|   `-- rf_sort_4pack.spec
|
|-- data_to_mdif/
|   |-- cli.py               # unified interactive CLI (main entry point)
|   |
|   |-- gain/                # gain-compression converter
|   |   |-- parser.py        # CSV parsing (handles DB/DEG, Log-Mag, REAL/IMAG)
|   |   |-- converter.py     # orchestration: discover nets -> parse -> write MDIF
|   |   `-- cli.py           # standalone CLI for gain only
|   |
|   |-- imd/                 # IMD-sweep converter
|   |   |-- parser.py
|   |   |-- converter.py
|   |   `-- cli.py
|   |
|   |-- nf/                  # noise-figure sweep converter
|   |   |-- parser.py
|   |   |-- converter.py
|   |   `-- cli.py
|   |
|   `-- s2p/                 # S-parameter converter
|       |-- parser.py        # Touchstone .s2p parser
|       |-- converter.py
|       |-- cli.py
|       `-- sparam_nf_to_mdif.py  # combined S-param + NF for RXEM/4-pack folders
|
|-- sorting/
|   |-- rdi/
|   |   `-- sorting.py       # group RDI nets by 4, average s21_db, sort by gain
|   `-- 4pack/
|       `-- sorting.py       # average s21_db across 4 paths per SN, sort by gain
|
|-- utils/
|   |-- cli.py               # prompt_missing, validate_temperature, prompt_validated
|   |-- freq.py              # extract_frequency (reads CW freq from CSV header)
|   |-- io.py                # write_bad_report, ensure_plots_dir
|   |-- mdif.py              # read_mdif, write_mdif
|   `-- net.py               # discover_nets, NetFolder dataclass
|
`-- templates/
    |-- mdif_examples/       # example MDIF files
    `-- measurement_data/    # example input files (one net, each measurement type)
```

---

## Expected input folder layout

All MDIF-generator tools expect the measurement data to be organised under a
**base directory** containing one sub-folder per net named `E<number>`:

```
<base_path>/
    E1/
        E1_Gain_Comp_27.5.csv
        E1_NB.s2p
        E1_WB.s2p
        E1_NF.csv
        E1_SWP_IMD.csv
    E2/
        ...
```

Outputs are written to `<base_path>/plots/`.

---

## Tools

### 1. rf-mdif -- Unified MDIF generator

The main tool. Presents an interactive menu and runs the appropriate converter(s).

**Menu options:**

| # | What it runs |
|---|---|
| 1 | Gain compression |
| 2 | IMD sweep |
| 3 | S-parameters (single key, e.g. NB or WB) |
| 4 | Noise figure |
| 5 | Linear characterisation -- S-params NB + S-params WB + NF |
| 6 | Nonlinear characterisation -- Gain compression + IMD sweep |
| 7 | Full characterisation -- all of the above |

**Outputs (written to `<base_path>/plots/`):**

| File | Contents |
|---|---|
| `RDI_gain_compression.mdif` | Gain vs Pin sweep, one block per net |
| `RDI_IMD_sweep.mdif` | IMD sweep (Pout, Pin, P3f, Gain, IMD3, OIP3, IIP3) |
| `measured_NB.mdif` | Narrowband S-parameters |
| `measured_WB.mdif` | Wideband S-parameters |
| `measured_NF.mdif` | Noise figure |
| `*_bad_measurements.txt` | Nets skipped due to missing or malformed files |

---

### 2. rf-sort-rdi -- RDI net sorter

Groups RDI nets four-by-four (by net number), averages `s21_db` within each
group, and ranks groups by their mean ambient-temperature gain (lowest first).

Input: an MDIF file from the gain-compression converter.
Output: a new MDIF with columns `%freq(real)` and `s21_avg_db(real)`.

---

### 3. rf-sort-4pack -- 4-pack path sorter

Averages `s21_db` across the four paths for each (SN, Temperature) pair and
ranks serial numbers by their mean ambient-temperature gain (lowest first).

Input: an MDIF file where each block has `VAR SN`, `VAR Path`, `VAR Temperature`
(as produced by `sparam_nf_to_mdif.py`).

---

### 4. sparam_nf_to_mdif -- RXEM / 4-pack combined converter

Located at `data_to_mdif/s2p/sparam_nf_to_mdif.py`. Handles a different
folder layout used for 4-pack characterisation:

```
<base_path>/
    RXEM1-000019/
        S-Parameters_RAW_RXEM1-000019_PATH1_25.0C.csv
        S-Parameters_PROCESSED_RXEM1-000019_PATH1_25.0C.csv
        NF_RAW_RXEM1-000019_PATH1_25.0C.csv
        NF_PROCESSED_RXEM1-000019_PATH1_25.0C.csv
```

Produces four MDIF files (RAW and PROCESSED for S-params and NF) with
`VAR SN`, `VAR Path`, and `VAR Temperature` blocks.

---

## Running from source (developer)

**Requirements:** Python 3.10+, numpy

```powershell
pip install numpy

# run the unified tool
python data_to_mdif/cli.py

# run a specific converter directly
python data_to_mdif/gain/cli.py --base-path "C:\path\to\data" --temperature 23
python data_to_mdif/imd/cli.py  --base-path "C:\path\to\data" --temperature 23
python data_to_mdif/nf/cli.py   --base-path "C:\path\to\data" --temperature 23 --key NF
python data_to_mdif/s2p/cli.py  --base-path "C:\path\to\data" --temperature 23 --key NB

# run a sorting script
python sorting/rdi/sorting.py   --input path/to/gain.mdif   --output path/to/sorted.mdif
python sorting/4pack/sorting.py --input path/to/sparam.mdif --output path/to/sorted.mdif
```

All CLIs also work fully interactively -- omit arguments and answer the prompts.

---

## Building and releasing executables

### First-time setup (once per machine)

Allow PowerShell scripts to run and install PyInstaller:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install pyinstaller
```

### Build

```powershell
.\build.ps1
```

The script compares the modification time of each source directory against the
already-built versioned `.exe` in `dist\`. Only executables whose source has
changed since the last build are recompiled. To rebuild everything regardless:

```powershell
.\build.ps1 -Force
```

### Release a new version

1. Edit `_version.py`:
   ```python
   __version__ = "1.1.0"
   ```
2. Update the matching `version` field in `pyproject.toml`.
3. Run `.\build.ps1`. Because the version number changed, no matching exe
   exists yet in `dist\`, so all three are rebuilt automatically.
4. Send the three `dist\*-v1.1.0.exe` files to the recipient.

Old versioned exes accumulate in `dist\` and can be deleted manually.

---

## Developing a new tool

Every measurement converter follows the same three-file pattern inside a
sub-package of `data_to_mdif/`:

```
data_to_mdif/<name>/
    __init__.py
    parser.py      # reads one measurement file, returns structured data
    converter.py   # walks net folders, calls parser, writes MDIF
    cli.py         # argument parsing + interactive fallback
```

Here is a complete walkthrough using a hypothetical **phase-noise** measurement
type as the example.

---

### Step 1 -- Create the sub-package

```powershell
mkdir data_to_mdif\pn
"" | Out-File data_to_mdif\pn\__init__.py
```

Add a one-liner `__init__.py` that re-exports `run` so the unified CLI can
import it cleanly:

```python
# data_to_mdif/pn/__init__.py
from .converter import run
__all__ = ["run"]
```

---

### Step 2 -- Write the parser (`parser.py`)

The parser reads **one** measurement file and returns a list of row dicts.
Key names must match what you will put in the MDIF header tokens (see Step 3).

```python
# data_to_mdif/pn/parser.py
import csv
from pathlib import Path
from typing import Dict, List

def parse_pn_csv(csv_path: Path) -> List[Dict[str, float]]:
    """Return a list of dicts with keys: freq, pn_dbc_hz."""
    rows = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            try:
                rows.append({
                    "freq":      float(row["Frequency_Hz"]),
                    "pn_dbc_hz": float(row["PN_dBc_Hz"]),
                })
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Bad row {i} in {csv_path.name}: {exc}") from exc
    if not rows:
        raise ValueError(f"No data rows found in {csv_path.name}")
    return rows
```

**Rules for parser output:**
- Return a `List[Dict[str, float]]` -- one dict per row.
- Key names must derive to the column name in the MDIF header when passed
  through `re.sub(r"[^\w]", "", token).lower().replace("real", "")`.
  For example, header token `"pn_dbc_hz(real)"` derives to key `"pn_dbc_hz"`.
- Raise `ValueError` or `KeyError` with a descriptive message on bad input
  so the converter can record it in the bad-measurement report.

---

### Step 3 -- Write the converter (`converter.py`)

The converter uses the shared utilities to walk the net folders, call the
parser, assemble MDIF blocks, and write the output.

```python
# data_to_mdif/pn/converter.py
from pathlib import Path
from typing import Dict, List, Tuple

MDIF_HEADER_TOKENS = ["%freq(real)", "pn_dbc_hz(real)"]
CSV_GLOB = "*PN*.csv"


def run(base_path: Path, temperature: float, *, out_name: str = "RDI_phase_noise.mdif") -> None:
    from .parser import parse_pn_csv
    from utils.net  import discover_nets
    from utils.mdif import write_mdif
    from utils.io   import write_bad_report, ensure_plots_dir
    from utils.cli  import validate_temperature

    validate_temperature(temperature)

    nets = discover_nets(base_path)
    good_blocks: List[Tuple[int, List[Dict]]] = []
    nets_without_csv: List[str] = []
    bad_files: List[str] = []
    bad_files_by_net: Dict[str, List[Tuple[str, str]]] = {}

    for net in nets:
        csv_paths = sorted(net.path.glob(CSV_GLOB))
        if not csv_paths:
            nets_without_csv.append(net.name)
            continue

        net_number = int(net.name.lstrip("Ee"))
        csv_path = csv_paths[0]
        try:
            rows = parse_pn_csv(csv_path)
            good_blocks.append((net_number, rows))
        except Exception as exc:
            bad_files.append(str(csv_path))
            bad_files_by_net.setdefault(net.name, []).append((str(csv_path), str(exc)))

    # Parser keys already match the token derivations, so no remapping needed.
    mdif_blocks = [
        ({"Net": net_number, "Temperature": temperature}, rows)
        for net_number, rows in good_blocks
    ]

    plots_dir = ensure_plots_dir(base_path)
    write_mdif(plots_dir / out_name, mdif_blocks, header_tokens=MDIF_HEADER_TOKENS)

    write_bad_report(
        base_path,
        nets_without_csv=nets_without_csv,
        bad_files=bad_files,
        bad_files_by_net=bad_files_by_net,
        kind="phase-noise",
    )
```

**Key mapping rule:** `write_mdif` derives a dict key from each header token
using `re.sub(r"[^\w]", "", token).lower().replace("real", "")`. The row dicts
your converter passes must use those derived keys. Examples:

| Header token | Derived key |
|---|---|
| `%freq(real)` | `freq` |
| `pn_dbc_hz(real)` | `pn_dbc_hz` |
| `S21_dB(real)` | `s21_db` |
| `S21_degree(real)` | `s21_degree` |

If your parser uses different key names, remap them in the converter before
building `mdif_blocks` (see `gain/converter.py` for an example).

---

### Step 4 -- Write the CLI (`cli.py`)

```python
# data_to_mdif/pn/cli.py
#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_to_mdif.pn.converter import run
from utils.cli import prompt_missing, TEMP_MIN, TEMP_MAX


def _parse_args():
    p = argparse.ArgumentParser(description="Combine phase-noise CSVs into a single MDIF.")
    p.add_argument("--base-path", type=Path)
    p.add_argument("--temperature", type=float)
    p.add_argument("--out-name", default="RDI_phase_noise.mdif")
    return p.parse_args()


def main():
    args = _parse_args()
    base_path = args.base_path or prompt_missing(
        "Base directory containing net folders (E1, E2, ...)", Path
    )
    if not base_path.is_dir():
        sys.exit(f"[ERROR] Directory not found: {base_path}")
    temperature = (
        args.temperature if args.temperature is not None
        else prompt_missing(f"Temperature (degC, {TEMP_MIN}...{TEMP_MAX})", float)
    )
    try:
        run(base_path, temperature, out_name=args.out_name)
    except Exception as exc:
        sys.exit(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
```

---

### Step 5 -- Register in the unified CLI (`data_to_mdif/cli.py`)

Add a runner function and a menu entry.

```python
# add this runner function alongside the existing ones
def _run_pn(base_path: Path, temperature: float) -> None:
    from data_to_mdif.pn.converter import run
    print("\n  -> Running phase-noise converter ...")
    run(base_path, temperature)
    print("    Done.")
```

Then extend the menu string and the `if/elif` block:

```python
# in _MENU, add:
"  8  Phase noise\n"

# in main(), add:
elif choice == "8":
    _safe(_run_pn, base_path, temperature)
```

---

### Step 6 -- Add to the build

**Create `specs/rf_pn.spec`:**

```python
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["data_to_mdif/pn/cli.py"],
    pathex=["."],
    hiddenimports=[
        "_version",
        "utils.mdif", "utils.net", "utils.io", "utils.cli", "utils.freq",
        "data_to_mdif.pn.converter",
        "data_to_mdif.pn.parser",
    ],
    datas=[],
    binaries=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="rf-pn", console=True, upx=False)
```

**Add an entry to the `$tools` table in `build.ps1`:**

```powershell
@{
    Name    = "rf-pn"
    Spec    = "specs\rf_pn.spec"
    Sources = @("data_to_mdif\pn", "utils", "_version.py")
}
```

That is all. The next `.\build.ps1` run will detect the new exe has never been
built and compile it automatically. Subsequent runs only recompile it when
`data_to_mdif\pn\` or `utils\` changes.

Note: if the new measurement type belongs in the **unified** `rf-mdif` exe
rather than its own executable, skip the spec file and `$tools` entry and only
do Steps 1-5. The unified exe's sources already include all of `data_to_mdif\`,
so it will be rebuilt automatically when the new sub-package is added.

---

## MDIF output format

Each block in the output file follows this structure:

```
VAR Net(real) = 4
VAR Frequency(real) = 27500000000
VAR Temperature(real) = 23.0
BEGIN ACDATA
%Pin_dBm(real)  S21_dB(real)  S21_degree(real)  ...
-20             -1.6477       113.367            ...
...
END
```

VAR lines vary by measurement type:

| Tool | VAR lines |
|---|---|
| Gain compression | Net, Frequency, Temperature |
| IMD sweep | Net, Temperature |
| S-parameters | Net, Temperature |
| Noise figure | Net, Temperature |
| sparam_nf_to_mdif | SN, Path, Temperature |
| Sorting outputs | SortIndex, !Net or !SN (commented), Temperature |

A `!` prefix on a VAR name writes it as a comment (`! VAR Net(real) = ...`)
so it is visible in the file but ignored by parsers.
