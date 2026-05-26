# PyInstaller spec for rf-dbf-to-mdif (DBF .mat → MDIF converter)
# Build with:  pyinstaller rf-dbf-to-mdif.spec

from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ["dbf_to_mdif/cli.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
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
    name="rf-dbf-to-mdif",
    console=True,
    onefile=True,
)
