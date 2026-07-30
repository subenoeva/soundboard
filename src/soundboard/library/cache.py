"""On-disk playback cache, keyed by content hash.

Files are named ``<sha256>.f32`` — raw mono float32 frames at the engine sample rate,
the same bytes stored remotely. No header, no format negotiation: the caller always
knows the sample rate (48kHz, fixed) and, when it wants a corruption check, the
expected frame count from the remote row.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np


class SoundCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str) -> Path:
        return self._dir / f"{sha256}.f32"

    def has(self, sha256: str) -> bool:
        return self._path(sha256).exists()

    def read(self, sha256: str) -> np.ndarray:
        return np.fromfile(self._path(sha256), dtype=np.float32)

    def write(self, sha256: str, pcm: np.ndarray) -> None:
        np.ascontiguousarray(pcm, dtype=np.float32).tofile(self._path(sha256))

    def get_or_fetch(
        self,
        sha256: str,
        fetch: Callable[[], bytes],
        expected_frames: int | None = None,
    ) -> np.ndarray:
        """Return the cached PCM for ``sha256``, downloading on a miss.

        A cached file whose frame count does not match ``expected_frames`` is treated
        as corrupt (e.g. a previous run was killed mid-write) and re-downloaded
        transparently, rather than handed to the caller or reported as an error.
        """
        if self.has(sha256):
            pcm = self.read(sha256)
            if expected_frames is None or pcm.shape[0] == expected_frames:
                return pcm
        pcm = np.frombuffer(fetch(), dtype=np.float32).copy()
        self.write(sha256, pcm)
        return pcm
