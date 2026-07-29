import numpy as np

from soundboard.audio.drift import DriftController, DriftResampler
from soundboard.audio.ringbuffer import RingBuffer


def test_ratio_is_one_at_target_fill() -> None:
    controller = DriftController(target_fill=512)

    assert controller.update(512) == 1.0


def test_ratio_rises_when_buffer_accumulates() -> None:
    controller = DriftController(target_fill=512)
    ratio = 1.0
    for _ in range(2000):
        ratio = controller.update(1024)

    assert ratio > 1.0
    assert ratio <= 1.005


def test_ratio_falls_when_buffer_drains() -> None:
    controller = DriftController(target_fill=512)
    ratio = 1.0
    for _ in range(2000):
        ratio = controller.update(0)

    assert ratio < 1.0
    assert ratio >= 0.995


def test_ema_converges_towards_observed_fill() -> None:
    controller = DriftController(target_fill=512)
    for _ in range(5000):
        controller.update(700)

    assert abs(controller.ema_fill - 700) < 1.0


def test_resampler_at_ratio_one_is_passthrough() -> None:
    rb = RingBuffer(1024)
    source = np.arange(64, dtype=np.float32)
    rb.write(source)
    resampler = DriftResampler(rb, max_block=32)
    out = np.zeros(32, dtype=np.float32)

    resampler.read(out, 1.0)

    assert np.allclose(out, source[:32], atol=1e-5)


def test_resampler_above_one_consumes_more_input_than_it_emits() -> None:
    rb = RingBuffer(8192)
    rb.write(np.zeros(4096, dtype=np.float32))
    resampler = DriftResampler(rb, max_block=256)
    out = np.zeros(256, dtype=np.float32)
    before = rb.fill

    for _ in range(8):
        resampler.read(out, 1.004)

    consumed = before - rb.fill
    assert consumed > 8 * 256


def test_resampler_keeps_a_sine_continuous_across_blocks() -> None:
    samplerate = 48_000
    frames = 48_000
    t = np.arange(frames, dtype=np.float64) / samplerate
    sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    rb = RingBuffer(frames + 16)
    rb.write(sine)
    resampler = DriftResampler(rb, max_block=256)

    blocks = []
    out = np.zeros(256, dtype=np.float32)
    for _ in range(160):
        resampler.read(out, 1.001)
        blocks.append(out.copy())
    signal = np.concatenate(blocks)

    # A 1 kHz sine at 48 kHz moves at most ~0.131 per sample. Any block-boundary
    # discontinuity would show up as a much larger jump.
    assert np.max(np.abs(np.diff(signal))) < 0.15
