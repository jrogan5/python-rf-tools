# -*- mode: python ; coding: utf-8 -*-
# Spec for the 4-pack path sorter (rf-sort-4pack.exe).


a = Analysis(
    ["sorting/4pack/sorting.py"],
    pathex=["."],
    hiddenimports=["_version", "utils.mdif", "utils.cli"],
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
    name="rf-sort-4pack",
    console=True,
    upx=False,
)
