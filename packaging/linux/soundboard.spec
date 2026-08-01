# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Linux --onedir build, later assembled into an AppImage
by build_appimage.sh.

Same keyring hidden-import risk as Windows, here for the SecretService backend.
pynput has the identical problem: it picks its keyboard/mouse backend via
importlib.import_module() at runtime based on sys.platform, so static analysis
never sees pynput._xorg/_base or the Xlib package it needs on X11/Xwayland — the
packaged app used to die on `import pynput.keyboard` before any window opened.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

sys.path.insert(0, os.path.join(SPECPATH, ".."))
from qt_prune import prune  # noqa: E402  (needs the path entry above)

entry_point = os.path.join(SPECPATH, "..", "..", "src", "soundboard", "__main__.py")

xlib_datas, xlib_binaries, xlib_hiddenimports = collect_all("Xlib")

a = Analysis(
    [entry_point],
    pathex=[os.path.join(SPECPATH, "..", "..", "src")],
    binaries=xlib_binaries,
    datas=[
        *xlib_datas,
        (
            os.path.join(SPECPATH, "..", "..", "src", "soundboard", "ui", "qml"),
            os.path.join("soundboard", "ui", "qml"),
        ),
    ],
    hiddenimports=[
        *collect_submodules("keyring.backends"),
        *collect_submodules("pynput"),
        # collect_submodules imports pynput to enumerate it, and on a headless build
        # runner `import pynput.keyboard` raises before the X11 backend is ever walked,
        # so the list above comes back without it. The AppImage then died on launch
        # under a real X server with "No module named 'pynput.keyboard._xorg'". Naming
        # them makes the bundle independent of what the build machine happens to have.
        "pynput.keyboard._xorg",
        "pynput.mouse._xorg",
        "pynput._util.xorg",
        "pynput._util.xorg_keysyms",
        *xlib_hiddenimports,
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPECPATH, "rt_hook_portaudio.py")],
    excludes=[],
    noarchive=False,
)
# Qt's own libraries are copied by PySide6's hook, not through the module graph, so
# `excludes=` above cannot reach them — see packaging/qt_prune.py.
a.binaries = prune(a.binaries)
a.datas = prune(a.datas, verify=False)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="soundboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="soundboard",
)
