from collections.abc import Callable

import numpy as np

from soundboard.effects.chain import EffectChain, Slot
from soundboard.effects.params import ParamSpec, ParamValue


class FakeEffect:
    """Test double: applies ``op`` in place and counts its calls.

    Keeps the chain tests independent of pedalboard and of the ONNX model, which
    is the whole reason ``Effect`` is a protocol rather than a base class.
    """

    def __init__(
        self,
        op: Callable[[np.ndarray], None],
        *,
        kind: str = "fake",
        latency_frames: int = 0,
    ) -> None:
        self.kind = kind
        self._op = op
        self._latency_frames = latency_frames
        self._params: dict[str, ParamValue] = {}
        self.calls = 0
        self.resets = 0

    def process(self, block: np.ndarray) -> None:
        self.calls += 1
        self._op(block)

    def reset(self) -> None:
        self.resets += 1

    def set_param(self, name: str, value: ParamValue) -> None:
        self._params[name] = value

    def params(self) -> dict[str, ParamValue]:
        return dict(self._params)

    def param_specs(self) -> tuple[ParamSpec, ...]:
        return ()

    @property
    def latency_frames(self) -> int:
        return self._latency_frames


def scale(factor: float) -> FakeEffect:
    return FakeEffect(lambda block: np.multiply(block, factor, out=block))


def offset(amount: float) -> FakeEffect:
    return FakeEffect(lambda block: np.add(block, amount, out=block))


def test_applies_effects_in_order() -> None:
    chain = EffectChain([scale(2.0), offset(1.0)])
    block = np.ones(4, dtype=np.float32)

    chain.process(block)

    # Order matters: scale-then-offset is 3.0, offset-then-scale would be 4.0.
    assert np.allclose(block, 3.0)


def test_a_bypassed_effect_is_not_called_at_all() -> None:
    muted = scale(0.0)
    chain = EffectChain([Slot(muted, enabled=False), Slot(offset(1.0))])
    block = np.ones(4, dtype=np.float32)

    chain.process(block)

    assert np.allclose(block, 2.0)
    # Skipped, not called-and-ignored: a bypassed neural block must not spend its
    # 2 ms of inference, which is the entire point of the switch.
    assert muted.calls == 0


def test_latency_is_the_sum_of_the_enabled_effects() -> None:
    chain = EffectChain(
        [
            FakeEffect(lambda block: None, latency_frames=960),
            Slot(FakeEffect(lambda block: None, latency_frames=128), enabled=False),
            FakeEffect(lambda block: None, latency_frames=64),
        ]
    )

    # A bypassed block delays nothing, so it must not be counted; the figure ends
    # up in front of the user as chainLatencyMs.
    assert chain.latency_frames == 1024


def test_reset_reaches_bypassed_effects_too() -> None:
    running = scale(1.0)
    bypassed = scale(1.0)
    chain = EffectChain([running, Slot(bypassed, enabled=False)])

    chain.reset()

    # A bypassed block still holds state -- a FIFO, a reverb tail -- and reset()
    # exists for the moments (device change, stream restart) where none of it is
    # valid any more.
    assert (running.resets, bypassed.resets) == (1, 1)


def test_an_empty_chain_leaves_the_block_untouched() -> None:
    block = np.array([0.5, -0.25, 0.0, 1.0], dtype=np.float32)
    original = block.copy()

    EffectChain().process(block)

    # The engine holds an empty chain whenever the user has configured nothing,
    # so this is the common path, not an edge case.
    assert np.array_equal(block, original)


def test_process_writes_into_the_caller_s_buffer() -> None:
    chain = EffectChain([offset(1.0)])
    block = np.zeros(4, dtype=np.float32)
    view = block[:2]

    chain.process(block)

    # The engine passes the same preallocated buffer the mixer reads next, so an
    # effect that rebinds instead of writing in place would silently do nothing.
    assert np.allclose(view, 1.0)
