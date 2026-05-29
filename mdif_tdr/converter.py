"""MDIF TDR converter.

Computes Time-Domain Reflectometry signals from S11 frequency-domain data:
  impulse  – r(t), impulse response (reflection coefficient units)
  step     – R(t) = cumsum(impulse), step reflection coefficient
  Z        – impedance profile Z(t) in Ohms

Algorithm follows the spec in claude.md exactly.
Key fix vs naive complex-IFFT: uses irfft + DC extrapolation so the
one-sided spectrum is extended to DC, producing a real, causal time signal
with correct amplitude.

read_mdif returns:
  meta_arr    : np.ndarray(object) — each element is a dict of VAR entries
  data_blocks : list[dict]         — each dict maps column name → np.ndarray
  Relevant column names used here: 'freq', 's11_db', 's11_deg'
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from utils.mdif import read_mdif, write_mdif

_HEADER_TOKENS = [
    "%time_ns(real)",
    "gam_impulse(real)",
    "gam_step(real)",
    "impedance(real)",
]


# ── core math ─────────────────────────────────────────────────────────────────

def s11_db_deg_to_complex(s11_db: np.ndarray, s11_deg: np.ndarray) -> np.ndarray:
    """Convert dB + degrees to linear complex."""
    mag = 10.0 ** (s11_db / 20.0)
    return mag * np.exp(1j * np.radians(s11_deg))


def compute_tdr(
    freqs: np.ndarray,
    s11_db: np.ndarray,
    s11_deg: np.ndarray,
    *,
    z0: float = 50.0,
    beta: float = 6.0,
    npad: int = 20,
    vf: float = 1.0,
) -> Dict:
    """
    Compute TDR from S11 frequency-domain data.

    Returns dict with keys:
        t_ns     : time array in nanoseconds
        impulse  : impulse response r(t)  [reflection coefficient units]
        step     : step reflection coeff R(t) = cumsum(impulse)
        Z        : impedance profile Z(t) in Ohms
        dist_mm  : one-way physical distance in mm
        dt       : time step in seconds
        z0       : reference impedance used
    """
    N  = len(freqs)
    df = (freqs[-1] - freqs[0]) / (N - 1)

    # Uniform spacing check
    dfs = np.diff(freqs)
    cv  = np.std(dfs) / np.mean(dfs)
    if cv >= 1e-3:
        raise ValueError(
            f"Frequency points are not uniformly spaced "
            f"(CV={cv:.2e}, min step={dfs.min():.3g} Hz, max step={dfs.max():.3g} Hz). "
            f"Interpolate to a uniform grid first."
        )

    s11 = s11_db_deg_to_complex(s11_db, s11_deg)

    # Step 1: Kaiser window
    #   Tapers band edges → suppresses Gibbs ringing in time domain.
    #   beta=6  → ~-44 dB sidelobes (default)
    #   beta=13 → ~-70 dB sidelobes (less time resolution)
    w     = np.kaiser(N, beta)
    s11_w = s11 * w

    # Step 2: DC extrapolation
    #   irfft expects a one-sided spectrum starting at f=0.
    #   Fill the gap [0, f_min) with Re{S11(f_min)} — a passive network's
    #   DC reflection coefficient is real, so this is the best estimate
    #   without extra low-frequency data.
    f_min   = freqs[0]
    n_dc    = max(1, int(round(f_min / df)))
    dc_val  = float(np.real(s11_w[0]))
    s11_ext = np.concatenate([np.full(n_dc, dc_val), s11_w])

    # Step 3: Zero-pad
    #   Increases time-domain sample count (interpolation in time).
    #   Does NOT improve spatial resolution — that is fixed by bandwidth.
    M     = len(s11_ext)
    N_pad = M * npad
    S_pad = np.zeros(N_pad, dtype=complex)
    S_pad[:M] = s11_ext

    # Step 4: Real IFFT (one-sided → real time signal)
    #   irfft(X of length N_pad) → 2*(N_pad-1) real samples
    #   dt = 1 / (2 * (N_pad - 1) * df)
    impulse = np.fft.irfft(S_pad)
    n_t     = len(impulse)
    dt      = 1.0 / (2.0 * (N_pad - 1) * df)
    t       = np.arange(n_t) * dt

    # Step 5: Step reflection coefficient
    #   R(t) = ∫ r(τ) dτ — irfft normalisation makes cumsum give correct Γ
    #   without an extra dt factor.
    step = np.cumsum(impulse)

    # Step 6: Impedance profile
    #   Z(t) = Z0 * (1 + R(t)) / (1 - R(t))
    denom = np.where(np.abs(1.0 - step) < 1e-9, 1e-9, 1.0 - step)
    Z     = z0 * (1.0 + step) / denom

    # Step 7: Physical distance (one-way: round-trip time / 2)
    vp      = vf * 2.998e8
    dist_mm = t * vp / 2.0 * 1000.0

    return {
        "t_ns"   : t * 1e9,
        "impulse": impulse,
        "step"   : step,
        "Z"      : Z,
        "dist_mm": dist_mm,
        "dt"     : dt,
        "z0"     : z0,
    }


def resolution_summary(
    freqs: np.ndarray,
    vf: float = 1.0,
) -> Dict:
    """Return spatial resolution and max unambiguous range."""
    N      = len(freqs)
    df     = (freqs[-1] - freqs[0]) / (N - 1)
    BW     = freqs[-1] - freqs[0]
    vp     = vf * 2.998e8
    return {
        "BW_GHz"   : BW / 1e9,
        "df_MHz"   : df / 1e6,
        "N"        : N,
        "f_min_GHz": freqs[0]  / 1e9,
        "f_max_GHz": freqs[-1] / 1e9,
        "res_mm"   : vp / (2.0 * BW) * 1000.0,
        "range_m"  : vp / (2.0 * df),
    }


# ── block helpers ─────────────────────────────────────────────────────────────

def _validate_block(block: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (freq, s11_db, s11_deg) from a data block, or raise with a clear message."""
    missing = [c for c in ("freq", "s11_db", "s11_deg") if c not in block]
    if missing:
        available = sorted(block.keys())
        raise ValueError(
            f"Block is missing required columns: {missing}. "
            f"Available columns: {available}"
        )
    return block["freq"], block["s11_db"], block["s11_deg"]


# ── public API ────────────────────────────────────────────────────────────────

def run(
    input_path: Path,
    output_path: Path,
    *,
    param: Optional[str] = None,
    vf: float = 1.0,
    beta: float = 6.0,
    npad: int = 20,
    z0: float = 50.0,
    t_max_ns: Optional[float] = None,
) -> Dict:
    """
    Full pipeline: read MDIF → compute TDR for every block → write MDIF.

    Returns a summary dict (printed by the CLI).
    """
    meta_arr, data_blocks = read_mdif(input_path)

    if not data_blocks:
        raise ValueError(f"No data blocks found in {input_path}")

    # Param selection is handled by the CLI; here we just validate all blocks
    # have the required S11 columns.  (param arg reserved for future per-param
    # selection when the MDIF contains multiple S-parameters beyond S11.)
    out_blocks = []
    summary_tdr = None   # keep the first block's result for the printed summary

    for i, block in enumerate(data_blocks):
        try:
            freq, s11_db, s11_deg = _validate_block(block)
        except ValueError as exc:
            raise ValueError(f"Block {i}: {exc}") from exc

        tdr = compute_tdr(freq, s11_db, s11_deg, z0=z0, beta=beta, npad=npad, vf=vf)
        if summary_tdr is None:
            summary_tdr = tdr
            summary_freq = freq

        t_ns    = tdr["t_ns"]
        impulse = tdr["impulse"]
        step    = tdr["step"]
        Z       = tdr["Z"]

        mask = (t_ns <= t_max_ns) if t_max_ns is not None else np.ones(len(t_ns), dtype=bool)

        row_meta = dict(meta_arr[i]) if i < len(meta_arr) else {}
        rows = [
            {
                "time_ns"     : float(t_ns[k]),
                "gam_impulse" : float(impulse[k]),
                "gam_step"    : float(step[k]),
                "impedance"   : float(Z[k]),
            }
            for k in range(len(t_ns)) if mask[k]
        ]
        out_blocks.append((row_meta, rows))

    if output_path.exists():
        print(f"[WARNING] Output file already exists and will be overwritten: {output_path}")

    write_mdif(output_path, out_blocks, header_tokens=_HEADER_TOKENS)

    # Build summary from first block
    res   = resolution_summary(summary_freq, vf=vf)
    t_ns  = summary_tdr["t_ns"]
    imp   = summary_tdr["impulse"]
    step  = summary_tdr["step"]
    peak_idx = int(np.argmax(np.abs(imp)))

    return {
        "input_path"   : input_path,
        "output_path"  : output_path,
        "n_blocks"     : len(out_blocks),
        "f_min_GHz"    : res["f_min_GHz"],
        "f_max_GHz"    : res["f_max_GHz"],
        "N"            : res["N"],
        "df_MHz"       : res["df_MHz"],
        "res_mm"       : res["res_mm"],
        "range_m"      : res["range_m"],
        "peak_t_ns"    : float(t_ns[peak_idx]),
        "peak_impulse" : float(imp[peak_idx]),
        "peak_step"    : float(step[peak_idx]),
        "vf"           : vf,
    }
