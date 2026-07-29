"""In-memory audio backend with a simulated clock, for tests."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from soundboard.audio.backend import DeviceInfo, InputCallback, OutputCallback

_DEFAULT_DEVICES = [
    DeviceInfo(0, "Fake Microphone", "fake", 1, 0, 48_000.0),
    DeviceInfo(1, "Fake Cable", "fake", 0, 2, 48_000.0),
]


class FakeStream:
    def __init__(self, backend: FakeBackend, is_input: bool, blocksize: int, channels: int,
                 callback: Callable[[np.ndarray], None]) -> None:
        self.backend = backend
        self.is_input = is_input
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.started = False
        self.closed = True
        if self in self.backend.streams:
            self.backend.streams.remove(self)


class FakeBackend:
    """Drives audio callbacks deterministically from the calling thread.

    ``advance(n)`` simulates ``n`` block periods. Input streams always run before
    output streams within a block, matching the real ordering closely enough for
    the engine's ring buffer accounting to behave the same way.
    """

    def __init__(self, devices: list[DeviceInfo] | None = None) -> None:
        self._devices = list(devices) if devices is not None else list(_DEFAULT_DEVICES)
        self.streams: list[FakeStream] = []
        self.input_source: Callable[[int], np.ndarray] | None = None
        self.captured: list[np.ndarray] = []

    def list_devices(self) -> list[DeviceInfo]:
        return list(self._devices)

    def open_input(self, *, device: int | None, samplerate: int, blocksize: int,
                   callback: InputCallback) -> FakeStream:
        stream = FakeStream(self, True, blocksize, 1, callback)
        self.streams.append(stream)
        return stream

    def open_output(self, *, device: int | None, samplerate: int, blocksize: int,
                    channels: int, callback: OutputCallback) -> FakeStream:
        stream = FakeStream(self, False, blocksize, channels, callback)
        self.streams.append(stream)
        return stream

    def advance(self, blocks: int = 1) -> None:
        for _ in range(blocks):
            for stream in [s for s in self.streams if s.is_input and s.started]:
                source = self.input_source
                block = (
                    source(stream.blocksize)
                    if source is not None
                    else np.zeros(stream.blocksize, dtype=np.float32)
                )
                stream.callback(block)
            for stream in [s for s in self.streams if not s.is_input and s.started]:
                out = np.zeros((stream.blocksize, stream.channels), dtype=np.float32)
                stream.callback(out)
                self.captured.append(out)
