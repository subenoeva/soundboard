"""EngineBridge polls the engine and republishes UI-friendly state."""

from __future__ import annotations

from soundboard.audio.engine import EngineMetrics
from soundboard.effects.chain import EffectChain
from soundboard.ui.engine_bridge import EngineBridge


class FakeEngine:
    def __init__(self) -> None:
        self.last_peak = 0.0
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
