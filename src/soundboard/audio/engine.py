"""Wires the capture stream, the mixer and the output stream together."""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass

import numpy as np

from soundboard.audio.backend import AudioBackend, Stream
from soundboard.audio.drift import DriftController, DriftResampler
from soundboard.audio.mixer import Mixer
from soundboard.audio.ringbuffer import RingBuffer
from soundboard.audio.voice import Voice
from soundboard.effects.chain import Effect, EffectChain, ParamChange
from soundboard.effects.params import ParamValue


@dataclass(frozen=True)
class EngineConfig:
    samplerate: int = 48_000
    blocksize: int = 256
    input_device: int | None = None
    output_device: int | None = None
    output_channels: int = 1
    target_fill_blocks: int = 8
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
        self._chain = EffectChain()
        self._commands: deque[tuple[str, Voice | EffectChain | ParamChange | None]] = deque()
        self._retired: deque[EffectChain] = deque()
        self._input_peak = 0.0
        self._chain_peak = 0.0
        self._ratio = 1.0
        self._input_stream: Stream | None = None
        self._output_stream: Stream | None = None
        self._voice_ids = itertools.count(1)

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
        self._input_stream.start()
        try:
            self._output_stream = self._backend.open_output(
                device=self._config.output_device,
                samplerate=self._config.samplerate,
                blocksize=self._config.blocksize,
                channels=self._config.output_channels,
                callback=self._on_output,
            )
            self._output_stream.start()
        except Exception:
            # Do not leave a stream running with nothing to close it: open_output
            # may have succeeded and left self._output_stream assigned even
            # though the failure came from its own .start() call.
            if self._output_stream is not None:
                self._output_stream.stop()
                self._output_stream.close()
                self._output_stream = None
            self._input_stream.stop()
            self._input_stream.close()
            self._input_stream = None
            raise

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
    ) -> int:
        """Queue a clip for playback; returns its voice id. Safe from any thread.

        The id comes from itertools.count, whose next() is a single C call and
        therefore safe under concurrent callers from different threads.
        """
        voice_id = next(self._voice_ids)
        voice = Voice(pcm, gain=gain, loop=loop, start=start, end=end, voice_id=voice_id)
        self._commands.append(("play", voice))
        return voice_id

    def stop_all(self) -> None:
        """Stop every playing clip. Safe to call from any thread."""
        self._commands.append(("stop_all", None))

    def set_chain(self, chain: EffectChain) -> None:
        """Install ``chain`` on the callback thread. Safe to call from any thread.

        The caller builds the replacement whole and hands it over; the callback
        only rebinds a reference, so it never sees a half-built chain.
        """
        self._commands.append(("chain", chain))

    def set_param(self, effect: Effect, name: str, value: ParamValue) -> None:
        """Move one knob on a live block. Safe to call from any thread.

        Queued rather than applied here for the reason ``ParamChange`` gives.
        """
        self._commands.append(("param", ParamChange(effect, name, value)))

    def drain_retired(self) -> list[EffectChain]:
        """Take the chains the callback has swapped out. For the UI thread only.

        Releasing a chain can mean tearing down an ONNX session or a VST3 plugin,
        neither of which may happen on the callback thread; the callback parks
        them here and whoever calls this holds the last reference.
        """
        retired = self._retired
        return [retired.popleft() for _ in range(len(retired))]

    def voice_states(self) -> list[tuple[int, float]]:
        """(voice_id, progress) snapshot; safe to call from the UI thread."""
        return self._mixer.voice_states()

    @property
    def last_peak(self) -> float:
        return self._mixer.last_peak

    @property
    def input_peak(self) -> float:
        """Microphone level before the chain; drives the rack's MIC card."""
        return self._input_peak

    @property
    def chain_peak(self) -> float:
        """Microphone level after the chain; drives the rack's OUT card."""
        return self._chain_peak

    @property
    def chain_latency_ms(self) -> float:
        """Latency of the chain currently running on the callback thread."""
        return self._chain.latency_frames * 1000.0 / self._config.samplerate

    @property
    def chain_cost_ms(self) -> float:
        """Declared processing cost of the enabled blocks in the active chain.

        Cost telemetry is optional because the pedalboard blocks are effectively
        free at this cadence; the neural block reports its measured p99 instead.
        Reading it here keeps timing and allocation out of the callback itself.
        """
        return sum(
            float(getattr(slot.effect, "cost_ms", 0.0))
            for slot in self._chain.slots
            if slot.enabled
        )

    def _on_input(self, block: np.ndarray) -> None:
        self._ring.write(block)

    def _on_output(self, out: np.ndarray) -> None:
        commands = self._commands
        while commands:
            name, payload = commands.popleft()
            if name == "play" and isinstance(payload, Voice):
                self._mixer.add_voice(payload)
            elif name == "stop_all":
                self._mixer.stop_all()
            elif name == "chain" and isinstance(payload, EffectChain):
                self._retired.append(self._chain)
                self._chain = payload
            elif name == "param" and isinstance(payload, ParamChange):
                payload.effect.set_param(payload.name, payload.value)

        self._ratio = self._controller.update(self._ring.fill)
        self._resampler.read(self._mic_block, self._ratio)
        # max/-min instead of max(abs(...)), for the reason Mixer gives: it is the
        # same absolute peak without the temporary array np.abs allocates.
        mic = self._mic_block
        self._input_peak = float(max(mic.max(), -mic.min()))
        self._chain.process(mic)
        self._chain_peak = float(max(mic.max(), -mic.min()))
        self._mixer.process(mic, self._mix_block)
        out[:] = self._mix_block[:, None]
