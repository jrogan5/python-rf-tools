"""MDIF time-domain transform and gating.

TDR  – IFFT of each S-param → magnitude vs time, written as a new MDIF.
Gate – IFFT → time-gate → FFT back → frequency-domain MDIF (same structure as input).
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from utils.mdif import read_mdif, write_mdif


# ── helpers ───────────────────────────────────────────────────────────────────

def _db_deg_to_complex(db: np.ndarray, deg: np.ndarray) -> np.ndarray:
    return 10.0 ** (db / 20.0) * np.exp(1j * np.radians(deg))


def _complex_to_db(c: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.abs(c) + 1e-30)


def _complex_to_db_deg(c: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    return _complex_to_db(c), np.degrees(np.angle(c))


def _detect_sparam_pairs(block: Dict[str, np.ndarray]) -> List[str]:
    """Return sorted S-param base names (e.g. ['s11','s21']) that have both _db and _deg columns."""
    bases = set()
    for col in block:
        m = re.match(r"(s\d+)_db$", col, re.IGNORECASE)
        if m:
            base = m.group(1).lower()
            if f"{base}_deg" in block:
                bases.add(base)
    return sorted(bases)


def _all_sparams(data_blocks: List[Dict[str, np.ndarray]]) -> List[str]:
    seen: set = set()
    for block in data_blocks:
        seen.update(_detect_sparam_pairs(block))
    return sorted(seen)


def _make_window(n: int, window: str, beta: float) -> np.ndarray:
    if window == "kaiser":
        return np.kaiser(n, beta)
    if window == "hann":
        return np.hanning(n)
    return np.ones(n)


def _make_gate(t: np.ndarray, t_start: float, t_stop: float, taper: float) -> np.ndarray:
    gate = np.zeros(len(t))
    if taper > 0:
        mask_rise = (t >= t_start) & (t < t_start + taper)
        gate[mask_rise] = 0.5 * (1.0 - np.cos(np.pi * (t[mask_rise] - t_start) / taper))
        mask_fall = (t > t_stop - taper) & (t <= t_stop)
        gate[mask_fall] = 0.5 * (1.0 - np.cos(np.pi * (t_stop - t[mask_fall]) / taper))
    mask_flat = (t >= t_start + taper) & (t <= t_stop - taper)
    gate[mask_flat] = 1.0
    if taper == 0.0:
        gate[(t >= t_start) & (t <= t_stop)] = 1.0
    return gate


# ── public API ────────────────────────────────────────────────────────────────

def run_tdr(
    input_path: Path,
    output_path: Path,
    *,
    zpad: int = 8,
    window: str = "kaiser",
    beta: float = 6.0,
) -> None:
    """
    Compute TDR (IFFT magnitude vs time) for every block in an MDIF file.

    Output MDIF has a ``time`` column (seconds) and one ``sXX_db`` column per
    detected S-parameter.  VAR metadata is preserved unchanged.
    """
    meta, data_blocks = read_mdif(input_path)
    sparams = _all_sparams(data_blocks)
    if not sparams:
        raise ValueError("No S-parameter column pairs (sXX_db / sXX_deg) found in input MDIF.")

    header_tokens = ["%time(real)"] + [f"{sp}_db(real)" for sp in sparams]
    out_blocks = []

    for idx, block in enumerate(data_blocks):
        freq = block.get("freq")
        if freq is None or len(freq) < 2:
            continue

        block_sparams = _detect_sparam_pairs(block)
        df = float(np.mean(np.diff(freq)))
        n_orig = len(freq)
        n_pad = n_orig * zpad
        win = _make_window(n_orig, window, beta)
        dt = 1.0 / (n_pad * df)
        time = np.arange(n_pad) * dt
        half = n_pad // 2

        td_db: Dict[str, np.ndarray] = {}
        for sp in sparams:
            if sp in block_sparams:
                s_complex = _db_deg_to_complex(block[f"{sp}_db"], block[f"{sp}_deg"])
                padded = np.zeros(n_pad, dtype=complex)
                padded[:n_orig] = s_complex * win
                td = np.fft.ifft(padded) * n_pad
                td_db[sp] = _complex_to_db(td[:half])
            else:
                td_db[sp] = np.full(half, np.nan)

        row_meta = dict(meta[idx]) if idx < len(meta) else {}
        rows = [
            {"time": float(time[n]), **{f"{sp}_db": float(td_db[sp][n]) for sp in sparams}}
            for n in range(half)
        ]
        out_blocks.append((row_meta, rows))

    write_mdif(output_path, out_blocks, header_tokens=header_tokens)


def run_gate(
    input_path: Path,
    output_path: Path,
    *,
    t_start: float,
    t_stop: float,
    taper: float = 0.1e-9,
    zpad: int = 8,
    window: str = "kaiser",
    beta: float = 6.0,
) -> None:
    """
    Time-domain gate each S-parameter in an MDIF file and write a gated
    frequency-domain MDIF (same structure as input).

    Parameters
    ----------
    t_start, t_stop : float
        Gate edges in seconds.
    taper : float
        Raised-cosine taper width in seconds applied to each gate edge.
    zpad : int
        Zero-padding factor (higher → finer time-domain resolution).
    window : str
        'kaiser' (default) or 'hann'.
    beta : float
        Kaiser beta (ignored for hann).
    """
    meta, data_blocks = read_mdif(input_path)
    sparams = _all_sparams(data_blocks)
    if not sparams:
        raise ValueError("No S-parameter column pairs (sXX_db / sXX_deg) found in input MDIF.")

    header_tokens = ["%freq(real)"] + [
        token
        for sp in sparams
        for token in (f"{sp}_db(real)", f"{sp}_deg(real)")
    ]
    out_blocks = []

    for idx, block in enumerate(data_blocks):
        freq = block.get("freq")
        if freq is None or len(freq) < 2:
            continue

        block_sparams = _detect_sparam_pairs(block)
        df = float(np.mean(np.diff(freq)))
        n_orig = len(freq)
        n_pad = n_orig * zpad
        win = _make_window(n_orig, window, beta)
        dt = 1.0 / (n_pad * df)
        time = np.arange(n_pad) * dt
        gate = _make_gate(time, t_start, t_stop, taper)

        # Index in the zero-padded freq array where the original sweep starts
        f_start = float(freq[0])
        k_start = int(round(f_start / df))
        k_end = k_start + n_orig
        if k_end > n_pad:
            raise ValueError(
                f"Zero-padding factor {zpad} is too small: increase zpad so that "
                f"f_start/df + N ≤ N*zpad  (got {k_end} > {n_pad})."
            )

        gated: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        for sp in sparams:
            if sp in block_sparams:
                s_complex = _db_deg_to_complex(block[f"{sp}_db"], block[f"{sp}_deg"])
                padded = np.zeros(n_pad, dtype=complex)
                padded[:n_orig] = s_complex * win
                td = np.fft.ifft(padded) * n_pad
                td_gated = td * gate
                s_back = np.fft.fft(td_gated) / n_pad
                gated[sp] = _complex_to_db_deg(s_back[k_start:k_end])
            else:
                nan = np.full(n_orig, np.nan)
                gated[sp] = (nan, nan)

        row_meta = dict(meta[idx]) if idx < len(meta) else {}
        rows = [
            {
                "freq": float(freq[n]),
                **{f"{sp}_db": float(gated[sp][0][n]) for sp in sparams},
                **{f"{sp}_deg": float(gated[sp][1][n]) for sp in sparams},
            }
            for n in range(n_orig)
        ]
        out_blocks.append((row_meta, rows))

    write_mdif(output_path, out_blocks, header_tokens=header_tokens)
