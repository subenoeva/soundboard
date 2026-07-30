import hashlib
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundboard.audio.mixer import CEILING
from soundboard.library.importer import import_sound


def _write_wav(path: Path, samples: np.ndarray, samplerate: int) -> None:
    sf.write(str(path), samples, samplerate)


def test_reports_original_samplerate_and_channels(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, np.full((4_410, 2), 0.1, dtype=np.float32), 44_100)

    imported = import_sound(path)

    assert imported.orig_samplerate == 44_100
    assert imported.orig_channels == 2


def test_mixes_to_mono_and_resamples_to_48k(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, np.full((4_410, 2), 0.1, dtype=np.float32), 44_100)

    imported = import_sound(path)

    assert imported.pcm.ndim == 1
    assert imported.duration_frames == imported.pcm.shape[0]
    # 100ms at 44.1kHz resampled to 48kHz is ~4800 frames.
    assert abs(imported.pcm.shape[0] - 4_800) < 10


def test_sha256_matches_the_original_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, np.full((4_800,), 0.2, dtype=np.float32), 48_000)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    imported = import_sound(path)

    assert imported.sha256 == expected


def test_source_filename_is_the_basename(tmp_path: Path) -> None:
    path = tmp_path / "subdir_marker.wav"
    path.parent.mkdir(exist_ok=True)
    _write_wav(path, np.zeros(480, dtype=np.float32), 48_000)

    imported = import_sound(path)

    assert imported.source_filename == "subdir_marker.wav"


def test_gain_db_brings_the_peak_to_the_limiter_ceiling(tmp_path: Path) -> None:
    path = tmp_path / "half.wav"
    _write_wav(path, np.full((480,), 0.5, dtype=np.float32), 48_000)

    imported = import_sound(path)

    expected_gain_db = 20.0 * math.log10(CEILING / 0.5)
    assert imported.gain_db == pytest.approx(expected_gain_db, abs=1e-2)


def test_silence_gets_zero_gain(tmp_path: Path) -> None:
    path = tmp_path / "silence.wav"
    _write_wav(path, np.zeros(480, dtype=np.float32), 48_000)

    imported = import_sound(path)

    assert imported.gain_db == 0.0
