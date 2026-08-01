"""The ordered list of effects the microphone bus runs through."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Effect(Protocol):
    """One block in the chain.

    ``process`` is in place and must return the same number of frames it was
    given, on every call: the engine hands it the same preallocated buffer the
    mixer will read, so an effect that needs to buffer internally (the neural
    block does) owns that problem rather than passing it upstream.

    ``params``/``set_param`` are here rather than on the concrete blocks because
    persistence and the parameter panel address every block the same way, whether
    it is a pedalboard plugin, a VST3 nobody here has seen, or the neural block
    and its dry/wet control.
    """

    kind: str

    def process(self, block: np.ndarray) -> None: ...

    def reset(self) -> None: ...

    def set_param(self, name: str, value: float) -> None: ...

    def params(self) -> dict[str, float]: ...

    @property
    def latency_frames(self) -> int: ...


@dataclass(frozen=True)
class Slot:
    """One position in the chain: an effect plus whether it is switched on.

    The flag lives here rather than on the effect because an effect is reused by
    identity across chain rebuilds -- bypassing a block must not disturb the
    state (FIFO contents, reverb tail) it carries.
    """

    effect: Effect
    enabled: bool = True


class EffectChain:
    """Runs its enabled effects in order, in place, on the callback thread."""

    def __init__(self, slots: Sequence[Effect | Slot] | Iterable[Effect | Slot] = ()) -> None:
        self._slots: tuple[Slot, ...] = tuple(
            slot if isinstance(slot, Slot) else Slot(slot) for slot in slots
        )

    @property
    def slots(self) -> tuple[Slot, ...]:
        return self._slots

    @property
    def latency_frames(self) -> int:
        return sum(slot.effect.latency_frames for slot in self._slots if slot.enabled)

    def process(self, block: np.ndarray) -> None:
        for slot in self._slots:
            if slot.enabled:
                slot.effect.process(block)

    def reset(self) -> None:
        """Drop the state every effect carries. Not for the callback thread."""
        for slot in self._slots:
            slot.effect.reset()
