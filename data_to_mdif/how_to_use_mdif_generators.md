`how_to_use_mdif_generators.txt`

James Rogan (May 2026)



These are a set of tools that can compile measurements of many, many nets in separate files into large .mdif files containg measured data for many nets. 

**Non-linear characteristics (Gain compression, IMD sweep) MDIF files:**

Steps to use without CLI:
* call  `python .\master_mdif_generator_nl_char.py`
* user will be promped with: `Base directory containing net folders (E1, E2, …): `. User may enter a path, eg. `C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement`.
* user will be promped with: `Temperature that measuremetns were taken at (°C): `. User may enter `int` or `float` eg. `23`.

For usage with CLI, just run `python .\master_mdif_generator_linear_char.py -h` to see options. 

The ouputs will be placed in a directory `plots` that is created under the supplied `base_path`. The outputs are:
1. An MDIF file containing all the gain compression data 
2. A txt file containing all the nets with malformed gain compression measurement data (and thus were omitted from the MDIF)
3. An MDIF file containing all the IMD sweep data 
4. A txt file containing all the nets with malformed IMD sweep measurement data (and thus were omitted from the MDIF)

Example:

```
PS C:\Users\ja099685\Desktop\RF_Task_1> python .\master_mdif_generator_nl_char.py
Base directory containing net folders (E1, E2, …): C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
Temperature that measuremetns were taken at (°C): 23

=== Running imd_sweep_to_mdif.py ===
INFO: [INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E75\E75_IMD_Swp.csv (net E75): Header line starting with 'FrequencyFC' not found in E75_IMD_Swp.csv
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E140 – skipping
INFO: [INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E244\E244_SWP_IMD.csv (net E244): Header line starting with 'FrequencyFC' not found in E244_SWP_IMD.csv
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E282 – skipping
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E284 – skipping
INFO: [INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E333\E333_SWP_IMD.csv (net E333): Header line starting with 'FrequencyFC' not found in E333_SWP_IMD.csv
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E383 – skipping
INFO: [INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E392\E392_SWP_IMD.csv (net E392): Header line starting with 'FrequencyFC' not found in E392_SWP_IMD.csv
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E426 – skipping
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E464 – skipping
INFO: [INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E468\E468_SWP_IMD.csv (net E468): Header line starting with 'FrequencyFC' not found in E468_SWP_IMD.csv
INFO: [INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E478 – skipping
INFO: A detailed bad measurement report has been written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\imd_sweep_bad_measurements.txt
INFO:
=== IMD\u2011sweep aggregation finished ===
INFO: Base path          : C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
INFO: Temperature (°C)   : 23.0
INFO: Nets processed     : 459
INFO: Total CSV rows used: 188649
INFO: Combined MDIF written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\RDI_IMD_sweep.mdif
INFO:
Nets that had no (or malformatted) IMD\u2011SWP CSV files and were omitted:
INFO:   - E140
INFO:   - E282
INFO:   - E284
INFO:   - E383
INFO:   - E426
INFO:   - E464
INFO:   - E478

=== Running gain_compression_to_mdif.py ===
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E63 – net will be omitted
[INFO] Incomplete log measurement file: E105_Gain_Comp_27p5.csv. Only S21 Log Mag(dB) present.
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E124 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E133 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E140 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E191 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E226 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E237 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E244 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E278 – net will be omitted
[INFO] Incomplete log measurement file: E337_Gain_Comp_27p5.csv. Only S21 Log Mag(dB) present.
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E383 – net will be omitted
[INFO] No CSV files found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E464 – net will be omitted

A detailed malformed measurement report has been written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\gain_comp_bad_measurements.txt

=== Gain compression aggregation finished ===
Base path                : C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
Temperature (°C)         : 23.0
Nets discovered          : 471
Nets used in MDIF       : 457
Total CSV files read    : 1371
Combined MDIF written to : C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\RDI_gain_compression.mdif

Nets that had **no** GainComp CSV files and were omitted:
  - E63
  - E124
  - E133
  - E140
  - E191
  - E226
  - E237
  - E244
  - E278
  - E383
  - E464

CSV files that were malformed (their nets were omitted):
  - C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E105\E105_Gain_Comp_27p5.csv
  - C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E337\E337_Gain_Comp_27p5.csv
  - C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E391\E391_Gain_Comp_27p5.csv

Nets that contained malformed data:
  Net E105:
    • C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E105\E105_Gain_Comp_27p5.csv
      Reason: 'R1,1 columns missing (neither DEG nor REAL/IMAG found)'
  Net E337:
    • C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E337\E337_Gain_Comp_27p5.csv
      Reason: 'R1,1 columns missing (neither DEG nor REAL/IMAG found)'
  Net E391:
    • C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E391\E391_Gain_Comp_27p5.csv
      Reason: 'S21 columns missing (neither DB/DEG nor REAL/IMAG found)'
[INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E105\E105_Gain_Comp_27p5.csv (net E105): 'R1,1 columns missing (neither DEG nor REAL/IMAG found)'
[INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E337\E337_Gain_Comp_27p5.csv (net E337): 'R1,1 columns missing (neither DEG nor REAL/IMAG found)'
[INFO] Skipping malformed CSV file C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E391\E391_Gain_Comp_27p5.csv (net E391): 'S21 columns missing (neither DB/DEG nor REAL/IMAG found)'

=== All MDIF files have been generated successfully ===
```

**Linear characteristics (NB, WB, and NF) MDIF files:**

Steps to use without CLI:
* call  `python .\master_mdif_generator_linear_char.py`
* user will be promped with: `Base directory containing net folders (E1, E2, …): `. User may enter a path, eg. `C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement`.
* user will be promped with: `Temperature that measuremetns were taken at (°C): `. User may enter `int` or `float` eg. `23`.

For usage with CLI, just run `python .\master_mdif_generator_linear_char.py -h` to see options. 

The ouputs will be placed in a directory `plots` that is created under the supplied `base_path`. The outputs are:
1. An MDIF file containing all the WB measured data organized by net
2. An MDIF file containing all the NB measured data organized by net
3. An MDIF file containing all the NF measured data organized by net
4. A txt file containing all the nets with malformed WB measurement data (and thus were omitted from the MDIF)
5. A txt file containing all the nets with malformed NB measurement data (and thus were omitted from the MDIF)
6. A txt file containing all the nets with malformed NF measurement data (and thus were omitted from the MDIF)


Example:

```
PS C:\Users\ja099685\Desktop\RF_Task_1> python .\master_mdif_generator_linear_char.py
Base directory containing net folders (E1, E2, …): C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
Temperature that measuremetns were taken at (°C): 23

=== Running s2p_to_mdif.py ===
INFO: Using filename pattern: *NB*.s2p
INFO: [INFO] No '*NB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E140 – skipping
INFO: [INFO] No '*NB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E158 – skipping
INFO: [INFO] No '*NB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E355 – skipping
INFO: [INFO] No '*NB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E383 – skipping
INFO: A detailed bad measurement report has been written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\s2p_bad_measurements.txt
INFO:
=== S2P \u2192 MDIF aggregation finished ===
INFO: Base path          : C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
INFO: Temperature (°C)   : 23.0
INFO: Nets processed     : 467
INFO: Total data rows    : 1915167
INFO: Combined MDIF written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\measured_NB.mdif

=== Running s2p_to_mdif.py ===
INFO: Using filename pattern: *WB*.s2p
INFO: [INFO] No '*WB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E158 – skipping
INFO: [INFO] No '*WB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E355 – skipping
INFO: [INFO] No '*WB*.s2p' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E383 – skipping
INFO: A detailed bad measurement report has been written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\s2p_bad_measurements.txt
INFO:
=== S2P \u2192 MDIF aggregation finished ===
INFO: Base path          : C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
INFO: Temperature (°C)   : 23.0
INFO: Nets processed     : 468
INFO: Total data rows    : 1872000
INFO: Combined MDIF written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\measured_WB.mdif

=== Running nf_sweep_to_mdif.py ===
INFO: Looking for files matching pattern: *NF*.csv
INFO: [INFO] No '*NF*.csv' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E140 – skipping
INFO: [INFO] No '*NF*.csv' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E147 – skipping
INFO: [INFO] No '*NF*.csv' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E350 – skipping
INFO: [INFO] No '*NF*.csv' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E383 – skipping
INFO: [INFO] No '*NF*.csv' file found in C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\E478 – skipping
INFO: A detailed bad measurement report has been written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\nf_bad_measurements.txt
INFO:
=== NF\u2011sweep aggregation finished ===
INFO: Base path          : C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement
INFO: Temperature (°C)   : 23.0
INFO: Nets processed     : 466
INFO: Total CSV rows used: 191526
INFO: Combined MDIF written to: C:\Users\ja099685\Desktop\RF_Task_1\RF Measurement\plots\measured_NF.mdif

=== All MDIF files have been generated successfully ===
```
