# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Linux --onedir build, later assembled into an AppImage
by build_appimage.sh.

Same keyring hidden-import risk as Windows, here for the SecretService backend.
pynput has the identical problem: it picks its keyboard/mouse backend via
importlib.import_module() at runtime based on sys.platform, so static analysis
never sees pynput._xorg/_base or the Xlib package it needs on X11/Xwayland — the
packaged app used to die on `import pynput.keyboard` before any window opened.
See docs/superpowers/specs/2026-07-30-standalone-executables-design.md.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

entry_point = os.path.join(SPECPATH, "..", "..", "src", "soundboard", "__main__.py")

xlib_datas, xlib_binaries, xlib_hiddenimports = collect_all("Xlib")

a = Analysis(
    [entry_point],
    pathex=[os.path.join(SPECPATH, "..", "..", "src")],
    binaries=xlib_binaries,
    datas=xlib_datas,
    hiddenimports=[
        *collect_submodules("keyring.backends"),
        *collect_submodules("pynput"),
        *xlib_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPECPATH, "rt_hook_portaudio.py")],
    excludes=[],
    noarchive=False,
)
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
