"""Wires the capture stream, the mixer and the output stream together."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from soundboard.audio.backend import AudioBackend, Stream
from soundboard.audio.drift import DriftController, DriftResampler
from soundboard.audio.mixer import Mixer
from soundboard.audio.ringbuffer import RingBuffer
from soundboard.audio.voice import Voice


@dataclass(frozen=True)
class EngineConfig:
    samplerate: int = 48_000
    blocksize: int = 256
    input_device: int | None = None
    output_device: int | None = None
    output_channels: int = 1
    target_fill_blocks: int = 2
    capacity_blocks: int = 16


@dataclass(frozen=True)
class EngineMetrics:
    underruns: int
    overruns: int
    fill: int
    ratio: float
    active_voices: int


class AudioEngine:
    """Owns the real-time audio path.

    The input callback only writes captured frames into the ring buffer. The
    output callback does everything else: drain pending commands, read the
    microphone bus at the drift-corrected rate, mix, and broadcast to the output
    channels.
    """

    def __init__(self, backend: AudioBackend, config: EngineConfig | None = None) -> None:
        self._backend = backend
        self._config = config or EngineConfig()
        block = self._config.blocksize
        self._target_fill = self._config.target_fill_blocks * block
        self._ring = RingBuffer(self._config.capacity_blocks * block + 1)
        self._controller = DriftController(target_fill=self._target_fill)
        self._resampler = DriftResampler(self._ring, max_block=block)
        self._mixer = Mixer(blocksize=block, samplerate=self._config.samplerate)
        self._mic_block = np.zeros(block, dtype=np.float32)
        self._mix_block = np.zeros(block, dtype=np.float32)
        self._commands: deque[tuple[str, Voice | None]] = deque()
        self._ratio = 1.0
        self._input_stream: Stream | None = None
        self._output_stream: Stream | None = None

    @property
    def mixer(self) -> Mixer:
        return self._mixer

    @property
    def config(self) -> EngineConfig:
        return self._config

    @property
    def metrics(self) -> EngineMetrics:
        return EngineMetrics(
            underruns=self._ring.underruns,
            overruns=self._ring.overruns,
            fill=self._ring.fill,
            ratio=self._ratio,
            active_voices=self._mixer.active_voices,
        )

    def start(self) -> None:
        # Prime the buffer so the first blocks do not underrun and the latency
        # settles immediately at the target instead of drifting up to it.
        self._ring.write(np.zeros(self._target_fill, dtype=np.float32))
        self._input_stream = self._backend.open_input(
            device=self._config.input_device,
            samplerate=self._config.samplerate,
            blocksize=self._config.blocksize,
            callback=self._on_input,
        )
        self._output_stream = self._backend.open_output(
            device=self._config.output_device,
            samplerate=self._config.samplerate,
            blocksize=self._config.blocksize,
            channels=self._config.output_channels,
            callback=self._on_output,
        )
        self._input_stream.start()
        self._output_stream.start()

    def stop(self) -> None:
        for stream in (self._output_stream, self._input_stream):
            if stream is not None:
                stream.stop()
                stream.close()
        self._output_stream = None
        self._input_stream = None

    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        """Queue a clip for playback. Safe to call from any thread."""
        voice = Voice(pcm, gain=gain, loop=loop, start=start, end=end)
        self._commands.append(("play", voice))

    def stop_all(self) -> None:
        """Stop every playing clip. Safe to call from any thread."""
        self._commands.append(("stop_all", None))

    def _on_input(self, block: np.ndarray) -> None:
        self._ring.write(block)

    def _on_output(self, out: np.ndarray) -> None:
        commands = self._commands
        while commands:
            name, voice = commands.popleft()
            if name == "play" and voice is not None:
                self._mixer.add_voice(voice)
            elif name == "stop_all":
                self._mixer.stop_all()

        self._ratio = self._controller.update(self._ring.fill)
        self._resampler.read(self._mic_block, self._ratio)
        self._mixer.process(self._mic_block, self._mix_block)
        out[:] = self._mix_block[:, None]
