"""PyInstaller runtime hook: makes ctypes.util.find_library see the PortAudio shared
object bundled into the AppDir by build_appimage.sh.

sounddevice resolves PortAudio via ctypes.util.find_library("portaudio") and raises
instead of falling back to a bundled copy on Linux (unlike its Windows/macOS paths).
PyInstaller's own ctypes patch that searches inside the bundle only runs on Windows
(see PyInstaller/loader/pyimod03_ctypes.py) — Linux needs this explicit hook.
"""

from __future__ import annotations

import ctypes.util
import os
import sys

_find_library = ctypes.util.find_library


def find_library(name: str) -> str | None:
    if name == "portaudio":
        bundled = os.path.join(sys._MEIPASS, "libportaudio.so.2")  # type: ignore[attr-defined]
        if os.path.isfile(bundled):
            return bundled
    return _find_library(name)


ctypes.util.find_library = find_library
