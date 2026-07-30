from pathlib import Path

import numpy as np

from soundboard.library.cache import SoundCache


def test_has_reports_false_for_an_unknown_hash(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)

    assert cache.has("deadbeef") is False


def test_write_then_read_roundtrips_the_pcm(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    pcm = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    cache.write("abc123", pcm)

    assert cache.has("abc123") is True
    assert np.array_equal(cache.read("abc123"), pcm)


def test_get_or_fetch_returns_cached_pcm_without_calling_fetch(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    pcm = np.array([1.0, 2.0], dtype=np.float32)
    cache.write("hit", pcm)

    def fail_if_called() -> bytes:
        raise AssertionError("fetch should not be called on a cache hit")

    result = cache.get_or_fetch("hit", fail_if_called, expected_frames=2)

    assert np.array_equal(result, pcm)


def test_get_or_fetch_downloads_and_caches_on_a_miss(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    pcm = np.array([0.5, -0.5, 0.25, -0.25], dtype=np.float32)
    calls = 0

    def fetch() -> bytes:
        nonlocal calls
        calls += 1
        return pcm.tobytes()

    result = cache.get_or_fetch("miss", fetch, expected_frames=4)

    assert calls == 1
    assert np.array_equal(result, pcm)
    assert cache.has("miss") is True
    # A second call must hit the now-populated cache, not fetch again.
    cache.get_or_fetch("miss", fetch, expected_frames=4)
    assert calls == 1


def test_get_or_fetch_redownloads_when_the_cached_file_is_truncated(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    cache.write("corrupt", np.array([1.0], dtype=np.float32))  # 1 frame, not the real 3
    good_pcm = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    def fetch() -> bytes:
        return good_pcm.tobytes()

    result = cache.get_or_fetch("corrupt", fetch, expected_frames=3)

    assert np.array_equal(result, good_pcm)


def test_creates_the_cache_directory_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "pcm" / "nested"

    SoundCache(nested)

    assert nested.is_dir()
