# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)
icon = project / "book_resale_finder" / "resources" / "icon.ico"

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[
        (str(icon), "book_resale_finder/resources"),
    ],
    hiddenimports=[
        "keyring.backends.Windows",
        "keyring.backends.null",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pandas", "numpy"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

# Use an onedir build. Qt/PySide applications are substantially more reliable
# this way because DLLs and platform plugins do not have to be unpacked into a
# temporary folder every time the program starts.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BookResaleFinder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BookResaleFinder",
)
