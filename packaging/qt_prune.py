"""Drop the Qt libraries and QML modules the app never loads from a PyInstaller TOC.

PyInstaller's `excludes=` only filters the *module* graph. PySide6's hook copies Qt's
shared libraries as binaries through a separate path, so excluding `PySide6.QtWebEngineCore`
leaves the 200MB `Qt6WebEngineCore` library in the bundle regardless — measured: adding
47 PySide6 modules to `excludes` changed the Windows onefile size by 562 bytes. The only
thing that removes them is filtering `a.binaries` / `a.datas` after Analysis, which is
what this module does for both platform specs.

What has to survive is narrow and known: the GUI imports QtCore, QtGui, QtWidgets (the
tray icon and the two fatal-boot QMessageBox paths), QtQml, QtQuick and
QtQuick.Controls.Basic, and Main.qml imports QtQuick.Layouts. Everything else Qt ships is
dead weight here. Qt6Network is kept because QtQml links it, Qt6OpenGL because the RHI
backend needs it, Qt6ShaderTools because Qt6Quick imports it at load time, and Qt6Svg
because the imageformats/iconengines plugins link it.

`prune()` verifies rather than trusts: if a load-bearing pattern stops matching — a Qt
release renaming or relocating one of the heavy libraries — the build fails instead of
quietly shipping the weight again.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

# Matched against a library's file name, lowercased, with any `lib` prefix stripped, so
# one entry covers Windows' `Qt6WebEngineCore.dll` and Linux's `libQt6WebEngineCore.so.6`.
PRUNED_PREFIXES: tuple[str, ...] = (
    "qt6webengine",
    "qt6webchannel",
    "qt6webview",
    "qt6websockets",
    "qt63d",
    "qt6quick3d",
    "qt6graphs",
    "qt6charts",
    "qt6datavisualization",
    "qt6pdf",
    "qt6virtualkeyboard",
    "qt6multimedia",
    "qt6spatialaudio",
    "qt6location",
    "qt6positioning",
    "qt6sensors",
    "qt6scxml",
    "qt6statemachine",
    "qt6remoteobjects",
    "qt6texttospeech",
    "qt6sql",
    "qt6test",
    "qt6quicktest",
    "qt6concurrent",
    "qt6labs",
    # Every Qt Quick Controls style except Basic, which Main.qml imports by name.
    "qt6quickcontrols2imagine",
    "qt6quickcontrols2material",
    "qt6quickcontrols2universal",
    "qt6quickcontrols2fusion",
    "qt6quickcontrols2fluentwinui3",
    "qt6quickcontrols2windows",
    # Its only reason to exist is QtQml.LocalStorage, which links Qt6Sql (pruned above)
    # and which nothing here imports.
    "qt6qmllocalstorage",
    # Qt ships the machinery to *be* a Wayland compositor. A client app never needs it,
    # and PySide6's copy links libwayland-server.so.0, which desktops do not install.
    # Note this is the compositor only: Qt6WaylandClient is what the app runs on under a
    # Wayland session, and it stays.
    "qt6waylandcompositor",
)

# Plugins Qt loads with dlopen/LoadLibrary at runtime, whose Qt library the prune removes.
# They are not named Qt6*, so the prefix list above never reaches them: v0.4.1 shipped
# them with a dangling import. A plugin that fails to load does so deep inside Qt, where
# no traceback surfaces, which is exactly the kind of failure this project does not want.
#
# Matched without the file extension. Naming them `qpdf.dll` covered Windows only, and
# v0.4.3's AppImage shipped all three of them dangling under their `libqpdf.so` spelling —
# only `QT_DEBUG_PLUGINS=1` showed it, as "Cannot load library ...: libQt6Pdf.so.6: cannot
# open shared object file".
PRUNED_PLUGIN_STEMS: tuple[str, ...] = (
    "qpdf",  # imageformats, links Qt6Pdf
    "qtvirtualkeyboardplugin",  # platforminputcontexts, links Qt6VirtualKeyboard
    "qmldbg_quick3dprofiler",  # qmltooling, links Qt6Quick3DUtils
)

# Paths under PySide6's `qml/` directory, matched as whole module trees.
PRUNED_QML_MODULES: tuple[str, ...] = (
    "QtWebEngine",
    "QtWebChannel",
    "QtWebView",
    "QtWebSockets",
    "Qt3D",
    "QtQuick3D",
    "QtGraphs",
    "QtCharts",
    "QtDataVisualization",
    "QtLocation",
    "QtMultimedia",
    "QtPositioning",
    "QtRemoteObjects",
    "QtScxml",
    "QtSensors",
    "QtTest",
    "QtTextToSpeech",
    "Qt5Compat",
    "Qt/labs",
    "QtQml/StateMachine",
    # PySide6 ships the LocalStorage plugin under QtQuick, not QtQml as its library name
    # suggests; both are listed so a future reshuffle does not silently orphan it again.
    "QtQml/LocalStorage",
    "QtQuick/LocalStorage",
    "QtQuick/VirtualKeyboard",
    "QtQuick/Pdf",
    "QtQuick/NativeStyle",
    "QtQuick/Scene2D",
    "QtQuick/Scene3D",
    "QtQuick/Controls/Material",
    "QtQuick/Controls/Universal",
    "QtQuick/Controls/Fusion",
    "QtQuick/Controls/Imagine",
    "QtQuick/Controls/FluentWinUI3",
    "QtQuick/Controls/Windows",
    "QtQuick/Controls/macOS",
    "QtQuick/Controls/iOS",
    "QtQuick/Controls/designer",
    "QtWayland/Compositor",
)

# The subset that must match on every platform. The rest are platform-specific (a
# Windows-only style, a macOS-only style) and are allowed to match nothing; these are
# the ones whose disappearance would mean the prune has quietly stopped working.
REQUIRED_PREFIXES: tuple[str, ...] = (
    "qt6webengine",
    "qt63d",
    "qt6quick3d",
    "qt6pdf",
    "qt6charts",
    "qt6datavisualization",
    "qt6multimedia",
    "qt6virtualkeyboard",
    "qt6quickcontrols2material",
)


class PruneError(RuntimeError):
    """A pattern that should have matched a bundled Qt library matched nothing."""


def _library_stem(dest: str) -> str:
    """`PySide6/Qt/lib/libQt6Core.so.6` -> `qt6core`, `PySide6\\Qt6Core.dll` -> `qt6core`."""
    name = dest.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name.removeprefix("lib")


def _plugin_stem(dest: str) -> str:
    """`plugins/imageformats/libqpdf.so` and `plugins\\imageformats\\qpdf.dll` -> `qpdf`.

    Unlike the prefix match, plugin names are compared whole, so the extension has to go
    or one platform's spelling silently stops matching.
    """
    return _library_stem(dest).split(".", 1)[0]


def _qml_module_path(dest: str) -> str | None:
    """The path under PySide6's `qml/` directory, or None if the entry is not in one.

    The directory sits at `PySide6/qml/` on Windows and `PySide6/Qt/qml/` on Linux, so
    the marker is located rather than assumed.
    """
    parts = dest.replace("\\", "/").split("/")
    for index, part in enumerate(parts):
        if part == "qml" and index > 0 and parts[0] == "PySide6":
            return "/".join(parts[index + 1 :])
    return None


def _matched_prefix(dest: str) -> str | None:
    stem = _library_stem(dest)
    for prefix in PRUNED_PREFIXES:
        if stem.startswith(prefix):
            return prefix
    return None


def _is_pruned_qml(dest: str) -> bool:
    module_path = _qml_module_path(dest)
    if module_path is None:
        return False
    return any(
        module_path == module or module_path.startswith(f"{module}/")
        for module in PRUNED_QML_MODULES
    )


def prune[T: Sequence[Any]](entries: Iterable[T], verify: bool = True) -> list[T]:
    """Return `entries` without the Qt libraries and QML modules the app never loads.

    Set `verify=False` to skip the required-pattern check, which only makes sense on a
    fragment of a real TOC.
    """
    kept: list[T] = []
    matched: set[str] = set()
    for entry in entries:
        dest = str(entry[0])
        prefix = _matched_prefix(dest)
        if prefix is not None:
            matched.add(prefix)
            continue
        if _plugin_stem(dest) in PRUNED_PLUGIN_STEMS:
            continue
        if _is_pruned_qml(dest):
            continue
        kept.append(entry)

    if verify:
        missing = [p for p in REQUIRED_PREFIXES if p not in matched]
        if missing:
            raise PruneError(
                "these Qt libraries were expected in the bundle but no longer match: "
                f"{', '.join(missing)}. Qt most likely renamed or relocated them; update "
                "PRUNED_PREFIXES in packaging/qt_prune.py, or the build ships them again."
            )
    return kept
