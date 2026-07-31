"""AudioEngine voice identity and level reporting, over FakeBackend."""

from __future__ import annotations

import numpy as np

from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.fake_backend import FakeBackend


def _running_engine() -> tuple[AudioEngine, FakeBackend]:
    backend = FakeBackend()
    engine = AudioEngine(backend, EngineConfig(blocksize=64))
    engine.start()
    return engine, backend


def test_play_returns_increasing_voice_ids() -> None:
    engine, _ = _running_engine()
    pcm = np.ones(256, dtype=np.float32) * 0.1
    first = engine.play(pcm)
    second = engine.play(pcm)
    assert first == 1
    assert second == 2
    engine.stop()


def test_voice_states_and_peak_after_processing() -> None:
    engine, backend = _running_engine()
    pcm = np.ones(1024, dtype=np.float32) * 0.5
    voice_id = engine.play(pcm)
    backend.advance(2)
    states = dict(engine.voice_states())
    assert voice_id in states
    assert 0.0 < states[voice_id] < 1.0
    assert engine.last_peak > 0.0
    engine.stop()
