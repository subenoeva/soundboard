"""Decoding clips into the engine's internal format."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import soxr


def load_mono_48k(path: str | Path, samplerate: int = 48_000) -> np.ndarray:
    """Decode a file into mono float32 at the engine sample rate.

    This is the phase-1 loader: soundfile only, decoding on demand. The library
    importer of phase 2 replaces it with a cached, multi-format pipeline.
    """
    data, file_rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if file_rate != samplerate:
        mono = soxr.resample(mono, file_rate, samplerate, quality="HQ")
    return np.ascontiguousarray(mono, dtype=np.float32)
