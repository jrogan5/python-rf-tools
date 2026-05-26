"""Parse VNA measurement data from MATLAB .mat files."""

from pathlib import Path
from typing import Dict, List

import numpy as np


# ── mat-file loading (handles both legacy and v7.3 / HDF5 formats) ────────────

def _load_mat_scipy(path: Path) -> dict:
    import scipy.io
    return scipy.io.loadmat(str(path))


def _load_mat_h5py(path: Path) -> dict:
    """Read a MATLAB v7.3 (HDF5) .mat file via h5py."""
    try:
        import h5py
    except ImportError:
        raise ImportError(
            "This .mat file is MATLAB v7.3 (HDF5) format and requires h5py.\n"
            "Install it with:  pip install h5py"
        )

    result = {}
    with h5py.File(str(path), "r") as f:
        for key in f.keys():
            try:
                arr = np.array(f[key])
                if arr.dtype.kind in ("f", "i", "u", "c"):
                    # h5py reads MATLAB arrays transposed (col-major → row-major)
                    result[key] = arr.T if arr.ndim > 1 else arr
            except Exception:
                pass
    return result


def _load_mat(path: Path) -> dict:
    """Load a .mat file regardless of MATLAB version."""
    import scipy.io
    try:
        return _load_mat_scipy(path)
    except NotImplementedError:
        # scipy raises NotImplementedError for v7.3 HDF5 files
        return _load_mat_h5py(path)
    except Exception as exc:
        # If scipy fails for any other reason also try h5py
        try:
            return _load_mat_h5py(path)
        except Exception:
            raise exc  # re-raise original error if h5py also fails


# ── array extraction ──────────────────────────────────────────────────────────

def _extract_array(mat: dict) -> np.ndarray:
    """
    Return the first usable (N, >=3) float array from a loadmat dict.

    Search order:
      1. Preferred names: vna_data, data, vna, meas
      2. Any remaining non-private key

    Structured arrays (dtype.names) are column-stacked into a plain 2-D array.
    Raises ValueError if nothing suitable is found.
    """
    PREFERRED = ["vna_data", "data", "vna", "meas"]
    private = {"__header__", "__version__", "__globals__"}
    candidate_keys = PREFERRED + [k for k in mat if k not in PREFERRED and k not in private]

    for key in candidate_keys:
        raw = mat.get(key)
        if raw is None:
            continue

        if hasattr(raw, "dtype") and raw.dtype.names:
            try:
                a = np.column_stack(
                    [raw[n].flatten() for n in raw.dtype.names]
                ).astype(float)
            except Exception:
                continue
        else:
            try:
                a = np.atleast_2d(np.asarray(raw, dtype=float))
            except (ValueError, TypeError):
                continue
            if a.ndim != 2:
                continue
            if a.shape[0] < a.shape[1]:
                a = a.T

        if a.shape[1] >= 3 and np.isfinite(a).any():
            return a

    available = [k for k in mat if k not in private]
    raise ValueError(
        f"No suitable numerical matrix (>=3 columns) found in {path.name}. "
        f"Available keys: {available}"
    )


# ── column format detection ───────────────────────────────────────────────────

def _detect_and_convert(col2: np.ndarray, col3: np.ndarray):
    """
    Determine the format of columns 2 and 3 and return (s11_db, s11_deg).

    Re/Im   – both |col| ≤ 2 and col2 contains negative values.
              Computes 20*log10(|Re+jIm|) and atan2(Im, Re) in degrees.
    Linear  – col2 non-negative and ≤ 2.
              Computes 20*log10(col2) and converts col3 radians → degrees.
    dB/rad  – col2 non-positive (already in dB), col3 in radians.
              Keeps col2, converts col3 → degrees.
    """
    max_abs = max(np.nanmax(np.abs(col2)), np.nanmax(np.abs(col3)))

    if max_abs <= 2.0 and np.any(col2 < 0):
        s11_complex = col2 + 1j * col3
        return (
            20.0 * np.log10(np.abs(s11_complex) + 1e-30),
            np.degrees(np.angle(s11_complex)),
        )
    elif np.all(col2 >= 0) and max_abs <= 2.0:
        return (
            20.0 * np.log10(np.abs(col2) + 1e-30),
            np.degrees(col3),
        )
    else:
        return col2, np.degrees(col3)


# ── public API ────────────────────────────────────────────────────────────────

def parse_mat_file(path: Path) -> List[Dict[str, float]]:
    """
    Read S11 data from a .mat file (legacy or v7.3 HDF5).

    Returns a list of row dicts with keys: freq_ghz, s11_db, s11_deg.
    Column format is auto-detected (Re/Im, linear magnitude, or dB/radians).
    """
    mat = _load_mat(path)
    arr = _extract_array(mat)

    freq_ghz = arr[:, 0].astype(float)
    col2     = arr[:, 1].astype(float)
    col3     = arr[:, 2].astype(float)

    s11_db, s11_deg = _detect_and_convert(col2, col3)

    return [
        {"freq_ghz": float(f), "s11_db": float(d), "s11_deg": float(p)}
        for f, d, p in zip(freq_ghz, s11_db, s11_deg)
    ]
