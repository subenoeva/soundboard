"""Global keyboard shortcuts.

Kept behind a protocol so the grid's shortcut logic is testable without a real OS
keyboard hook — same role ``AudioBackend``/``FakeBackend`` play for the audio engine.
"""

from __future__ import annotations
