# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows --onefile --windowed build.

keyring discovers its backends (here: the Windows Credential Locker) via
entry-points, which PyInstaller's static import analysis does not follow —
without collect_submodules the packaged exe raises "no recommended backend"
at runtime. pynput has the same problem: it picks pynput.keyboard._win32 /
pynput.mouse._win32 via importlib.import_module() at runtime, so without
collect_submodules the packaged exe dies on `import pynput.keyboard` instead.

The effects chain adds two more of the same shape. onnxruntime loads its provider
DLLs out of onnxruntime/capi at session construction, and pedalboard's DSP lives in
pedalboard_native, a top-level extension module the graph reaches only because it is
named here; collect_all covers the rest of both packages.

The neural block's weights are fetched and hash-checked before Analysis runs rather
than committed, so the file bundled below is always the pinned revision — see
packaging/fetch_model.py. It ships inside the binary because first launch has to work
offline, and THIRD-PARTY-NOTICES plus the full Apache-2.0 text ship with it: this
build redistributes PySide6, pedalboard, onnxruntime and CEVA's model, and Apache-2.0
§4 wants the licence carried, not cited. With --onefile they live in the archive,
which is the only "beside the binary" a single executable has.
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

onnxruntime_datas, onnxruntime_binaries, onnxruntime_hiddenimports = collect_all("onnxruntime")
pedalboard_datas, pedalboard_binaries, pedalboard_hiddenimports = collect_all("pedalboard")

a = Analysis(
    [entry_point],
    pathex=[os.path.join(SPECPATH, "..", "..", "src")],
    binaries=[
        *onnxruntime_binaries,
        *pedalboard_binaries,
    ],
    datas=[
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
        *onnxruntime_hiddenimports,
        *pedalboard_hiddenimports,
        "pedalboard_native",
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
# Qt's own libraries are copied by PySide6's hook, not through the module graph, so
# `excludes=` above cannot reach them — see packaging/qt_prune.py.
a.binaries = prune(a.binaries)
a.datas = prune(a.datas, verify=False)

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
