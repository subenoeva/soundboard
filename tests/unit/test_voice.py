import numpy as np
import pytest

from soundboard.audio.voice import Voice


def test_mixes_samples_additively_with_gain() -> None:
    voice = Voice(np.ones(4, dtype=np.float32), gain=0.5)
    out = np.full(4, 1.0, dtype=np.float32)

    voice.mix_into(out)

    assert np.allclose(out, 1.5)


def test_respects_trim_start_and_end() -> None:
    voice = Voice(np.arange(10, dtype=np.float32), start=2, end=5)
    out = np.zeros(4, dtype=np.float32)

    voice.mix_into(out)

    assert np.array_equal(out, np.array([2, 3, 4, 0], dtype=np.float32))
    assert voice.finished


def test_finishes_and_leaves_the_rest_of_the_block_untouched() -> None:
    voice = Voice(np.ones(2, dtype=np.float32))
    out = np.zeros(5, dtype=np.float32)

    voice.mix_into(out)

    assert np.array_equal(out, np.array([1, 1, 0, 0, 0], dtype=np.float32))
    assert voice.finished


def test_finished_voice_writes_nothing_more() -> None:
    voice = Voice(np.ones(2, dtype=np.float32))
    out = np.zeros(4, dtype=np.float32)
    voice.mix_into(out)
    out[:] = 0.0

    voice.mix_into(out)

    assert np.array_equal(out, np.zeros(4, dtype=np.float32))


def test_loops_back_to_the_trim_start() -> None:
    voice = Voice(np.array([1, 2, 3], dtype=np.float32), loop=True)
    out = np.zeros(7, dtype=np.float32)

    voice.mix_into(out)

    assert np.array_equal(out, np.array([1, 2, 3, 1, 2, 3, 1], dtype=np.float32))
    assert not voice.finished


def test_spans_multiple_blocks() -> None:
    voice = Voice(np.arange(6, dtype=np.float32))
    first = np.zeros(4, dtype=np.float32)
    second = np.zeros(4, dtype=np.float32)

    voice.mix_into(first)
    voice.mix_into(second)

    assert np.array_equal(first, np.array([0, 1, 2, 3], dtype=np.float32))
    assert np.array_equal(second, np.array([4, 5, 0, 0], dtype=np.float32))


def test_empty_trim_range_finishes_immediately() -> None:
    voice = Voice(np.ones(4, dtype=np.float32), start=2, end=2)
    out = np.zeros(4, dtype=np.float32)

    voice.mix_into(out)

    assert voice.finished
    assert np.array_equal(out, np.zeros(4, dtype=np.float32))


def test_voice_id_defaults_to_zero_and_is_stored() -> None:
    pcm = np.zeros(10, dtype=np.float32)
    assert Voice(pcm).voice_id == 0
    assert Voice(pcm, voice_id=7).voice_id == 7


def test_progress_advances_from_zero_to_one() -> None:
    pcm = np.ones(100, dtype=np.float32)
    voice = Voice(pcm)
    assert voice.progress == 0.0
    out = np.zeros(50, dtype=np.float32)
    voice.mix_into(out)
    assert voice.progress == pytest.approx(0.5)
    voice.mix_into(out)
    assert voice.progress == pytest.approx(1.0)
    assert voice.finished


def test_progress_respects_trim_range() -> None:
    pcm = np.ones(100, dtype=np.float32)
    voice = Voice(pcm, start=20, end=60)
    out = np.zeros(20, dtype=np.float32)
    voice.mix_into(out)
    assert voice.progress == pytest.approx(0.5)  # 20 frames within a range of 40


def test_progress_is_one_for_empty_range() -> None:
    pcm = np.ones(10, dtype=np.float32)
    voice = Voice(pcm, start=5, end=5)
    assert voice.finished
    assert voice.progress == 1.0
