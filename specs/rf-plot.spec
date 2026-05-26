# PyInstaller spec for rf-plot (standalone MDIF plotter)
# Build with:  pyinstaller rf-plot.spec

from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ["../plot/cli.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "matplotlib.backends.backend_tkagg",
        "scipy.io",
        "scipy.io.matlab",
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
    name="rf-plot",
    console=True,
    onefile=True,
)
