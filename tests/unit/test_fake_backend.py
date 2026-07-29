import numpy as np

from soundboard.audio.fake_backend import FakeBackend


def test_lists_default_devices() -> None:
    backend = FakeBackend()
    names = [d.name for d in backend.list_devices()]

    assert "Fake Microphone" in names
    assert "Fake Cable" in names


def test_advance_drives_the_input_callback() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: np.full(frames, 0.25, dtype=np.float32)
    received: list[np.ndarray] = []

    def on_input(block: np.ndarray) -> None:
        received.append(block.copy())

    stream = backend.open_input(
        device=0, samplerate=48_000, blocksize=64, callback=on_input
    )
    stream.start()

    backend.advance(3)

    assert len(received) == 3
    assert np.allclose(received[0], 0.25)


def test_advance_captures_output_blocks() -> None:
    backend = FakeBackend()

    def fill(out: np.ndarray) -> None:
        out[:] = 0.5

    stream = backend.open_output(
        device=1, samplerate=48_000, blocksize=64, channels=2, callback=fill
    )
    stream.start()

    backend.advance(2)

    assert len(backend.captured) == 2
    assert backend.captured[0].shape == (64, 2)
    assert np.allclose(backend.captured[0], 0.5)


def test_stopped_streams_do_not_run() -> None:
    backend = FakeBackend()
    calls = 0

    def count(block: np.ndarray) -> None:
        nonlocal calls
        calls += 1

    stream = backend.open_input(device=0, samplerate=48_000, blocksize=64, callback=count)
    backend.advance(5)

    assert calls == 0
    stream.start()
    backend.advance(2)
    assert calls == 2


def test_input_runs_before_output_within_a_block() -> None:
    backend = FakeBackend()
    order: list[str] = []
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)
    out_stream = backend.open_output(
        device=1, samplerate=48_000, blocksize=8, channels=1, callback=lambda o: order.append("out")
    )
    in_stream = backend.open_input(
        device=0, samplerate=48_000, blocksize=8, callback=lambda b: order.append("in")
    )
    out_stream.start()
    in_stream.start()

    backend.advance(2)

    assert order == ["in", "out", "in", "out"]
