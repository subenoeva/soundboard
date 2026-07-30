"""Forces the offscreen Qt platform so widget tests never need a real display.

Must run before the first ``QApplication``/``QGuiApplication`` is constructed, which
happens lazily the first time a test requests pytest-qt's ``qtbot``/``qapp`` fixtures —
well after this module is imported during collection. ``setdefault`` lets a developer
override it (e.g. to watch a widget test run) by setting the env var beforehand.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
