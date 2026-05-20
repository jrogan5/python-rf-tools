# -*- mode: python ; coding: utf-8 -*-
# Spec for the RDI net sorter (rf-sort-rdi.exe).


a = Analysis(
    ["../sorting/rdi/sorting.py"],
    pathex=[".."],
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
    name="rf-sort-rdi",
    console=True,
    upx=False,
)
