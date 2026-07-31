import numpy as np
import pytest

from soundboard.audio.mixer import CEILING, Mixer
from soundboard.audio.voice import Voice


def test_passes_the_microphone_through_when_idle() -> None:
    mixer = Mixer(blocksize=8)
    mic = np.full(8, 0.1, dtype=np.float32)
    out = np.zeros(8, dtype=np.float32)

    mixer.process(mic, out)

    assert np.allclose(out, 0.1, atol=1e-3)


def test_adds_voice_audio_to_the_microphone() -> None:
    mixer = Mixer(blocksize=4, duck_threshold=1.0)  # threshold high: no ducking here
    mixer.add_voice(Voice(np.full(4, 0.2, dtype=np.float32)))
    mic = np.full(4, 0.1, dtype=np.float32)
    out = np.zeros(4, dtype=np.float32)

    mixer.process(mic, out)

    # The soft limiter bends even quiet signals slightly, so compare loosely.
    assert np.allclose(out, 0.3, atol=0.02)


def test_ducking_attenuates_the_microphone_while_a_clip_plays() -> None:
    mixer = Mixer(blocksize=256, duck_db=-12.0)
    # Levels are kept low so the soft limiter stays out of the way and the
    # measured attenuation is the ducking gain alone.
    mixer.add_voice(Voice(np.full(256 * 100, 0.05, dtype=np.float32), loop=True))
    mic = np.full(256, 0.2, dtype=np.float32)
    out = np.zeros(256, dtype=np.float32)

    for _ in range(50):
        mixer.process(mic, out)

    expected_gain = 10.0 ** (-12.0 / 20.0)  # 0.2512
    mic_component = float(np.mean(out)) - 0.05
    assert abs(mic_component - 0.2 * expected_gain) < 0.005


def test_ducking_can_be_disabled() -> None:
    mixer = Mixer(blocksize=256, duck_db=-12.0)
    mixer.ducking_enabled = False
    mixer.add_voice(Voice(np.full(256 * 100, 0.05, dtype=np.float32), loop=True))
    mic = np.full(256, 0.2, dtype=np.float32)
    out = np.zeros(256, dtype=np.float32)

    for _ in range(50):
        mixer.process(mic, out)

    assert abs(float(np.mean(out)) - 0.25) < 0.01


def test_finished_voices_are_dropped() -> None:
    mixer = Mixer(blocksize=4)
    mixer.add_voice(Voice(np.ones(2, dtype=np.float32)))
    out = np.zeros(4, dtype=np.float32)
    mic = np.zeros(4, dtype=np.float32)

    assert mixer.active_voices == 1
    mixer.process(mic, out)
    assert mixer.active_voices == 0


def test_stop_all_clears_every_voice() -> None:
    mixer = Mixer(blocksize=4)
    mixer.add_voice(Voice(np.ones(1000, dtype=np.float32)))
    mixer.add_voice(Voice(np.ones(1000, dtype=np.float32)))

    mixer.stop_all()

    assert mixer.active_voices == 0


def test_limiter_keeps_the_output_under_the_ceiling() -> None:
    mixer = Mixer(blocksize=8, duck_threshold=1e9)
    mic = np.full(8, 5.0, dtype=np.float32)
    out = np.zeros(8, dtype=np.float32)

    mixer.process(mic, out)

    assert np.all(np.abs(out) < CEILING)


def test_output_gain_scales_the_mix() -> None:
    mixer = Mixer(blocksize=4, duck_threshold=1e9)
    mixer.output_gain = 0.5
    mic = np.full(4, 0.2, dtype=np.float32)
    out = np.zeros(4, dtype=np.float32)

    mixer.process(mic, out)

    assert np.allclose(out, 0.1, atol=1e-3)


def test_voice_states_reports_id_and_progress() -> None:
    mixer = Mixer(blocksize=50)
    pcm = np.ones(100, dtype=np.float32) * 0.1
    mixer.add_voice(Voice(pcm, voice_id=3))
    mic = np.zeros(50, dtype=np.float32)
    out = np.zeros(50, dtype=np.float32)
    mixer.process(mic, out)
    states = mixer.voice_states()
    assert states == [(3, pytest.approx(0.5))]  # type: ignore[comparison-overlap]


def test_voice_states_drops_finished_voices() -> None:
    mixer = Mixer(blocksize=50)
    mixer.add_voice(Voice(np.ones(50, dtype=np.float32) * 0.1, voice_id=1))
    mic = np.zeros(50, dtype=np.float32)
    out = np.zeros(50, dtype=np.float32)
    mixer.process(mic, out)
    assert mixer.voice_states() == []


def test_last_peak_tracks_output_block() -> None:
    mixer = Mixer(blocksize=50)
    mic = np.zeros(50, dtype=np.float32)
    out = np.zeros(50, dtype=np.float32)
    mixer.process(mic, out)
    assert mixer.last_peak == 0.0
    mixer.add_voice(Voice(np.ones(100, dtype=np.float32) * 0.5, voice_id=1))
    mixer.process(mic, out)
    assert mixer.last_peak == pytest.approx(float(np.max(np.abs(out))))
    assert mixer.last_peak > 0.0
