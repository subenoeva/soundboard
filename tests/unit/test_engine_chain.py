"""The effects chain inside the engine: insertion, swapping, retirement, meters."""

from __future__ import annotations

import numpy as np
import pytest

from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.fake_backend import FakeBackend
from soundboard.effects.chain import EffectChain
from soundboard.effects.params import ParamSpec


class ConstantEffect:
    """Writes a fixed value over every frame, so the block it ran on is obvious."""

    kind = "constant"

    def __init__(
        self, value: float, *, latency_frames: int = 0, cost_ms: float = 0.0
    ) -> None:
        self._value = value
        self._latency_frames = latency_frames
        self.cost_ms = cost_ms
        self.calls = 0

    def process(self, block: np.ndarray) -> None:
        self.calls += 1
        block[:] = self._value

    def reset(self) -> None:
        pass

    def set_param(self, name: str, value: float) -> None:
        self._value = value

    def params(self) -> dict[str, float]:
        return {"value": self._value}

    def param_specs(self) -> tuple[ParamSpec, ...]:
        return (ParamSpec("value", "Value", 0.0, 1.0, 0.0),)

    @property
    def latency_frames(self) -> int:
        return self._latency_frames


def _running_engine() -> tuple[AudioEngine, FakeBackend]:
    backend = FakeBackend()
    engine = AudioEngine(backend, EngineConfig(blocksize=64))
    engine.start()
    return engine, backend


def test_the_chain_runs_on_the_microphone_bus() -> None:
    engine, backend = _running_engine()
    engine.set_chain(EffectChain([ConstantEffect(0.1)]))

    backend.advance(2)

    # The mic bus is silent here (the ring is primed with zeros), so anything
    # non-zero at the output can only have come from the chain. The level is kept
    # low so the mixer's soft limiter barely bends it and the value stays legible.
    assert np.allclose(backend.captured[-1], 0.1, atol=0.005)
    engine.stop()


def test_nothing_is_retired_before_the_callback_has_run() -> None:
    engine, backend = _running_engine()
    engine.set_chain(EffectChain([ConstantEffect(0.1)]))
    backend.advance(1)
    engine.drain_retired()

    engine.set_chain(EffectChain([ConstantEffect(0.2)]))

    # The swap is a queued command, not a mutation from the calling thread: until
    # the callback has drained the queue the old chain is still the live one and
    # dropping it would free objects the audio thread is about to use.
    assert engine.drain_retired() == []
    engine.stop()


def test_the_replaced_chain_is_handed_back_once_the_swap_has_happened() -> None:
    engine, backend = _running_engine()
    first = EffectChain([ConstantEffect(0.1)])
    engine.set_chain(first)
    backend.advance(1)
    engine.drain_retired()

    engine.set_chain(EffectChain([ConstantEffect(0.2)]))
    backend.advance(1)

    # pedalboard plugins and ONNX sessions must be released by the UI thread, so
    # the callback pushes the outgoing chain out rather than dropping the last
    # reference to it itself.
    assert engine.drain_retired() == [first]
    assert engine.drain_retired() == []
    engine.stop()


def test_a_parameter_change_waits_for_the_callback() -> None:
    engine, backend = _running_engine()
    effect = ConstantEffect(0.1)
    engine.set_chain(EffectChain([effect]))
    backend.advance(1)

    engine.set_param(effect, "value", 0.2)

    # Reaching into a live plugin from the calling thread while the callback is
    # inside process() is concurrency pedalboard does not document, so a knob
    # move rides the same deque the chain swap does and lands between blocks.
    assert effect.params() == {"value": 0.1}
    backend.advance(1)
    assert effect.params() == {"value": 0.2}
    engine.stop()


def test_the_peaks_bracket_the_chain() -> None:
    engine, backend = _running_engine()
    backend.input_source = lambda frames: np.full(frames, -0.2, dtype=np.float32)
    engine.set_chain(EffectChain([ConstantEffect(0.05)]))

    # Enough blocks for the primed silence to drain out of the ring buffer and
    # the microphone signal to reach the callback.
    backend.advance(8)

    # These two drive the MIC and OUT cards at the ends of the rack, so they have
    # to sit on opposite sides of the chain -- and the negative input proves the
    # peak is an absolute value, not a maximum.
    assert engine.input_peak == pytest.approx(0.2, abs=0.01)
    assert engine.chain_peak == pytest.approx(0.05, abs=0.01)
    engine.stop()


def test_the_active_chain_reports_its_latency_and_declared_cost() -> None:
    engine, backend = _running_engine()
    effect = ConstantEffect(0.1, latency_frames=960, cost_ms=1.25)
    engine.set_chain(EffectChain([effect]))

    backend.advance(1)

    assert engine.chain_latency_ms == 20.0
    assert engine.chain_cost_ms == 1.25
    engine.stop()
