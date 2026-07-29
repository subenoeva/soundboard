"""Audio backend abstraction.

Keeping PortAudio behind a protocol is what makes the engine testable: the whole
mixing path can run against an in-memory backend with a simulated clock, in CI,
with no sound card present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

InputCallback = Callable[[np.ndarray], None]
"""Receives a ``(frames,)`` mono float32 block of captured audio."""

OutputCallback = Callable[[np.ndarray], None]
"""Receives a ``(frames, channels)`` float32 block to fill in place."""


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


class Stream(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class AudioBackend(Protocol):
    xruns: int
    """Driver-reported overflow/underflow count, at the device boundary.

    Distinct from ``RingBuffer.overruns``/``underruns``, which only see the
    engine's internal buffer state, not what the driver itself reports.
    """

    def list_devices(self) -> list[DeviceInfo]: ...

    def open_input(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        callback: InputCallback,
    ) -> Stream: ...

    def open_output(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        channels: int,
        callback: OutputCallback,
    ) -> Stream: ...
