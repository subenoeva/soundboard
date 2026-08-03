"""Keeps cyclic garbage collection off the audio callback thread."""

from __future__ import annotations

import gc

_active = False
_was_enabled = False


def enable() -> None:
    """Freeze startup objects and hand collection to the Qt poll timer."""
    global _active, _was_enabled
    if _active:
        return
    _was_enabled = gc.isenabled()
    gc.freeze()
    gc.disable()
    _active = True


def collect() -> None:
    """Run a collection explicitly; safe to call even without a neural block."""
    if _active:
        gc.collect()


def restore() -> None:
    """Return collection policy to what the process used before the neural block."""
    global _active
    if not _active:
        return
    _active = False
    if _was_enabled:
        gc.enable()
