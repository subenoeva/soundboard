import itertools
import sys
import threading

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


def test_concurrent_write_and_read_never_reorders_or_corrupts_frames() -> None:
    """Two real OS threads hammer write()/read() against an undersized buffer.

    This is the spec-mandated RingBuffer concurrency test (see docs/superpowers/
    specs/2026-07-29-soundboard-design.md, section 9), and also a regression
    guard for the lost-update race in write()/read(): before the fix, the two
    methods each split their work across two separate ``with self._lock:``
    blocks, copying the buffer *unlocked* in between, which let a producer
    overflow clobber a concurrent consumer's stale read index.

    The producer writes a strictly increasing sequence of float32 values in
    small chunks (sizes 1-3); the consumer reads in small chunks (size 6)
    against a deliberately tiny capacity (32 frames, 31 usable) so overruns
    happen on almost every write. Overruns legitimately create *gaps* in the
    sequence the consumer sees (that is correct FIFO-drop behaviour, not a
    bug) - what a corrupted lock could produce instead is a repeated,
    decreasing, or out-of-order value, which ``np.diff(...) > 0`` catches.

    ``sys.setswitchinterval`` is lowered for the duration of the test. The
    unlocked window the pre-fix bug depended on is only a few numpy
    instructions wide, and CPython only considers switching threads at
    bytecode-count/time boundaries; at the default 5 ms interval the race
    this test targets was empirically never observed to reproduce in dozens
    of runs. At a 10 us interval it reproduced in 15/15 trial runs against
    the pre-fix implementation (verified manually via ``git stash`` during
    development) while still passing reliably (30/30 trial runs) against the
    fix in this file - it makes the test both fast (~15 ms) and a meaningful
    regression guard instead of a coin flip.
    """
    capacity = 32
    num_chunks = 8_000
    out_size = 6
    # Safety valve only: bounds how long the consumer spins waiting for the
    # producer before failing loudly instead of hanging forever.
    max_consumer_iterations = 10_000_000

    rb = RingBuffer(capacity)
    producer_done = threading.Event()
    collected: list[np.ndarray] = []

    def produce() -> None:
        value = 0
        sizes = itertools.cycle((1, 2, 3))
        for _ in range(num_chunks):
            size = next(sizes)
            rb.write(np.arange(value, value + size, dtype=np.float32))
            value += size
        producer_done.set()

    def consume() -> None:
        out = np.zeros(out_size, dtype=np.float32)
        for _ in range(max_consumer_iterations):
            take = rb.read(out)
            if take:
                collected.append(out[:take].copy())
            if producer_done.is_set() and rb.fill == 0:
                return
        raise AssertionError("consumer never observed the producer finishing")

    consumer_thread = threading.Thread(target=consume)
    producer_thread = threading.Thread(target=produce)
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.00001)
    try:
        consumer_thread.start()
        producer_thread.start()
        producer_thread.join()
        consumer_thread.join()
    finally:
        sys.setswitchinterval(previous_interval)

    assert collected, "consumer never read any real frames"
    combined = np.concatenate(collected)
    assert combined.size > 100, "stress run collected suspiciously few frames"
    assert np.all(np.diff(combined) > 0)
