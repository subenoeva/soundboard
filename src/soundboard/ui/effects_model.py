"""List model behind the QML rack: which blocks the chain holds, in what order."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)

from soundboard.effects.chain import Effect, EffectChain
from soundboard.effects.chain import Slot as ChainSlot
from soundboard.effects.params import ParamValue
from soundboard.effects.realtime_gc import enable as enable_realtime_gc
from soundboard.effects.registry import catalog, create
from soundboard.ui.effect_worker import EffectLoadWorker, load_effect_entry
from soundboard.ui.effects_presenter import adopted, parameter_rows, row_label, summary
from soundboard.ui.effects_store import EffectEntry, LoadedEffect, save_effects


class Engine(Protocol):
    """Chain-only view of the engine, kept narrow so a fake stays small."""

    def set_chain(self, chain: EffectChain) -> None: ...
    def set_param(self, effect: Effect, name: str, value: ParamValue) -> None: ...


class EffectsModel(QAbstractListModel):
    KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    LABEL_ROLE = KIND_ROLE + 1
    ENABLED_ROLE = KIND_ROLE + 2
    SUMMARY_ROLE = KIND_ROLE + 3
    LATENCY_MS_ROLE = KIND_ROLE + 4
    ERROR_ROLE = KIND_ROLE + 5
    LOADING_ROLE = KIND_ROLE + 6

    toast = Signal(str)

    def __init__(
        self,
        engine: Engine,
        rows: Iterable[LoadedEffect],
        path: Path,
        parent: QObject | None = None,
        samplerate: int = 48_000,
        blocksize: int = 256,
        load_effect: Callable[[EffectEntry, int], Effect] | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._rows = [adopted(row) for row in rows]
        self._path = path
        self._samplerate = samplerate
        self._blocksize = blocksize
        self._load_effect = load_effect or load_effect_entry
        self._active_workers: set[EffectLoadWorker] = set()
        self._live = True
        self._push()
        for row in self._rows:
            if row.loading:
                self._start_loading(row)

    @Slot(str)
    def add(self, kind: str) -> None:
        """Append a block from the palette, built with the defaults it declares."""
        if kind == "neural":
            row = LoadedEffect(EffectEntry(kind=kind), loading=True)
            self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
            self._rows.append(row)
            self.endInsertRows()
            self._commit()
            self._start_loading(row)
            return
        try:
            effect = create(kind)
        except KeyError as exc:
            self.toast.emit(f"No se pudo añadir el efecto: {exc.args[0]}")
            return
        entry = EffectEntry(kind=kind, params=effect.params())
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(LoadedEffect(entry, effect=effect))
        self.endInsertRows()
        self._commit()

    @Slot(str)
    def add_vst(self, plugin_path: str) -> None:
        """Append a VST3 path now; the plugin itself is built by the worker."""
        if not plugin_path:
            return
        row = LoadedEffect(
            EffectEntry(kind="vst3", plugin_path=plugin_path), loading=True
        )
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(row)
        self.endInsertRows()
        self._commit()
        self._start_loading(row)

    @Slot(int)
    def remove(self, index: int) -> None:
        if not 0 <= index < len(self._rows):
            return
        self.beginRemoveRows(QModelIndex(), index, index)
        del self._rows[index]
        self.endRemoveRows()
        self._commit()

    @Slot(int, int)
    def move(self, source: int, destination: int) -> None:
        """Drag a block to another position, taking the block itself with it."""
        rows = self._rows
        if not (0 <= source < len(rows) and 0 <= destination < len(rows)):
            return
        # Qt counts the destination among the rows before the move, so a block
        # travelling right lands one past the row it is displacing.
        target = destination + 1 if destination > source else destination
        if not self.beginMoveRows(QModelIndex(), source, source, QModelIndex(), target):
            return
        rows.insert(destination, rows.pop(source))
        self.endMoveRows()
        self._commit()

    @Slot(int, bool)
    def set_enabled(self, index: int, enabled: bool) -> None:
        if not 0 <= index < len(self._rows):
            return
        row = self._rows[index]
        self._rows[index] = replace(row, entry=replace(row.entry, enabled=enabled))
        self._emit_row_changed(index, [self.ENABLED_ROLE])
        self._commit()

    @Slot(int, str, "QVariant")
    def set_param(self, index: int, name: str, value: ParamValue) -> None:
        """Move one knob on the block at ``index``, and remember where it now sits.

        The value is clamped here as well as in the block because this is the copy
        that gets saved: handing the plugin 900 dB and writing 900 dB down would
        give a file that no longer describes what the user is hearing.
        """
        if not 0 <= index < len(self._rows):
            return
        row = self._rows[index]
        if row.effect is None:
            return
        spec = next((s for s in row.effect.param_specs() if s.name == name), None)
        if spec is None:
            return
        value = spec.coerce(value)
        params = {**row.entry.params, name: value}
        self._rows[index] = replace(row, entry=replace(row.entry, params=params))
        self._engine.set_param(row.effect, name, value)
        self._emit_row_changed(index, [self.SUMMARY_ROLE])
        # No new chain: the blocks and their order are what they were, and
        # rebuilding one per slider frame would retire a chain per frame with it.
        save_effects(self._path, [row.entry for row in self._rows])

    @Slot(int, result="QVariantList")
    def param_specs(self, index: int) -> list[dict[str, Any]]:
        """The knobs of one block, as QML can read them, with their positions."""
        if not 0 <= index < len(self._rows):
            return []
        row = self._rows[index]
        if row.effect is None:
            return []
        return parameter_rows(row)

    @Slot(result="QVariantList")
    def catalog(self) -> list[dict[str, str]]:
        """What the palette offers, so QML does not list the blocks a second time."""
        return catalog()

    def detach(self) -> None:
        """Ignore results belonging to a model retired during a device change."""
        self._live = False

    def _start_loading(self, row: LoadedEffect) -> None:
        worker = EffectLoadWorker(lambda: self._load_effect(row.entry, self._blocksize))
        self._active_workers.add(worker)

        def finish(effect: Effect) -> None:
            self._active_workers.discard(worker)
            if not self._live:
                return
            index = next((i for i, current in enumerate(self._rows) if current is row), -1)
            if index < 0:
                return
            if effect.kind == "neural":
                enable_realtime_gc()
            self._rows[index] = adopted(LoadedEffect(row.entry, effect=effect))
            self._emit_row_changed(
                index,
                [
                    self.LABEL_ROLE,
                    self.ENABLED_ROLE,
                    self.SUMMARY_ROLE,
                    self.LATENCY_MS_ROLE,
                    self.ERROR_ROLE,
                    self.LOADING_ROLE,
                ],
            )
            self._push()

        def fail(message: str) -> None:
            self._active_workers.discard(worker)
            if not self._live:
                return
            index = next((i for i, current in enumerate(self._rows) if current is row), -1)
            if index < 0:
                return
            self._rows[index] = LoadedEffect(row.entry, error=message)
            self._emit_row_changed(
                index, [self.ENABLED_ROLE, self.ERROR_ROLE, self.LOADING_ROLE]
            )

        worker.signals.finished.connect(finish)
        worker.signals.failed.connect(fail)
        QThreadPool.globalInstance().start(worker)

    def _emit_row_changed(self, index: int, roles: list[int]) -> None:
        model_index = self.index(index)
        self.dataChanged.emit(model_index, model_index, roles)

    def _commit(self) -> None:
        """Write the rack down and hand the engine the chain it now describes."""
        save_effects(self._path, [row.entry for row in self._rows])
        self._push()

    def _push(self) -> None:
        """Hand the engine a chain of the rows that built, in the order shown."""
        self._engine.set_chain(
            EffectChain(
                ChainSlot(row.effect, row.entry.enabled)
                for row in self._rows
                if row.effect is not None
            )
        )

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent and parent.isValid():
            return 0
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        i = index.row()
        if not 0 <= i < len(self._rows):
            return None
        row = self._rows[i]
        if role == self.KIND_ROLE:
            return row.entry.kind
        if role == self.LABEL_ROLE:
            return row_label(row)
        if role == self.ENABLED_ROLE:
            return row.entry.enabled and row.effect is not None
        if role == self.SUMMARY_ROLE:
            return summary(row)
        if role == self.LATENCY_MS_ROLE:
            frames = row.effect.latency_frames if row.effect else 0
            return frames * 1000.0 / self._samplerate
        if role == self.ERROR_ROLE:
            return row.error or ""
        if role == self.LOADING_ROLE:
            return row.loading
        return None

    def roleNames(self) -> dict[int, bytes]:  # type: ignore[override]
        return {
            self.KIND_ROLE: b"kind",
            self.LABEL_ROLE: b"label",
            self.ENABLED_ROLE: b"enabled",
            self.SUMMARY_ROLE: b"summary",
            self.LATENCY_MS_ROLE: b"latencyMs",
            self.ERROR_ROLE: b"errorText",
            self.LOADING_ROLE: b"loading",
        }
