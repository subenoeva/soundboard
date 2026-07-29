"""Single-producer / single-consumer ring buffer for mono float32 frames."""

from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Fixed-capacity FIFO of mono ``float32`` frames.

    One thread writes and one thread reads. Only the index updates run inside the
    lock; the sample copies happen outside it, so a slow ``memcpy`` never blocks
    the other side. A single slot is kept free so that a full buffer is
    distinguishable from an empty one.
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 2:
            raise ValueError("capacity must be at least 2 frames")
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._size = capacity
        self._read = 0
        self._write = 0
        self._lock = threading.Lock()
        self.overruns = 0
        self.underruns = 0

    @property
    def capacity(self) -> int:
        """Usable capacity in frames."""
        return self._size - 1

    @property
    def fill(self) -> int:
        """Frames written but not yet read."""
        with self._lock:
            return (self._write - self._read) % self._size

    def write(self, data: np.ndarray) -> None:
        """Append frames. Producer thread only.

        On overflow the oldest frames are dropped: keeping latency bounded matters
        more than preserving samples the consumer has already fallen behind on.
        """
        if int(data.shape[0]) > self.capacity:
            data = data[-self.capacity :]
        n = int(data.shape[0])
        if n == 0:
            return

        with self._lock:
            free = self.capacity - (self._write - self._read) % self._size
            if n > free:
                self._read = (self._read + (n - free)) % self._size
                self.overruns += 1
            start = self._write

        end = start + n
        if end <= self._size:
            self._buf[start:end] = data
        else:
            split = self._size - start
            self._buf[start:] = data[:split]
            self._buf[: end - self._size] = data[split:]

        with self._lock:
            self._write = end % self._size

    def read(self, out: np.ndarray) -> int:
        """Fill ``out`` with the oldest frames. Consumer thread only.

        Returns the number of real frames read. Any shortfall is zero-filled and
        counted as an underrun.
        """
        n = int(out.shape[0])
        with self._lock:
            available = int((self._write - self._read) % self._size)
            start = self._read

        take = min(n, available)
        end = start + take
        if end <= self._size:
            out[:take] = self._buf[start:end]
        else:
            split = self._size - start
            out[:split] = self._buf[start:]
            out[split:take] = self._buf[: end - self._size]

        if take < n:
            out[take:] = 0.0
            self.underruns += 1

        with self._lock:
            self._read = end % self._size
        return take
