# -*- mode: python ; coding: utf-8 -*-
# Spec for the unified MDIF generator (rf-mdif.exe).
# Add new converter packages to _hidden when extending the tool.



_hidden = [
    "_version",
    "utils.mdif",
    "utils.net",
    "utils.io",
    "utils.cli",
    "utils.freq",
    "data_to_mdif.gain.converter",
    "data_to_mdif.gain.parser",
    "data_to_mdif.imd.converter",
    "data_to_mdif.imd.parser",
    "data_to_mdif.nf.converter",
    "data_to_mdif.nf.parser",
    "data_to_mdif.s2p.converter",
    "data_to_mdif.s2p.parser",
]

a = Analysis(
    ["data_to_mdif/cli.py"],
    pathex=["."],
    hiddenimports=_hidden,
    datas=[],
    binaries=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rf-mdif",
    console=True,
    upx=False,
)
