"""Decodes a source file into the engine's internal format and measures it.

Runs once per import, off the real-time path. Produces the same mono float32 48kHz
PCM that ``audio.audioio.load_mono_48k`` produces for the phase-1 CLI, plus the
metadata the remote library needs: a content hash for dedup and a gain that would
bring the clip's peak to the limiter ceiling without ever modifying the samples
themselves.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

from soundboard.audio.mixer import CEILING


@dataclass(frozen=True)
class ImportedSound:
    pcm: np.ndarray
    sha256: str
    source_filename: str
    duration_frames: int
    orig_samplerate: int
    orig_channels: int
    gain_db: float


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure_gain_db(pcm: np.ndarray) -> float:
    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    if peak <= 0.0:
        return 0.0
    return 20.0 * math.log10(CEILING / peak)


def import_sound(path: str | Path, samplerate: int = 48_000) -> ImportedSound:
    """Decode ``path``, mix to mono, resample to ``samplerate`` and measure it."""
    path = Path(path)
    data, orig_samplerate = sf.read(str(path), dtype="float32", always_2d=True)
    orig_channels = data.shape[1]

    mono = data.mean(axis=1)
    if orig_samplerate != samplerate:
        mono = soxr.resample(mono, orig_samplerate, samplerate, quality="HQ")
    pcm = np.ascontiguousarray(mono, dtype=np.float32)

    return ImportedSound(
        pcm=pcm,
        sha256=_sha256_file(path),
        source_filename=path.name,
        duration_frames=pcm.shape[0],
        orig_samplerate=orig_samplerate,
        orig_channels=orig_channels,
        gain_db=_measure_gain_db(pcm),
    )
