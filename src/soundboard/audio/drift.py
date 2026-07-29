"""Clock-drift compensation between two independent audio devices.

The microphone and the virtual cable are driven by different oscillators. A
typical 10-100 ppm deviation means one frame gained or lost every few seconds,
which is audible as a click. ``DriftController`` watches how full the bridging
ring buffer is and asks for a slightly different read rate; ``DriftResampler``
applies that rate with a fractional read position.
"""

from __future__ import annotations

import numpy as np

from soundboard.audio.ringbuffer import RingBuffer


class DriftController:
    """Proportional controller over the ring buffer fill level."""

    def __init__(
        self,
        target_fill: int,
        alpha: float = 0.005,
        gain: float = 0.05,
        max_deviation: float = 0.005,
    ) -> None:
        if target_fill <= 0:
            raise ValueError("target_fill must be positive")
        self._target = float(target_fill)
        self._alpha = alpha
        self._gain = gain
        self._max_deviation = max_deviation
        self._ema = float(target_fill)

    @property
    def ema_fill(self) -> float:
        """Smoothed estimate of the ring buffer fill level, in frames."""
        return self._ema

    def update(self, fill: int) -> float:
        """Feed the current fill level and get the read ratio to apply."""
        self._ema += self._alpha * (fill - self._ema)
        error = (self._ema - self._target) / self._target
        ratio = 1.0 + self._gain * error
        low = 1.0 - self._max_deviation
        high = 1.0 + self._max_deviation
        return min(max(ratio, low), high)


class DriftResampler:
    """Pulls frames from a ring buffer at a fractionally variable rate.

    ``ratio`` is input frames consumed per output frame produced. Neighbouring
    input samples are linearly interpolated; at the +-0.5% deviations this is used
    for, that is a sub-sample fractional delay whose distortion sits far below the
    noise floor of any microphone.
    """

    _MAX_RATIO = 1.02

    def __init__(self, source: RingBuffer, max_block: int) -> None:
        self._source = source
        self._phase = 0.0
        self._history = np.zeros(2, dtype=np.float32)
        self._history_len = 0
        span = int(max_block * self._MAX_RATIO) + 4
        self._buffer = np.zeros(span, dtype=np.float32)
        self._grid = np.arange(span, dtype=np.float64)
        self._ramp = np.arange(max_block, dtype=np.float64)
        self._positions = np.zeros(max_block, dtype=np.float64)

    def read(self, out: np.ndarray, ratio: float) -> None:
        """Fill ``out`` with ``len(out)`` frames read at the given ratio."""
        n = out.shape[0]
        positions = self._positions[:n]
        np.multiply(self._ramp[:n], ratio, out=positions)
        positions += self._phase

        # Highest input index the interpolation will touch, plus its partner.
        span = int(positions[n - 1]) + 2
        window = self._buffer[:span]
        kept = self._history_len
        window[:kept] = self._history[:kept]
        self._source.read(window[kept:])

        # np.interp allocates its result; there is no out= parameter. One small
        # array per block is the single unavoidable allocation in this path.
        out[:] = np.interp(positions, self._grid[:span], window)

        advance = self._phase + n * ratio
        consumed = int(advance)
        self._phase = advance - consumed
        kept = max(span - consumed, 0)
        self._history_len = kept
        self._history[:kept] = window[consumed : consumed + kept]
