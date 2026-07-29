from typing import Any

import numpy as np
import pytest

from soundboard.audio.backend import DeviceInfo
from soundboard.audio.portaudio import PortAudioBackend, find_device

DEVICES = [
    DeviceInfo(0, "Microphone (Realtek)", "MME", 2, 0, 44_100.0),
    DeviceInfo(1, "CABLE Input (VB-Audio Virtual Cable)", "MME", 0, 2, 48_000.0),
    DeviceInfo(2, "CABLE Output (VB-Audio Virtual Cable)", "MME", 2, 0, 48_000.0),
]


def test_find_device_matches_a_substring_case_insensitively() -> None:
    found = find_device(DEVICES, "realtek", want_input=True)

    assert found.index == 0


def test_find_device_filters_by_direction() -> None:
    found = find_device(DEVICES, "cable", want_input=False)

    assert found.index == 1


def test_find_device_rejects_an_ambiguous_needle() -> None:
    extended = [*DEVICES, DeviceInfo(3, "CABLE-A Output (VB-Audio)", "MME", 2, 0, 48_000.0)]

    with pytest.raises(LookupError, match="ambiguous"):
        find_device(extended, "cable", want_input=True)


def test_find_device_reports_a_missing_needle() -> None:
    with pytest.raises(LookupError, match="no device"):
        find_device(DEVICES, "nonexistent", want_input=True)


@pytest.mark.hardware
def test_lists_real_devices() -> None:
    devices = PortAudioBackend().list_devices()

    assert devices
    assert all(isinstance(d.name, str) for d in devices)


def test_open_input_converts_stereo_indata_to_mono_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeInputStream:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("soundboard.audio.portaudio.sd.InputStream", _FakeInputStream)

    received: list[np.ndarray] = []
    PortAudioBackend().open_input(
        device=0,
        samplerate=48_000,
        blocksize=64,
        callback=lambda block: received.append(block.copy()),
    )

    indata = np.full((64, 1), 0.5, dtype=np.float32)
    captured["callback"](indata, 64, None, None)

    assert len(received) == 1
    assert received[0].shape == (64,)
    assert np.allclose(received[0], 0.5)


def test_open_output_passes_the_buffer_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeOutputStream:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("soundboard.audio.portaudio.sd.OutputStream", _FakeOutputStream)

    def fill(out: np.ndarray) -> None:
        out[:] = 0.25

    PortAudioBackend().open_output(
        device=1, samplerate=48_000, blocksize=64, channels=2, callback=fill
    )

    outdata = np.zeros((64, 2), dtype=np.float32)
    captured["callback"](outdata, 64, None, None)

    assert np.allclose(outdata, 0.25)


def test_input_status_flag_counts_as_an_xrun(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeInputStream:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("soundboard.audio.portaudio.sd.InputStream", _FakeInputStream)

    backend = PortAudioBackend()
    backend.open_input(device=0, samplerate=48_000, blocksize=64, callback=lambda block: None)

    indata = np.zeros((64, 1), dtype=np.float32)
    captured["callback"](indata, 64, None, None)
    assert backend.xruns == 0

    captured["callback"](indata, 64, None, "input_overflow")
    assert backend.xruns == 1


def test_output_status_flag_counts_as_an_xrun(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeOutputStream:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("soundboard.audio.portaudio.sd.OutputStream", _FakeOutputStream)

    backend = PortAudioBackend()
    backend.open_output(
        device=1, samplerate=48_000, blocksize=64, channels=2, callback=lambda out: None
    )

    outdata = np.zeros((64, 2), dtype=np.float32)
    captured["callback"](outdata, 64, None, None)
    assert backend.xruns == 0

    captured["callback"](outdata, 64, None, "output_underflow")
    assert backend.xruns == 1
