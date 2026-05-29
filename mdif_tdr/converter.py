"""MDIF time-domain transform and gating.

TDR  – IFFT of each S-param → impulse magnitude (dB) vs time.
Gate – IFFT → time-gate → FFT back → frequency-domain MDIF.

Debug mode (debug=True) writes three extra files alongside the main output:
  *_impulse.mdif  – impulse response magnitude in dB vs time  (same as TDR output)
  *_step.mdif     – step response (linear reflection coefficient ρ) vs time
  *_zc.mdif       – characteristic impedance (Ohms) vs time derived from ρ
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.fft import fft, ifft

from utils.mdif import read_mdif, write_mdif


# ── small helpers ─────────────────────────────────────────────────────────────

def _db_deg_to_complex(db: np.ndarray, deg: np.ndarray) -> np.ndarray:
    return 10.0 ** (db / 20.0) * np.exp(1j * np.radians(deg))


def _complex_to_db(c: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.abs(c) + 1e-30)


def _complex_to_db_deg(c: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    return _complex_to_db(c), np.degrees(np.angle(c))


def _detect_sparam_pairs(block: Dict[str, np.ndarray]) -> List[str]:
    bases = set()
    for col in block:
        m = re.match(r"(s\d+)_db$", col, re.IGNORECASE)
        if m and f"{m.group(1)}_deg" in block:
            bases.add(m.group(1).lower())
    return sorted(bases)


def _all_sparams(blocks: List[Dict[str, np.ndarray]]) -> List[str]:
    seen: set = set()
    for b in blocks:
        seen.update(_detect_sparam_pairs(b))
    return sorted(seen)


def _make_window(n: int, win: str, beta: float) -> np.ndarray:
    if win == "kaiser":
        return np.kaiser(n, beta)
    if win == "hann":
        return np.hanning(n)
    return np.ones(n)


def _make_gate(t: np.ndarray, t0: float, t1: float, tap: float) -> np.ndarray:
    """Raised-cosine tapered gate from t0 to t1."""
    g = np.zeros_like(t)
    if tap > 0:
        r = (t >= t0) & (t < t0 + tap)
        g[r] = 0.5 * (1.0 - np.cos(np.pi * (t[r] - t0) / tap))
        f = (t > t1 - tap) & (t <= t1)
        g[f] = 0.5 * (1.0 - np.cos(np.pi * (t1 - t[f]) / tap))
    g[(t >= t0 + tap) & (t <= t1 - tap)] = 1.0
    if tap == 0.0:
        g[(t >= t0) & (t <= t1)] = 1.0
    return g


# ── core transforms ───────────────────────────────────────────────────────────

def _impulse_response(
    freq: np.ndarray,
    s_complex: np.ndarray,
    win_name: str,
    beta: float,
    zpad: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    IFFT of windowed, zero-padded S-parameter data.

    Returns
    -------
    time      : 1-D array, seconds (first half only — causal response)
    impulse   : complex 1-D array, normalised so |peak| = 1 for perfect reflector
    win       : window array (length = len(freq)), exposed for reuse in gating
    df        : mean frequency step in Hz
    """
    order = np.argsort(freq)
    f = freq[order]
    s = s_complex[order]

    n0 = len(f)
    n  = n0 * zpad
    win = _make_window(n0, win_name, beta)

    padded = np.zeros(n, dtype=complex)
    padded[:n0] = s * win

    # Normalise by window coherent gain so |peak| = 1.0 for |S| = 1 everywhere
    impulse_full = ifft(padded) * n / np.sum(win)

    df  = float(np.mean(np.diff(f)))
    dt  = 1.0 / (n * df)
    half = n // 2
    time = np.arange(half) * dt

    return time, impulse_full[:half], win, df


def _step_response(impulse: np.ndarray, dt: float) -> np.ndarray:
    """
    Integrate the real part of the impulse response → reflection coefficient ρ(t).

    For a step-like mismatch the result rises to ρ = (Zc-Z0)/(Zc+Z0).
    The imaginary part is discarded; it carries only the Hilbert envelope of
    the bandpass carrier and has no physical meaning in ρ space.
    """
    return np.cumsum(np.real(impulse)) * dt


def _char_impedance(step: np.ndarray, z0: float = 50.0) -> np.ndarray:
    """Convert reflection coefficient ρ(t) → characteristic impedance Zc (Ohms)."""
    rho = np.clip(step, -0.9999, 0.9999)   # avoid divide-by-zero at open/short
    return z0 * (1.0 + rho) / (1.0 - rho)


# ── debug writer ──────────────────────────────────────────────────────────────

def _write_debug_mdif(
    path: Path,
    meta_list,
    time_per_block: List[np.ndarray],
    data_per_block: List[Dict[str, np.ndarray]],
    sparams: List[str],
    col_suffix: str,
    col_label: str,
) -> None:
    """Write a single-column-per-sparam debug MDIF (time as independent variable)."""
    header = ["%time(real)"] + [f"{sp}_{col_suffix}(real)" for sp in sparams]
    out_blocks = []
    for idx, (time, data) in enumerate(zip(time_per_block, data_per_block)):
        row_meta = dict(meta_list[idx]) if idx < len(meta_list) else {}
        rows = [
            {"time": float(time[n]), **{f"{sp}_{col_suffix}": float(data[sp][n]) for sp in sparams}}
            for n in range(len(time))
        ]
        out_blocks.append((row_meta, rows))
    write_mdif(path, out_blocks, header_tokens=header)


# ── public API ────────────────────────────────────────────────────────────────

def run_tdr(
    inp: Path,
    out: Path,
    *,
    zpad: int = 8,
    window: str = "kaiser",
    beta: float = 6.0,
    z0: float = 50.0,
    debug: bool = False,
) -> None:
    """
    Compute TDR for every block in an MDIF file.

    Main output: impulse response magnitude (dB) vs time.

    With debug=True, three extra files are written alongside `out`:
      *_impulse.mdif  – same impulse magnitude as main output
      *_step.mdif     – step response (linear ρ, dimensionless)
      *_zc.mdif       – characteristic impedance in Ohms
    """
    meta, blocks = read_mdif(inp)
    sparams = _all_sparams(blocks)
    if not sparams:
        raise ValueError("No S-parameter column pairs (sXX_db / sXX_deg) found.")

    hdr = ["%time(real)"] + [f"{sp}_db(real)" for sp in sparams]

    # Accumulators for all blocks (needed to write debug files in one pass)
    out_blocks   = []
    dbg_time     = []
    dbg_impulse  = {}   # sp → list of arrays across blocks
    dbg_step     = {}
    dbg_zc       = {}
    for sp in sparams:
        dbg_impulse[sp] = []
        dbg_step[sp]    = []
        dbg_zc[sp]      = []

    for i, blk in enumerate(blocks):
        freq = blk.get("freq")
        if freq is None or len(freq) < 2:
            continue

        blk_sp = _detect_sparam_pairs(blk)
        row_meta = dict(meta[i]) if i < len(meta) else {}

        td_db    = {}
        time_ref = None   # all sparams share the same time axis per block

        for sp in sparams:
            if sp in blk_sp:
                s_cplx = _db_deg_to_complex(blk[f"{sp}_db"], blk[f"{sp}_deg"])
                time, impulse, win, df = _impulse_response(
                    freq, s_cplx, window, beta, zpad
                )
                dt   = time[1] - time[0] if len(time) > 1 else 1.0
                step = _step_response(impulse, dt)
                zc   = _char_impedance(step, z0)

                td_db[sp] = _complex_to_db(impulse)
                if debug:
                    dbg_impulse[sp].append(_complex_to_db(impulse))
                    dbg_step[sp].append(step)
                    dbg_zc[sp].append(zc)
            else:
                half = len(freq) * zpad // 2
                nan  = np.full(half, np.nan)
                td_db[sp] = nan
                if debug:
                    dbg_impulse[sp].append(nan)
                    dbg_step[sp].append(nan)
                    dbg_zc[sp].append(nan)
                time = np.arange(half) / (len(freq) * zpad * float(np.mean(np.diff(freq))))

            if time_ref is None:
                time_ref = time

        if debug:
            dbg_time.append(time_ref)

        n = len(time_ref)
        rows = [
            {"time": float(time_ref[k]),
             **{f"{sp}_db": float(td_db[sp][k]) for sp in sparams}}
            for k in range(n)
        ]
        out_blocks.append((row_meta, rows))

    write_mdif(out, out_blocks, header_tokens=hdr)

    if debug:
        stem = out.stem
        parent = out.parent

        # impulse (dB)
        _write_debug_mdif(
            parent / f"{stem}_impulse.mdif",
            meta, dbg_time,
            [{sp: dbg_impulse[sp][i] for sp in sparams} for i in range(len(dbg_time))],
            sparams, col_suffix="db", col_label="Impulse response (dB)",
        )
        # step response (linear ρ)
        _write_debug_mdif(
            parent / f"{stem}_step.mdif",
            meta, dbg_time,
            [{sp: dbg_step[sp][i] for sp in sparams} for i in range(len(dbg_time))],
            sparams, col_suffix="rho", col_label="Step response (ρ)",
        )
        # characteristic impedance (Ohms)
        _write_debug_mdif(
            parent / f"{stem}_zc.mdif",
            meta, dbg_time,
            [{sp: dbg_zc[sp][i] for sp in sparams} for i in range(len(dbg_time))],
            sparams, col_suffix="zc", col_label="Characteristic impedance (Ω)",
        )


def run_gate(
    inp: Path,
    out: Path,
    *,
    t_start: Optional[float] = None,
    t_stop: Optional[float] = None,
    center: Optional[float] = None,
    span: Optional[float] = None,
    taper: float = 0.1e-9,
    zpad: int = 8,
    window: str = "kaiser",
    beta: float = 6.0,
    debug: bool = False,
) -> None:
    """
    Time-domain gate each S-parameter and write a gated frequency-domain MDIF.

    Gate can be specified two ways (matching scikit-rf's time_gate API):
      start/stop  – explicit gate edges in seconds
      center/span – centre time and full width in seconds (converted to start/stop)

    With debug=True writes *_pregated_impulse.mdif and *_gated_impulse.mdif
    so you can visually confirm the gate is positioned correctly.
    """
    # Resolve gate edges
    if center is not None and span is not None:
        t_start = center - span / 2.0
        t_stop  = center + span / 2.0
    if t_start is None or t_stop is None:
        raise ValueError("Specify either (t_start, t_stop) or (center, span).")
    if t_start >= t_stop:
        raise ValueError(f"t_start ({t_start*1e9:.3f} ns) must be < t_stop ({t_stop*1e9:.3f} ns).")

    meta, blocks = read_mdif(inp)
    sparams = _all_sparams(blocks)
    if not sparams:
        raise ValueError("No S-parameter column pairs (sXX_db / sXX_deg) found.")

    hdr = ["%freq(real)"] + [
        tok for sp in sparams for tok in (f"{sp}_db(real)", f"{sp}_deg(real)")
    ]
    out_blocks = []

    dbg_time        = []
    dbg_pre_impulse  = {sp: [] for sp in sparams}
    dbg_post_impulse = {sp: [] for sp in sparams}

    for i, blk in enumerate(blocks):
        freq = blk.get("freq")
        if freq is None or len(freq) < 2:
            continue

        blk_sp = _detect_sparam_pairs(blk)
        df  = float(np.mean(np.diff(freq)))
        n0  = len(freq)
        n   = n0 * zpad
        win = _make_window(n0, window, beta)
        dt  = 1.0 / (n * df)
        t   = np.arange(n) * dt
        gate = _make_gate(t, t_start, t_stop, taper)

        # Index into zero-padded array where the original sweep begins
        f0  = float(freq[0])
        k0  = int(round(f0 / df))
        k1  = k0 + n0
        if k1 > n:
            raise ValueError(
                f"zpad={zpad} too small: f_start/df + N = {k1} > N*zpad = {n}. "
                f"Increase zpad."
            )

        row_meta = dict(meta[i]) if i < len(meta) else {}
        gated = {}

        for sp in sparams:
            if sp in blk_sp:
                s_cplx = _db_deg_to_complex(blk[f"{sp}_db"], blk[f"{sp}_deg"])
                padded = np.zeros(n, dtype=complex)
                padded[:n0] = s_cplx * win

                # To time domain (normalised)
                td = ifft(padded) * n / np.sum(win)
                # Gate
                td_gated = td * gate
                # Back to frequency domain (invert normalisation)
                s_back = fft(td_gated) * np.sum(win) / n

                gated[sp] = _complex_to_db_deg(s_back[k0:k1])

                if debug:
                    half = n // 2
                    dbg_pre_impulse[sp].append(_complex_to_db(td[:half]))
                    dbg_post_impulse[sp].append(_complex_to_db(td_gated[:half]))
            else:
                nan = np.full(n0, np.nan)
                gated[sp] = (nan, nan)
                if debug:
                    half = n // 2
                    dbg_pre_impulse[sp].append(np.full(half, np.nan))
                    dbg_post_impulse[sp].append(np.full(half, np.nan))

        if debug:
            dbg_time.append(np.arange(n // 2) * dt)

        rows = [
            {"freq": float(freq[k]),
             **{f"{sp}_db":  float(gated[sp][0][k]) for sp in sparams},
             **{f"{sp}_deg": float(gated[sp][1][k]) for sp in sparams}}
            for k in range(n0)
        ]
        out_blocks.append((row_meta, rows))

    write_mdif(out, out_blocks, header_tokens=hdr)

    if debug:
        stem   = out.stem
        parent = out.parent
        _write_debug_mdif(
            parent / f"{stem}_pregated_impulse.mdif",
            meta, dbg_time,
            [{sp: dbg_pre_impulse[sp][i] for sp in sparams} for i in range(len(dbg_time))],
            sparams, col_suffix="db", col_label="Pre-gate impulse (dB)",
        )
        _write_debug_mdif(
            parent / f"{stem}_gated_impulse.mdif",
            meta, dbg_time,
            [{sp: dbg_post_impulse[sp][i] for sp in sparams} for i in range(len(dbg_time))],
            sparams, col_suffix="db", col_label="Post-gate impulse (dB)",
        )
