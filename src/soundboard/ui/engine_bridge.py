"""Polls the audio engine and republishes peak/metrics/voice progress for the UI."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from soundboard.audio.engine import EngineMetrics


class MeteredEngine(Protocol):
    @property
    def last_peak(self) -> float: ...
    @property
    def metrics(self) -> EngineMetrics: ...
    def voice_states(self) -> list[tuple[int, float]]: ...


class EngineBridge(QObject):
    peakChanged = Signal()
    metricsChanged = Signal()
    voice_states_updated = Signal(object)

    def __init__(
        self, engine: MeteredEngine, parent: QObject | None = None, interval_ms: int = 33
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._peak = 0.0
        self._metrics_text = ""
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @Slot()
    def poll(self) -> None:
        peak = float(self._engine.last_peak)
        if peak != self._peak:
            self._peak = peak
            self.peakChanged.emit()
        self.voice_states_updated.emit(self._engine.voice_states())
        m = self._engine.metrics
        text = f"underruns {m.underruns} · fill {m.fill} · voces {m.active_voices}"
        if text != self._metrics_text:
            self._metrics_text = text
            self.metricsChanged.emit()

    def _get_peak(self) -> float:
        return self._peak

    def _get_metrics_text(self) -> str:
        return self._metrics_text

    peak = Property(float, _get_peak, notify=peakChanged)
    metricsText = Property(str, _get_metrics_text, notify=metricsChanged)
