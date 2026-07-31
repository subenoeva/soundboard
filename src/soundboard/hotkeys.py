"""Global keyboard shortcuts.

Kept behind a protocol so the grid's shortcut logic is testable without a real OS
keyboard hook — same role ``AudioBackend``/``FakeBackend`` play for the audio engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pynput import keyboard


class HotkeyManager(Protocol):
    def register(self, combo: str, callback: Callable[[], None]) -> None:
        """Register ``combo`` (pynput syntax, e.g. ``"<ctrl>+<alt>+1"``).

        Raises ``ValueError`` if ``combo`` is not a well-formed hotkey string.
        """
        ...

    def unregister(self, combo: str) -> None: ...

    def stop(self) -> None:
        """Release the OS hook and forget every combo registered so far."""
        ...


class PynputHotkeyManager:
    """Real implementation over ``pynput.keyboard.GlobalHotKeys``.

    ``GlobalHotKeys`` takes its whole mapping at construction time and has no API to
    add or remove a single combo, so every register/unregister rebuilds and restarts
    the underlying listener thread with the full current mapping.
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, Callable[[], None]] = {}
        self._listener: keyboard.GlobalHotKeys | None = None

    def register(self, combo: str, callback: Callable[[], None]) -> None:
        keyboard.HotKey.parse(combo)  # raises ValueError before touching the listener
        self._callbacks[combo] = callback
        self._restart()

    def unregister(self, combo: str) -> None:
        self._callbacks.pop(combo, None)
        self._restart()

    def stop(self) -> None:
        self._stop_listener()
        # Forgetting the callbacks is the point: they belong to whoever registered
        # them, and a later register() would otherwise resurrect them all when it
        # rebuilds the listener from the full mapping.
        self._callbacks.clear()

    def _stop_listener(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _restart(self) -> None:
        self._stop_listener()
        if self._callbacks:
            self._listener = keyboard.GlobalHotKeys(dict(self._callbacks))
            self._listener.start()


class FakeHotkeyManager:
    """In-memory double for tests: no OS hooks, ``trigger`` simulates a key press."""

    def __init__(self) -> None:
        self._callbacks: dict[str, Callable[[], None]] = {}

    def register(self, combo: str, callback: Callable[[], None]) -> None:
        keyboard.HotKey.parse(combo)
        self._callbacks[combo] = callback

    def unregister(self, combo: str) -> None:
        self._callbacks.pop(combo, None)

    def stop(self) -> None:
        self._callbacks.clear()

    def trigger(self, combo: str) -> None:
        self._callbacks[combo]()
