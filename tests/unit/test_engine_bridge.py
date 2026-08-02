"""EngineBridge polls the engine and republishes UI-friendly state."""

from __future__ import annotations

from soundboard.audio.engine import EngineMetrics
from soundboard.effects.chain import EffectChain
from soundboard.ui.engine_bridge import EngineBridge


class FakeEngine:
    def __init__(self) -> None:
        self.last_peak = 0.0
        self.input_peak = 0.0
        self.chain_peak = 0.0
        self.chain_latency_ms = 0.0
        self.chain_cost_ms = 0.0
        self.states: list[tuple[int, float]] = []
        self.retired: list[EffectChain] = []

    def voice_states(self) -> list[tuple[int, float]]:
        return self.states

    def drain_retired(self) -> list[EffectChain]:
        retired = self.retired[:]
        self.retired.clear()
        return retired

    @property
    def metrics(self) -> EngineMetrics:
        return EngineMetrics(underruns=1, overruns=0, fill=512, ratio=1.0,
                             active_voices=len(self.states))


def test_poll_publishes_peak_and_metrics(qtbot: object) -> None:
    engine = FakeEngine()
    bridge = EngineBridge(engine)
    engine.last_peak = 0.5
    engine.states = [(1, 0.25)]
    received: list[object] = []
    bridge.voice_states_updated.connect(received.append)
    bridge.poll()
    assert bridge.peak == 0.5  # type: ignore[comparison-overlap]
    assert "underruns 1" in bridge.metricsText  # type: ignore[operator]
    assert received == [[(1, 0.25)]]


def test_peak_changed_only_fires_on_change(qtbot: object) -> None:
    engine = FakeEngine()
    bridge = EngineBridge(engine)
    fired: list[bool] = []
    bridge.peakChanged.connect(lambda: fired.append(True))
    bridge.poll()
    bridge.poll()
    assert fired == []  # 0.0 → 0.0: unchanged, so no signal
    engine.last_peak = 0.3
    bridge.poll()
    assert len(fired) == 1


def test_poll_drains_retired_chains(qtbot: object) -> None:
    engine = FakeEngine()
    bridge = EngineBridge(engine)
    engine.retired.append(EffectChain())

    bridge.poll()

    assert engine.retired == []


def test_poll_publishes_the_effects_rack_metrics(qtbot: object) -> None:
    engine = FakeEngine()
    bridge = EngineBridge(engine)
    engine.input_peak = 0.2
    engine.chain_peak = 0.1
    engine.chain_latency_ms = 20.0
    engine.chain_cost_ms = 1.25

    bridge.poll()

    assert bridge.inputPeak == 0.2  # type: ignore[comparison-overlap]
    assert bridge.chainPeak == 0.1  # type: ignore[comparison-overlap]
    assert bridge.chainLatencyMs == 20.0  # type: ignore[comparison-overlap]
    assert bridge.chainCostMs == 1.25  # type: ignore[comparison-overlap]
