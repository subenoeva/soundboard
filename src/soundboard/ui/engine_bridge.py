"""Polls the audio engine and republishes peak/metrics/voice progress for the UI."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from soundboard.audio.engine import EngineMetrics
from soundboard.effects.chain import EffectChain
from soundboard.effects.realtime_gc import collect as collect_realtime_garbage
from soundboard.effects.realtime_gc import restore as restore_realtime_garbage


class MeteredEngine(Protocol):
    @property
    def last_peak(self) -> float: ...
    @property
    def input_peak(self) -> float: ...
    @property
    def chain_peak(self) -> float: ...
    @property
    def chain_latency_ms(self) -> float: ...
    @property
    def chain_cost_ms(self) -> float: ...
    @property
    def metrics(self) -> EngineMetrics: ...
    def voice_states(self) -> list[tuple[int, float]]: ...
    def drain_retired(self) -> list[EffectChain]: ...


class EngineBridge(QObject):
    peakChanged = Signal()
    metricsChanged = Signal()
    rackMetricsChanged = Signal()
    voice_states_updated = Signal(object)

    def __init__(
        self, engine: MeteredEngine, parent: QObject | None = None, interval_ms: int = 33
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._peak = 0.0
        self._rack_metrics = (0.0, 0.0, 0.0, 0.0)
        self._metrics_text = ""
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        restore_realtime_garbage()

    @Slot()
    def poll(self) -> None:
        peak = float(self._engine.last_peak)
        if peak != self._peak:
            self._peak = peak
            self.peakChanged.emit()
        rack_metrics = (
            float(self._engine.input_peak),
            float(self._engine.chain_peak),
            float(self._engine.chain_latency_ms),
            float(self._engine.chain_cost_ms),
        )
        if rack_metrics != self._rack_metrics:
            self._rack_metrics = rack_metrics
            self.rackMetricsChanged.emit()
        self.voice_states_updated.emit(self._engine.voice_states())
        m = self._engine.metrics
        text = f"underruns {m.underruns} · fill {m.fill} · voces {m.active_voices}"
        if text != self._metrics_text:
            self._metrics_text = text
            self.metricsChanged.emit()
        self._engine.drain_retired()
        collect_realtime_garbage()

    def _get_peak(self) -> float:
        return self._peak

    def _get_metrics_text(self) -> str:
        return self._metrics_text

    def _get_input_peak(self) -> float:
        return self._rack_metrics[0]

    def _get_chain_peak(self) -> float:
        return self._rack_metrics[1]

    def _get_chain_latency_ms(self) -> float:
        return self._rack_metrics[2]

    def _get_chain_cost_ms(self) -> float:
        return self._rack_metrics[3]

    peak = Property(float, _get_peak, notify=peakChanged)
    metricsText = Property(str, _get_metrics_text, notify=metricsChanged)
    inputPeak = Property(float, _get_input_peak, notify=rackMetricsChanged)
    chainPeak = Property(float, _get_chain_peak, notify=rackMetricsChanged)
    chainLatencyMs = Property(float, _get_chain_latency_ms, notify=rackMetricsChanged)
    chainCostMs = Property(float, _get_chain_cost_ms, notify=rackMetricsChanged)
