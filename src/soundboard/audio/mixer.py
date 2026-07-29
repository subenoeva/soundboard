"""Mixes the microphone bus with the active clip voices."""

from __future__ import annotations

import math

import numpy as np

from soundboard.audio.voice import Voice

CEILING = 10.0 ** (-1.0 / 20.0)
"""Soft-clip ceiling, -1 dBFS."""


class Mixer:
    """Sums voices onto the microphone bus, with ducking and a soft limiter.

    Ducking is evaluated once per block rather than per sample. At 256 frames a
    block is 5.3 ms, an order of magnitude shorter than the attack time, so the
    extra resolution would buy nothing.
    """

    def __init__(
        self,
        blocksize: int,
        samplerate: int = 48_000,
        duck_db: float = -12.0,
        attack_ms: float = 10.0,
        release_ms: float = 300.0,
        duck_threshold: float = 0.01,
    ) -> None:
        self._sounds = np.zeros(blocksize, dtype=np.float32)
        self._voices: list[Voice] = []
        self._duck_floor = 10.0 ** (duck_db / 20.0)
        self._duck_gain = 1.0
        self._attack = math.exp(-1000.0 / (samplerate * attack_ms))
        self._release = math.exp(-1000.0 / (samplerate * release_ms))
        self._threshold = duck_threshold
        self.output_gain = 1.0
        self.ducking_enabled = True

    @property
    def active_voices(self) -> int:
        return len(self._voices)

    def add_voice(self, voice: Voice) -> None:
        self._voices.append(voice)

    def stop_all(self) -> None:
        self._voices.clear()

    def process(self, mic: np.ndarray, out: np.ndarray) -> None:
        """Render one block: ``out = limit((mic * duck) + sounds)``."""
        sounds = self._sounds
        sounds[:] = 0.0
        for voice in self._voices:
            voice.mix_into(sounds)
        if any(voice.finished for voice in self._voices):
            # Rebuilding the list allocates; it only happens on the blocks where a
            # clip actually ends, not on every block.
            self._voices = [voice for voice in self._voices if not voice.finished]

        loud = self.ducking_enabled and bool(np.max(np.abs(sounds)) > self._threshold)
        target = self._duck_floor if loud else 1.0
        coefficient = self._attack if target < self._duck_gain else self._release
        self._duck_gain = target + (self._duck_gain - target) * coefficient ** out.shape[0]

        np.multiply(mic, self._duck_gain, out=out)
        np.add(out, sounds, out=out)
        np.multiply(out, self.output_gain, out=out)
        np.divide(out, CEILING, out=out)
        np.tanh(out, out=out)
        np.multiply(out, CEILING, out=out)
