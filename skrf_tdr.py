import skrf as rf
import numpy as np
import matplotlib.pyplot as plt

# Load S1P
ntwk = rf.Network(r'C:\Users\jrog1\Documents\MDA\python-rf-tools\templates\s1p_adc0\ADC0_IdxASIC10_RefDesDBF220.s1p')

# Apply Kaiser window (β=6 ≈ -44 dB sidelobes) before IFFT
ntwk_w = ntwk.windowed(window=('kaiser', 6))

# --- Impulse response ---
fig, axes = plt.subplots(3, 1, figsize=(10, 10))

t = ntwk_w.s_time_db.flatten()  # time axis is in ntwk.frequency... 
# Actually use:
ntwk_w.plot_s_time_db(ax=axes[0], label='S11 impulse (dB)')
axes[0].set_title('TDR Impulse Response')
axes[0].set_xlabel('Time (ns)')
axes[0].set_xlim([0, 20])  # adjust for your expected line length

# --- Step response and impedance ---
# Manual computation from windowed network
s11 = ntwk_w.s[:, 0, 0]        # complex S11 array
freqs = ntwk_w.f                # Hz

# IFFT to get impulse response (skrf zero-pads internally for plot,
# but we'll do it manually for the impedance profile)
Z0 = ntwk.z0[0, 0].real     # reference impedance (usually 50 Ω)