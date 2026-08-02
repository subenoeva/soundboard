"""Default engine factory and the session-store protocol `AppController` depends on.

Split out of `controller.py` to keep that file within its line budget: this holds
the concrete "resolve devices and start a real `AudioEngine`" plumbing (parallel to
how `portaudio.py` holds the real `AudioBackend` beside its protocol) plus the small
structural types `AppController` needs but that `auth.py`/`client.py` don't expose
as protocols themselves.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from soundboard.audio.backend import AudioBackend
from soundboard.audio.engine import AudioEngine, EngineConfig, EngineMetrics
from soundboard.audio.portaudio import find_device
from soundboard.effects.chain import EffectChain
from soundboard.remote.models import Session
from soundboard.ui.layout_store import GridLayout


class Engine(Protocol):
    """Union of what `GridModel` and `EngineBridge` each need from the engine.

    The wide one: `grid_model.Engine` is the narrow playback-only view of the same
    object. A real `AudioEngine` satisfies both.
    """

    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> int: ...
    def stop_all(self) -> None: ...
    def stop(self) -> None: ...
    def voice_states(self) -> list[tuple[int, float]]: ...
    def drain_retired(self) -> list[EffectChain]: ...

    @property
    def last_peak(self) -> float: ...

    @property
    def metrics(self) -> EngineMetrics: ...


class Store(Protocol):
    """Structural stand-in for `remote.client.SessionStore` (and its test double)."""

    def load(self) -> Session | None: ...
    def save(self, session: Session) -> None: ...
    def clear(self) -> None: ...


def build_engine(backend: AudioBackend, layout: GridLayout) -> AudioEngine:
    """Default `engine_factory`: resolve devices and start the engine.

    One attempt, no retry loop: the caller (`AppController`) turns a failure into
    `setupError` and keeps the view on "setup" so QML can offer its own retry via
    `apply_devices`.
    """
    devices = backend.list_devices()
    microphone = find_device(devices, layout.mic, want_input=True)
    cable = find_device(devices, layout.out, want_input=False)
    engine = AudioEngine(
        backend,
        EngineConfig(
            blocksize=layout.blocksize,
            input_device=microphone.index,
            output_device=cable.index,
            output_channels=min(2, cable.max_output_channels) or 1,
        ),
    )
    engine.start()
    return engine
