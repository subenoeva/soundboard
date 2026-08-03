"""The streaming adapter between fixed engine blocks and DPDFNet model frames."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from soundboard.effects.neural import NeuralEffect, RuntimeModel


class FakeSession:
    """A deterministic stand-in for the stateful ONNX boundary."""

    def __init__(self, *, silent: bool = False) -> None:
        self.silent = silent
        self.states_seen: list[float] = []

    def run(
        self, output_names: list[str], inputs: dict[str, np.ndarray]
    ) -> list[np.ndarray]:
        assert output_names == ["enhanced", "next_state"]
        self.states_seen.append(float(inputs["state"][0]))
        enhanced = inputs["spec"].copy()
        if self.silent:
            enhanced.fill(0.0)
        return [enhanced, inputs["state"] + 1.0]


def _runtime(session: FakeSession) -> RuntimeModel:
    return RuntimeModel(
        session=session,
        initial_state=np.zeros(1, dtype=np.float32),
        input_spec_name="spec",
        input_state_name="state",
        output_spec_name="enhanced",
        output_state_name="next_state",
    )


def test_the_adapter_reports_the_prefill_as_latency() -> None:
    effect = NeuralEffect(_runtime(FakeSession()), blocksize=256)

    assert effect.latency_frames == 960


def test_dry_audio_is_delayed_to_stay_aligned_with_the_model_output() -> None:
    effect = NeuralEffect(_runtime(FakeSession(silent=True)), blocksize=256)
    effect.set_param("mix", 0.0)
    source = np.linspace(-0.8, 0.8, 256 * 12, dtype=np.float32)
    rendered = np.empty_like(source)

    for start in range(0, source.size, 256):
        block = source[start : start + 256].copy()
        effect.process(block)
        rendered[start : start + 256] = block

    expected = np.concatenate((np.zeros(960, dtype=np.float32), source[:-960]))
    assert np.array_equal(rendered, expected)


def test_model_state_is_carried_from_one_inference_to_the_next() -> None:
    session = FakeSession()
    effect = NeuralEffect(_runtime(session), blocksize=256)

    for _ in range(8):
        effect.process(np.zeros(256, dtype=np.float32))

    assert session.states_seen[:3] == [0.0, 1.0, 2.0]


def test_the_output_fifo_never_runs_short_at_the_engine_cadence() -> None:
    effect = NeuralEffect(_runtime(FakeSession()), blocksize=256)
    block = np.linspace(-0.25, 0.25, 256, dtype=np.float32)

    for _ in range(500):
        current = block.copy()
        effect.process(current)
        assert current.shape == (256,)
        assert np.all(np.isfinite(current))


@pytest.mark.parametrize("blocksize", [64, 481])
def test_a_blocksize_the_inline_model_cannot_serve_is_rejected(blocksize: int) -> None:
    with pytest.raises(ValueError, match="blocksize"):
        NeuralEffect(_runtime(FakeSession()), blocksize=blocksize)


def test_reset_restores_the_latency_prefill_and_model_state() -> None:
    session = FakeSession(silent=True)
    effect = NeuralEffect(_runtime(session), blocksize=256)
    effect.set_param("mix", 0.0)
    for _ in range(8):
        effect.process(np.ones(256, dtype=np.float32))

    effect.reset()
    block = np.ones(256, dtype=np.float32)
    effect.process(block)

    assert np.array_equal(block, np.zeros(256, dtype=np.float32))
    for _ in range(3):
        effect.process(np.ones(256, dtype=np.float32))
    assert session.states_seen[-1] == 0.0


@dataclass
class FakeClock:
    values: list[int]

    def __call__(self) -> int:
        return self.values.pop(0)


def test_processing_cost_reports_the_observed_p99() -> None:
    clock = FakeClock([0, 1_000_000, 2_000_000, 4_000_000])
    effect = NeuralEffect(_runtime(FakeSession()), blocksize=480, clock_ns=clock)

    effect.process(np.zeros(480, dtype=np.float32))
    effect.process(np.zeros(480, dtype=np.float32))
    effect.process(np.zeros(480, dtype=np.float32))

    assert effect.cost_ms == pytest.approx(1.99)


def test_loading_from_a_missing_model_is_visible() -> None:
    from soundboard.effects.neural import load_neural

    with pytest.raises(FileNotFoundError, match="ONNX model"):
        load_neural(Path("missing.onnx"), blocksize=256)
