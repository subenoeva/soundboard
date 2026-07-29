"""PortAudio backend, via the sounddevice bindings."""

from __future__ import annotations

from typing import Any

import numpy as np
import sounddevice as sd

from soundboard.audio.backend import DeviceInfo, InputCallback, OutputCallback, Stream

# Windows exposes the same physical device once per host API, all under the same
# (or MME-truncated) name. Prefer the lowest-latency/most-capable API on a name tie
# instead of treating the duplicate as ambiguous.
_HOSTAPI_PRIORITY = ("Windows WASAPI", "Windows DirectSound", "MME", "Windows WDM-KS")


def _hostapi_rank(hostapi: str) -> int:
    try:
        return _HOSTAPI_PRIORITY.index(hostapi)
    except ValueError:
        return len(_HOSTAPI_PRIORITY)


def find_device(devices: list[DeviceInfo], needle: str, *, want_input: bool) -> DeviceInfo:
    """Resolve a device by case-insensitive substring of its name.

    Devices are matched by name rather than index because PortAudio indices shift
    whenever hardware is plugged in or removed.
    """
    lowered = needle.lower()
    matches = [
        device
        for device in devices
        if lowered in device.name.lower()
        and (device.max_input_channels if want_input else device.max_output_channels) > 0
    ]
    if not matches:
        direction = "input" if want_input else "output"
        raise LookupError(f"no device matching {needle!r} with an {direction} channel")
    if len(matches) > 1:
        best_rank = min(_hostapi_rank(device.hostapi) for device in matches)
        matches = [device for device in matches if _hostapi_rank(device.hostapi) == best_rank]
    if len(matches) > 1:
        names = ", ".join(repr(device.name) for device in matches)
        raise LookupError(f"ambiguous device name {needle!r}; matches: {names}")
    return matches[0]


class _SoundDeviceStream:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()


class PortAudioBackend:
    """Real audio I/O. Mono in, N channels out, always float32."""

    def __init__(self) -> None:
        # Driver-reported xrun count (input_overflow, output_underflow, etc.),
        # accumulated from PortAudio's own ``status`` callback flag. Distinct
        # from RingBuffer's overrun/underrun counters, which never see this.
        self.xruns = 0

    def list_devices(self) -> list[DeviceInfo]:
        hostapis = sd.query_hostapis()
        return [
            DeviceInfo(
                index=index,
                name=str(device["name"]),
                hostapi=str(hostapis[device["hostapi"]]["name"]),
                max_input_channels=int(device["max_input_channels"]),
                max_output_channels=int(device["max_output_channels"]),
                default_samplerate=float(device["default_samplerate"]),
            )
            for index, device in enumerate(sd.query_devices())
        ]

    def open_input(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        callback: InputCallback,
    ) -> Stream:
        def on_data(indata: np.ndarray, frames: int, time: Any, status: Any) -> None:
            if status:
                self.xruns += 1
            callback(indata[:, 0])

        return _SoundDeviceStream(
            sd.InputStream(
                device=device,
                samplerate=samplerate,
                blocksize=blocksize,
                channels=1,
                dtype="float32",
                latency="low",
                callback=on_data,
            )
        )

    def open_output(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        channels: int,
        callback: OutputCallback,
    ) -> Stream:
        def on_data(outdata: np.ndarray, frames: int, time: Any, status: Any) -> None:
            if status:
                self.xruns += 1
            callback(outdata)

        return _SoundDeviceStream(
            sd.OutputStream(
                device=device,
                samplerate=samplerate,
                blocksize=blocksize,
                channels=channels,
                dtype="float32",
                latency="low",
                callback=on_data,
            )
        )
