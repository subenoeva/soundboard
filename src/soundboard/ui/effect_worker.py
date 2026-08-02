"""Builds one expensive effect outside the Qt thread."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from soundboard.effects.chain import Effect
from soundboard.effects.neural import default_model_path, load_neural
from soundboard.effects.registry import create
from soundboard.ui.effects_store import EffectEntry


class _EffectSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class EffectLoadWorker(QRunnable):
    def __init__(self, load: Callable[[], Effect]) -> None:
        super().__init__()
        self._load = load
        self.signals = _EffectSignals()

    def run(self) -> None:
        try:
            effect = self._load()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(effect)


def load_effect_entry(entry: EffectEntry, blocksize: int) -> Effect:
    """Build one saved row; expensive kinds reach this only inside the worker."""
    if entry.kind == "neural":
        return load_neural(default_model_path(), blocksize=blocksize, params=entry.params)
    return create(entry.kind, entry.params)
