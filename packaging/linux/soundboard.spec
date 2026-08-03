# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Linux --onedir build, later assembled into an AppImage
by build_appimage.sh.

Same keyring hidden-import risk as Windows, here for the SecretService backend.
pynput has the identical problem: it picks its keyboard/mouse backend via
importlib.import_module() at runtime based on sys.platform, so static analysis
never sees pynput._xorg/_base or the Xlib package it needs on X11/Xwayland — the
packaged app used to die on `import pynput.keyboard` before any window opened.

The effects chain adds two more of the same shape. onnxruntime loads its provider
libraries out of onnxruntime/capi at session construction, and pedalboard's DSP lives
in pedalboard_native, a top-level extension module the graph reaches only because it
is named here; collect_all covers the rest of both packages.

The neural block's weights are fetched and hash-checked before Analysis runs rather
than committed, so the file bundled below is always the pinned revision — see
packaging/fetch_model.py. It ships inside the bundle because first launch has to work
offline, and THIRD-PARTY-NOTICES plus the GPL-3.0, LGPL-3.0 and Apache-2.0 texts ship
beside it: this build redistributes PySide6, pedalboard, onnxruntime and CEVA's model,
and those licences want their text carried, not cited. Qt arrives here as separate
shared libraries the user can replace in _internal/, which is LGPL-3 §4(d)(1); the
notices file argues §4(d)(0) as well, because the Windows onefile build has no other
route and one notices file serves both.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

sys.path.insert(0, os.path.join(SPECPATH, ".."))
from fetch_model import ensure_model  # noqa: E402  (needs the path entry above)
from qt_prune import prune  # noqa: E402
from third_party_notices import write_notices  # noqa: E402

entry_point = os.path.join(SPECPATH, "..", "..", "src", "soundboard", "__main__.py")
build_dir = Path(SPECPATH).parents[1] / "build"

model_path = ensure_model()
notices_datas = write_notices(build_dir / "notices")

xlib_datas, xlib_binaries, xlib_hiddenimports = collect_all("Xlib")
onnxruntime_datas, onnxruntime_binaries, onnxruntime_hiddenimports = collect_all("onnxruntime")
pedalboard_datas, pedalboard_binaries, pedalboard_hiddenimports = collect_all("pedalboard")

a = Analysis(
    [entry_point],
    pathex=[os.path.join(SPECPATH, "..", "..", "src")],
    binaries=[
        *xlib_binaries,
        *onnxruntime_binaries,
        *pedalboard_binaries,
    ],
    datas=[
        *xlib_datas,
        *notices_datas,
        *onnxruntime_datas,
        *pedalboard_datas,
        (
            os.path.join(SPECPATH, "..", "..", "src", "soundboard", "ui", "qml"),
            os.path.join("soundboard", "ui", "qml"),
        ),
        (
            str(model_path),
            os.path.join("soundboard", "effects", "models"),
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
        *onnxruntime_hiddenimports,
        *pedalboard_hiddenimports,
        "pedalboard_native",
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
