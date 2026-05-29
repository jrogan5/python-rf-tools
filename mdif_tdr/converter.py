
"""MDIF time‑domain transform and gating."""
import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy import signal
from numpy.fft import fft, ifft

from utils.mdif import read_mdif, write_mdif


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
    seen = set()
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
    g = np.zeros_like(t)
    if tap > 0:
        r = (t >= t0) & (t < t0 + tap)
        g[r] = 0.5 * (1 - np.cos(np.pi * (t[r] - t0) / tap))
        f = (t > t1 - tap) & (t <= t1)
        g[f] = 0.5 * (1 - np.cos(np.pi * (t1 - t[f]) / tap))
    g[(t >= t0 + tap) & (t <= t1 - tap)] = 1.0
    if tap == 0.0:
        g[(t >= t0) & (t <= t1)] = 1.0
    return g


def _s11_to_tdr(freq, s11, *, vf=0.66, win="hann", beta=6.0, zpad=4):
    if freq.shape != s11.shape:
        raise ValueError("freq and s11 must have the same shape")
    order = np.argsort(freq)
    f = freq[order]
    s = s11[order]

    n0 = len(f)
    n = int(n0 * zpad)
    w = _make_window(n0, win, beta)

    padded = np.zeros(n, dtype=complex)
    padded[:n0] = s * w
    impulse = ifft(padded) * n / np.sum(w)

    df = np.mean(np.diff(f))
    dt = 1.0 / (n * df)
    time = np.arange(n) * dt
    step = np.cumsum(np.real(impulse)) * dt

    c = 299_792_458.0
    dist = vf * c * time / 2.0
    return time, dist, step


def run_tdr(inp: Path, out: Path, *, zpad=8, window="kaiser", beta=6.0):
    meta, blocks = read_mdif(inp)
    sparams = _all_sparams(blocks)
    if not sparams:
        raise ValueError("No S‑parameter columns found")
    hdr = ["%time(real)"] + [f"{s}_db(real)" for s in sparams]
    out_blocks = []

    for i, blk in enumerate(blocks):
        freq = blk.get("freq")
        if freq is None or len(freq) < 2:
            continue
        blk_sp = _detect_sparam_pairs(blk)
        td_db = {}
        for sp in sparams:
            if sp in blk_sp:
                comp = _db_deg_to_complex(blk[f"{sp}_db"], blk[f"{sp}_deg"])
                _, _, step = _s11_to_tdr(freq, comp, win=window,
                                         beta=beta, zpad=zpad)
                half = len(step) // 2
                td_db[sp] = _complex_to_db(step[:half])
            else:
                half = len(freq) * zpad // 2
                td_db[sp] = np.full(half, np.nan)

        n = td_db[sparams[0]].size
        df = np.mean(np.diff(freq))
        dt = 1.0 / (df * zpad * len(freq))
        t_axis = np.arange(n) * dt
        rows = [
            {"time": float(t_axis[k]),
             **{f"{sp}_db": float(td_db[sp][k]) for sp in sparams}}
            for k in range(n)
        ]
        out_blocks.append((dict(meta[i]) if i < len(meta) else {}, rows))

    write_mdif(out, out_blocks, header_tokens=hdr)


def run_gate(inp: Path, out: Path, *, t_start, t_stop,
             taper=0.1e-9, zpad=8, window="kaiser", beta=6.0):
    meta, blocks = read_mdif(inp)
    sparams = _all_sparams(blocks)
    if not sparams:
        raise ValueError("No S‑parameter columns found")
    hdr = ["%freq(real)"] + [
        token for sp in sparams for token in (f"{sp}_db(real)", f"{sp}_deg(real)")
    ]
    out_blocks = []

    for i, blk in enumerate(blocks):
        freq = blk.get("freq")
        if freq is None or len(freq) < 2:
            continue
        blk_sp = _detect_sparam_pairs(blk)

        df = float(np.mean(np.diff(freq)))
        n0 = len(freq)
        n = n0 * zpad
        win = _make_window(n0, window, beta)

        dt = 1.0 / (n * df)
        t = np.arange(n) * dt
        gate = _make_gate(t, t_start, t_stop, taper)

        f0 = float(freq[0])
        k0 = int(round(f0 / df))
        k1 = k0 + n0
        if k1 > n:
            raise ValueError("zpad too small for sweep start frequency")

        gated = {}
        for sp in sparams:
            if sp in blk_sp:
                comp = _db_deg_to_complex(blk[f"{sp}_db"], blk[f"{sp}_deg"])
                padded = np.zeros(n, dtype=complex)
                padded[:n0] = comp * win
                td = ifft(padded) * n / np.sum(win)
                td_g = td * gate
                back = fft(td_g) / n * np.sum(win)
                gated[sp] = _complex_to_db_deg(back[k0:k1])
            else:
                nan = np.full(n0, np.nan)
                gated[sp] = (nan, nan)

        rows = [
            {"freq": float(freq[k]),
             **{f"{sp}_db": float(gated[sp][0][k]) for sp in sparams},
             **{f"{sp}_deg": float(gated[sp][1][k]) for sp in sparams}}
            for k in range(n0)
        ]
        out_blocks.append((dict(meta[i]) if i < len(meta) else {}, rows))

    write_mdif(out, out_blocks, header_tokens=hdr)
