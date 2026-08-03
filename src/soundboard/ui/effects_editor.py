"""The plugin windows the rack has open, and what they send back.

``ui/vst_editor_process.py`` is the process; this is what the rack does with it.
The two halves are split from ``effects_model.py`` because that file is at its line
budget, and because they belong together: a window is opened for one block, and
everything it reports has to land in that block through the same funnel a slider
uses — clamped, handed to the chain, written down.

Windows are keyed by the effect rather than by the row. A row is a frozen dataclass
the model replaces whenever a knob moves, and the first thing an open window does is
move knobs; the block behind it is the same object throughout.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from soundboard.effects.chain import Effect
from soundboard.effects.params import ParamValue
from soundboard.ui.vst_editor_process import VstEditor

if TYPE_CHECKING:  # a cycle otherwise: the model owns one of these
    from soundboard.ui.effects_model import EffectsModel


class RackEditors:
    """Every plugin window this rack has up, at most one per block."""

    def __init__(
        self, model: EffectsModel, command: tuple[str, list[str]] | None = None
    ) -> None:
        self._model = model
        self._command = command
        self._open: dict[Effect, VstEditor] = {}

    def __contains__(self, effect: Effect) -> bool:
        return effect in self._open

    def open(
        self, effect: Effect, path: Path | str, params: Mapping[str, ParamValue]
    ) -> None:
        """Show ``effect``'s own window, or do nothing if it already has one."""
        if effect in self._open:
            return
        # Parented to the model: the window's process is owned by the rack that
        # opened it, and dies with the rack rather than with this bookkeeping.
        editor = VstEditor(self._model, command=self._command)
        self._open[effect] = editor
        editor.changed.connect(lambda moved: self._moved(effect, moved))
        editor.closed.connect(lambda: self._done(effect, ""))
        editor.failed.connect(lambda message: self._done(effect, message))
        editor.open(path, params)

    def close(self, effect: Effect | None) -> None:
        """Take down one block's window, if it has one."""
        editor = self._open.get(effect) if effect is not None else None
        if editor is not None:
            editor.close()

    def close_all(self) -> None:
        """A rack being retired has no business leaving plugin instances running."""
        for editor in list(self._open.values()):
            editor.close()

    def _moved(self, effect: Effect, params: dict[str, ParamValue]) -> None:
        """Knobs the user moved in the plugin's window, on their way to the chain."""
        index = self._model.row_of(effect)
        if index < 0:
            return
        for name, value in params.items():
            try:
                self._model.apply_param(index, name, value)
            except (TypeError, ValueError) as exc:
                # Both instances are the same plugin, so this means one of them is
                # lying about its own parameters. Say so once, rather than let it
                # out of a signal handler as a traceback.
                self._model.toast.emit(f"El plugin devolvió un valor inválido: {exc}")
        self._model.save()

    def _done(self, effect: Effect, message: str) -> None:
        self._open.pop(effect, None)
        if message:
            self._model.toast.emit(f"La ventana del plugin falló: {message}")
        index = self._model.row_of(effect)
        if index >= 0:
            self._model.refresh(index, [self._model.EDITOR_ROLE])
