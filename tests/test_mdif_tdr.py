"""Unit tests for mdif_tdr.converter (spec: claude.md)."""

import sys
from pathlib import Path
import tempfile

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mdif_tdr.converter import (
    s11_db_deg_to_complex,
    compute_tdr,
    run,
    _HEADER_TOKENS,
)
from utils.mdif import read_mdif


# ── helpers ───────────────────────────────────────────────────────────────────

def _uniform_freqs(f_start=1e8, f_stop=3e9, n=201):
    return np.linspace(f_start, f_stop, n)


# ── Test 1: round-trip dB/deg ↔ complex ──────────────────────────────────────

def test_s11_to_complex_roundtrip():
    """Round-trip dB/deg → complex → dB/deg must have < 1e-6 error."""
    rng = np.random.default_rng(0)
    db  = rng.uniform(-30, 0, 50)
    deg = rng.uniform(-180, 180, 50)

    cplx     = s11_db_deg_to_complex(db, deg)
    db_back  = 20.0 * np.log10(np.abs(cplx))
    deg_back = np.degrees(np.angle(cplx))

    assert np.max(np.abs(db_back  - db))  < 1e-6
    assert np.max(np.abs(deg_back - deg)) < 1e-6


# ── Test 2: matched load (S11 = 0) ───────────────────────────────────────────

def test_tdr_matched_load():
    """S11 = -∞ dB (magnitude 0) → impulse ≈ 0, step ≈ 0, Z ≈ Z0."""
    freqs  = _uniform_freqs()
    db     = np.full(len(freqs), -200.0)   # effectively 0 magnitude
    deg    = np.zeros(len(freqs))

    tdr = compute_tdr(freqs, db, deg, z0=50.0, npad=4)

    assert np.max(np.abs(tdr["impulse"])) < 1e-6
    assert np.max(np.abs(tdr["step"]))    < 1e-6
    assert np.allclose(tdr["Z"], 50.0, atol=1e-3)


# ── Test 3: open circuit (Γ = +1) ────────────────────────────────────────────

def test_tdr_open_circuit():
    """S11 = 0 dB, 0° (Γ = +1) → step is positive, Z at peak >> Z0.

    Kaiser β=6 has coherent gain ≈ 0.40, so the step peaks near 0.35, not 1.0.
    The threshold of 0.25 confirms sign and rough magnitude without demanding
    perfect DC convergence.
    """
    z0    = 50.0
    freqs = _uniform_freqs()
    db    = np.zeros(len(freqs))
    deg   = np.zeros(len(freqs))

    tdr = compute_tdr(freqs, db, deg, z0=z0, npad=4)

    assert tdr["step"].max() > 0.25
    peak_idx = np.argmax(tdr["step"])
    assert tdr["Z"][peak_idx] > z0  # windowed step ~0.35 → Z ≈ 104 Ω >> 50 Ω


# ── Test 4: short circuit (Γ = −1) ───────────────────────────────────────────

def test_tdr_short_circuit():
    """S11 = 0 dB, 180° (Γ = −1) → step is negative, Z at trough < Z0.

    Same Kaiser gain caveat as open circuit — threshold is 0.25 in magnitude.
    """
    z0    = 50.0
    freqs = _uniform_freqs()
    db    = np.zeros(len(freqs))
    deg   = np.full(len(freqs), 180.0)

    tdr = compute_tdr(freqs, db, deg, z0=z0, npad=4)

    assert tdr["step"].min() < -0.25
    peak_idx = np.argmin(tdr["step"])
    assert tdr["Z"][peak_idx] < z0  # windowed step ~-0.35 → Z ≈ 24 Ω < 50 Ω


# ── Test 5: DC extrapolation does not shift time origin ──────────────────────

def test_dc_extrapolation_time_origin():
    """
    A pure delay in the frequency domain (S11 = e^{-j*2π*f*τ}) should produce
    an impulse peak at t ≈ τ.  The DC fill must not shift this.
    """
    tau_ns = 3.0                             # 3 ns round-trip delay
    freqs  = _uniform_freqs(f_start=1e8, f_stop=3e9, n=201)
    deg    = -np.degrees(2 * np.pi * freqs * tau_ns * 1e-9)
    db     = np.zeros(len(freqs))            # |Γ| = 1 everywhere

    tdr = compute_tdr(freqs, db, deg, npad=20)

    peak_t_ns = tdr["t_ns"][np.argmax(np.abs(tdr["impulse"]))]
    # Allow ±2 × time step tolerance
    dt_ns = float(np.diff(tdr["t_ns"][:2])[0])
    assert abs(peak_t_ns - tau_ns) < 2.0 * dt_ns, (
        f"Peak at {peak_t_ns:.4f} ns, expected {tau_ns:.4f} ns "
        f"(tolerance {2*dt_ns:.4f} ns)"
    )


# ── Test 6: end-to-end MDIF round-trip ───────────────────────────────────────

def test_output_mdif_parseable(tmp_path):
    """
    Write a synthetic input MDIF with two blocks, run the converter, re-parse
    the output and verify structure.
    """
    # Build a minimal synthetic MDIF
    freqs = _uniform_freqs(f_start=1e8, f_stop=2e9, n=51)
    input_mdif = tmp_path / "synthetic.mdif"

    lines = []
    for block_idx in range(2):
        lines.append(f"VAR Net(real) = {block_idx + 1}\n")
        lines.append("BEGIN ACDATA\n")
        lines.append("%freq(real)  s11_db(real)  s11_deg(real)\n")
        for f in freqs:
            deg = -np.degrees(2 * np.pi * f * 2e-9)   # 2 ns delay
            lines.append(f"{f:.6g}  -6.0  {deg:.6g}\n")
        lines.append("END\n\n")
    input_mdif.write_text("".join(lines))

    output_mdif = tmp_path / "synthetic_tdr.mdif"
    run(input_mdif, output_mdif, npad=4)

    meta_arr, data_blocks = read_mdif(output_mdif)

    assert len(data_blocks) == 2, f"Expected 2 blocks, got {len(data_blocks)}"

    expected_cols = {"time_ns", "gam_impulse", "gam_step", "impedance"}
    for i, block in enumerate(data_blocks):
        assert expected_cols <= set(block.keys()), (
            f"Block {i} missing columns. Got: {set(block.keys())}"
        )
        assert len(block["time_ns"]) > 0, f"Block {i} has no rows"
