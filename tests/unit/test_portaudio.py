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
