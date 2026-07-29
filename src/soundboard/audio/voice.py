"""A single clip playback in progress."""

from __future__ import annotations

import numpy as np


class Voice:
    """One playing clip: position, gain, looping and trim range.

    ``mix_into`` adds onto the destination block rather than overwriting it, so
    several voices can share one buffer.
    """

    def __init__(
        self,
        pcm: np.ndarray,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        length = pcm.shape[0]
        self._pcm: np.ndarray = pcm
        self.gain: float = gain
        self.loop: bool = loop
        self._start: int = max(0, min(start, length))
        self._end: int = length if end is None else max(self._start, min(end, length))
        self._position: int = self._start
        self.finished: bool = self._end <= self._start

    @property
    def position(self) -> int:
        return self._position

    def mix_into(self, out: np.ndarray) -> None:
        """Add the next block of this voice onto ``out``."""
        written = 0
        total = out.shape[0]
        while written < total and not self.finished:
            take = min(total - written, self._end - self._position)
            chunk = self._pcm[self._position : self._position + take]
            # One small array per active voice per block; adding a scratch buffer
            # to avoid it would add real-time-path complexity for a negligible saving.
            out[written : written + take] += chunk * self.gain
            self._position += take
            written += take
            if self._position >= self._end:
                if self.loop:
                    self._position = self._start
                else:
                    self.finished = True
