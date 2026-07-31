"""Forces the offscreen Qt platform so Qt tests never need a real display.

Must run before the first ``QApplication``/``QGuiApplication`` is constructed, which
happens lazily the first time a test requests pytest-qt's ``qtbot``/``qapp`` fixtures —
well after this module is imported during collection. ``setdefault`` lets a developer
override it (e.g. to watch a widget test run) by setting the env var beforehand.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if sys.platform == "win32":
    # PySide6 adds its own package directory to ``PATH`` in ``PySide6/__init__.py``, but
    # on some Windows setups that isn't enough for the QML engine's internal DLL loader to
    # resolve a QML plugin's own dependencies — e.g. ``QtQuick``'s ``qtquick2plugin.dll``
    # depending on ``Qt6Quick.dll``, or ``QtQuick.Controls.Basic``'s style plugin depending
    # on ``Qt6QuickControls2Basic.dll`` — failing with "the specified module could not be
    # found" even though the file sits right next to ``PySide6/__init__.py``. Registering
    # the directory via ``os.add_dll_directory`` (rather than relying on ``PATH``) fixes
    # it; must run before the first ``QQmlEngine`` is constructed.
    import PySide6

    pyside6_file = PySide6.__file__
    assert pyside6_file is not None
    os.add_dll_directory(str(Path(pyside6_file).resolve().parent))
