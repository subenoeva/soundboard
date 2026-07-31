# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows --onefile --windowed build.

keyring discovers its backends (here: the Windows Credential Locker) via
entry-points, which PyInstaller's static import analysis does not follow —
without collect_submodules the packaged exe raises "no recommended backend"
at runtime. pynput has the same problem: it picks pynput.keyboard._win32 /
pynput.mouse._win32 via importlib.import_module() at runtime, so without
collect_submodules the packaged exe dies on `import pynput.keyboard` instead.
See docs/superpowers/specs/2026-07-30-standalone-executables-design.md.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

entry_point = os.path.join(SPECPATH, "..", "..", "src", "soundboard", "__main__.py")

a = Analysis(
    [entry_point],
    pathex=[os.path.join(SPECPATH, "..", "..", "src")],
    binaries=[],
    datas=[
        (
            os.path.join(SPECPATH, "..", "..", "src", "soundboard", "ui", "qml"),
            os.path.join("soundboard", "ui", "qml"),
        ),
    ],
    hiddenimports=[
        *collect_submodules("keyring.backends"),
        *collect_submodules("pynput"),
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="soundboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
