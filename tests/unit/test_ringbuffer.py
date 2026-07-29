import numpy as np
import pytest

from soundboard.audio.ringbuffer import RingBuffer


def test_roundtrip_returns_written_frames() -> None:
    rb = RingBuffer(16)
    rb.write(np.arange(4, dtype=np.float32))
    out = np.zeros(4, dtype=np.float32)

    assert rb.read(out) == 4
    assert np.array_equal(out, np.arange(4, dtype=np.float32))
    assert rb.fill == 0


def test_fill_reports_pending_frames() -> None:
    rb = RingBuffer(16)
    rb.write(np.ones(5, dtype=np.float32))

    assert rb.fill == 5


def test_wraparound_preserves_order() -> None:
    rb = RingBuffer(8)  # 7 usable frames
    scratch = np.zeros(5, dtype=np.float32)
    rb.write(np.arange(5, dtype=np.float32))
    rb.read(scratch)
    rb.write(np.arange(5, 10, dtype=np.float32))

    assert rb.read(scratch) == 5
    assert np.array_equal(scratch, np.arange(5, 10, dtype=np.float32))


def test_underflow_zero_pads_and_counts() -> None:
    rb = RingBuffer(16)
    rb.write(np.ones(2, dtype=np.float32))
    out = np.full(5, 9.0, dtype=np.float32)

    assert rb.read(out) == 2
    assert np.array_equal(out, np.array([1, 1, 0, 0, 0], dtype=np.float32))
    assert rb.underruns == 1


def test_overflow_drops_oldest_and_counts() -> None:
    rb = RingBuffer(6)  # 5 usable frames
    rb.write(np.arange(5, dtype=np.float32))
    rb.write(np.array([100.0, 200.0], dtype=np.float32))
    out = np.zeros(5, dtype=np.float32)
    rb.read(out)

    assert np.array_equal(out, np.array([2, 3, 4, 100, 200], dtype=np.float32))
    assert rb.overruns == 1


def test_write_longer_than_capacity_keeps_the_tail() -> None:
    rb = RingBuffer(6)
    rb.write(np.arange(20, dtype=np.float32))
    out = np.zeros(5, dtype=np.float32)
    rb.read(out)

    assert np.array_equal(out, np.arange(15, 20, dtype=np.float32))


def test_rejects_tiny_capacity() -> None:
    with pytest.raises(ValueError):
        RingBuffer(1)
