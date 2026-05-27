# PyInstaller spec for rf-mdif-tdr (MDIF time-domain transform and gating)
# Build with:  pyinstaller specs\rf-mdif-tdr.spec

from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ["../mdif_tdr/cli.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "numpy.fft",
    ],
    hookspath=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="rf-mdif-tdr",
    console=True,
    onefile=True,
)
