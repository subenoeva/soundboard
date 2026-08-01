"""Wraps a pedalboard plugin so the chain can drive it."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from pedalboard import Plugin

from soundboard.effects.params import ParamSpec


class PedalEffect:
    """One pedalboard plugin behind the ``Effect`` protocol.

    Holds no audio state of its own: the plugin keeps its own filter histories and
    envelopes, which is why ``process`` passes ``reset=False`` and why ``reset``
    has anything to delegate.
    """

    def __init__(
        self,
        kind: str,
        plugin: Plugin,
        specs: Iterable[ParamSpec] = (),
        *,
        samplerate: int = 48_000,
    ) -> None:
        self.kind = kind
        self._plugin = plugin
        self._specs = {spec.name: spec for spec in specs}
        self._samplerate = samplerate

    def process(self, block: np.ndarray) -> None:
        block[:] = self._plugin.process(block, self._samplerate, reset=False)

    def reset(self) -> None:
        self._plugin.reset()

    def set_param(self, name: str, value: float) -> None:
        """Move one knob. Call it from the Qt thread, never from the callback."""
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"{self.kind!r} has no parameter {name!r}")
        setattr(self._plugin, name, spec.clamp(value))

    def params(self) -> dict[str, float]:
        """Every knob's current position, read off the plugin, for persistence."""
        return {name: float(getattr(self._plugin, name)) for name in self._specs}

    @property
    def latency_frames(self) -> int:
        """Always zero: pedalboard's built-ins do not delay the signal.

        Reverb is the one that looks like an exception -- it reports 25 ms -- but
        that is pre-delay on the wet signal and the dry path is unshifted, so an
        impulse still leaves the chain at sample 0. Plugins that really do delay
        report it themselves; that is ``vst.py``'s problem, not this one's.
        """
        return 0
