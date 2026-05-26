"""Parse VNA measurement data from MATLAB .mat files."""

from pathlib import Path
from typing import Dict, List

import numpy as np
import scipy.io


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
    mat = scipy.io.loadmat(path, squeeze_me=True)
    data = mat['vna_data']['s11'].item()
    freq_ghz, real, imag = data.T
    s11_db, s11_deg = _detect_and_convert(real, imag)
    return [
        {"freq": float(f*1000000000), "s11_db": float(d), "s11_deg": float(p)}
        for f, d, p in zip(freq_ghz, s11_db, s11_deg)
    ]
