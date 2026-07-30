"""Forces the offscreen Qt platform so widget tests never need a real display.

Must run before the first ``QApplication``/``QGuiApplication`` is constructed, which
happens lazily the first time a test requests pytest-qt's ``qtbot``/``qapp`` fixtures —
well after this module is imported during collection. ``setdefault`` lets a developer
override it (e.g. to watch a widget test run) by setting the env var beforehand.
"""

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Keep strong references to QMimeData objects created in tests to prevent garbage
# collection while QDropEvent objects still reference them
_mime_data_cache: list[Any] = []


def _patch_drop_event_test() -> None:
    """Monkeypatch to cache QMimeData objects during tests."""
    from PySide6.QtCore import QMimeData

    original_mime_init = QMimeData.__init__

    def patched_mime_init(self, *args, **kwargs):  # type: ignore
        original_mime_init(self, *args, **kwargs)
        _mime_data_cache.append(self)

    QMimeData.__init__ = patched_mime_init  # type: ignore


_patch_drop_event_test()


@pytest.fixture(autouse=True)
def _reset_mime_cache() -> Any:
    """Reset QMimeData cache between tests."""
    global _mime_data_cache
    _mime_data_cache = []
    yield
    _mime_data_cache = []
