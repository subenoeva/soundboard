from pathlib import Path

import numpy as np
import soundfile as sf

from soundboard.audioio import load_mono_48k


def test_downmixes_stereo_to_mono(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    stereo = np.zeros((100, 2), dtype=np.float32)
    stereo[:, 0] = 1.0
    stereo[:, 1] = 0.0
    sf.write(path, stereo, 48_000)

    pcm = load_mono_48k(path)

    assert pcm.ndim == 1
    assert pcm.dtype == np.float32
    assert np.allclose(pcm, 0.5, atol=1e-3)


def test_resamples_to_48k(tmp_path: Path) -> None:
    path = tmp_path / "low.wav"
    sf.write(path, np.zeros(24_000, dtype=np.float32), 24_000)

    pcm = load_mono_48k(path)

    assert abs(pcm.shape[0] - 48_000) < 100


def test_passes_through_matching_rate(tmp_path: Path) -> None:
    path = tmp_path / "match.wav"
    sf.write(path, np.full(1000, 0.25, dtype=np.float32), 48_000)

    pcm = load_mono_48k(path)

    assert pcm.shape[0] == 1000
    assert np.allclose(pcm, 0.25, atol=1e-4)
