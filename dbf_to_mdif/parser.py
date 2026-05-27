"""Parse VNA measurement data from MATLAB .mat files."""

from pathlib import Path
from typing import Dict, List

import numpy as np
import scipy.io


def _real_imag_to_db_deg(real: np.ndarray, imag: np.ndarray):
    s11_complex = real + 1j * imag
    return (
        20.0 * np.log10(np.abs(s11_complex) + 1e-30),
        np.degrees(np.angle(s11_complex)),
    )


# ── public API ────────────────────────────────────────────────────────────────

def parse_mat_file(path: Path) -> List[Dict[str, float]]:
    """
    Read S11 data from a .mat file (legacy or v7.3 HDF5).

    Returns a list of row dicts with keys: freq_ghz, s11_db, s11_deg.
    Columns are assumed to be Re/Im; converted to dB and degrees.
    """
    mat = scipy.io.loadmat(path, squeeze_me=True)
    data = mat['vna_data']['s11'].item()
    freq_ghz, real, imag = data.T
    s11_db, s11_deg = _real_imag_to_db_deg(real, imag)
    return [
        {"freq": float(f*1000000000), "s11_db": float(d), "s11_deg": float(p)}
        for f, d, p in zip(freq_ghz, s11_db, s11_deg)
    ]
