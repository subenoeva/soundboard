"""Hosts one VST3 effect and exposes the parameters it reports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from pedalboard import load_plugin  # type: ignore[attr-defined]

from soundboard.effects.params import ParamSpec, ParamValue


class _OutputFifo:
    def __init__(self, capacity: int, prefill: int) -> None:
        self._buffer = np.zeros(capacity, dtype=np.float32)
        self._prefill = prefill
        self.reset()

    def reset(self) -> None:
        self._buffer.fill(0.0)
        self._read = 0
        self._write = self._prefill
        self._length = self._prefill

    def prime(self, frames: int) -> None:
        """Learn a plugin's initial buffering without allocating in the callback."""
        if self._length or not 0 <= frames <= self._buffer.size:
            raise RuntimeError("invalid VST3 output FIFO prefill")
        self._prefill = frames
        self._write = frames
        self._length = frames

    def append(self, frames: np.ndarray) -> None:
        frames = np.asarray(frames, dtype=np.float32).reshape(-1)
        count = int(frames.size)
        if self._length + count > self._buffer.size:
            raise RuntimeError("VST3 output FIFO overflow")
        first = min(count, self._buffer.size - self._write)
        self._buffer[self._write : self._write + first] = frames[:first]
        rest = count - first
        if rest:
            self._buffer[:rest] = frames[first:]
        self._write = (self._write + count) % self._buffer.size
        self._length += count

    def pop_into(self, destination: np.ndarray) -> None:
        count = int(destination.size)
        if self._length < count:
            raise RuntimeError("VST3 returned too few samples for real-time processing")
        first = min(count, self._buffer.size - self._read)
        destination[:first] = self._buffer[self._read : self._read + first]
        rest = count - first
        if rest:
            destination[first:] = self._buffer[:rest]
        self._read = (self._read + count) % self._buffer.size
        self._length -= count


def read_param(plugin: Any, name: str) -> ParamValue:
    """One parameter, typed the way the plugin's own descriptor declares it."""
    return _typed(getattr(plugin, name), plugin.parameters[name].type)


def plugin_params(plugin: Any) -> dict[str, ParamValue]:
    """Every parameter the plugin reports. Also what the editor process polls.

    ``plugin.parameters`` is a property that rebuilds its whole dictionary on each
    access — 3.7 ms for Graillon's 67 parameters — so it is read once here rather
    than once per name. Measured on that plugin: 258 ms a read became 4.5 ms.
    """
    parameters = plugin.parameters
    return {
        name: _typed(getattr(plugin, name), parameters[name].type) for name in parameters
    }


def _typed(value: Any, parameter_type: type) -> ParamValue:
    if parameter_type is bool:
        return bool(value)
    if parameter_type is str:
        return str(value)
    return float(value)


def _descriptor(name: str, parameter: Any, value: ParamValue) -> ParamSpec:
    label = str(getattr(parameter, "name", name)).strip() or name.replace("_", " ").title()
    unit = str(getattr(parameter, "label", "") or "")
    parameter_type = getattr(parameter, "type", float)
    if parameter_type is bool:
        return ParamSpec(name, label, 0.0, 1.0, bool(value), unit, "bool")
    if parameter_type is str:
        choices = tuple(str(item) for item in getattr(parameter, "valid_values", ()))
        return ParamSpec(name, label, 0.0, float(max(len(choices) - 1, 0)), str(value), unit,
                         "choice", choices)
    minimum = getattr(parameter, "min_value", None)
    maximum = getattr(parameter, "max_value", None)
    return ParamSpec(
        name,
        label,
        float(minimum) if minimum is not None else 0.0,
        float(maximum) if maximum is not None else 1.0,
        float(value),
        unit,
    )


class VstEffect:
    """A loaded VST3 effect with descriptors derived from its live parameters."""

    kind = "vst3"

    def __init__(
        self,
        plugin: Any,
        path: Path,
        *,
        samplerate: int = 48_000,
        blocksize: int = 256,
    ) -> None:
        if not bool(plugin.is_effect):
            raise ValueError(f"VST3 plugin {path} is an instrument, not an effect")
        self._plugin = plugin
        self.plugin_path = path
        self.label = str(getattr(plugin, "name", path.stem))
        self._samplerate = samplerate
        self._blocksize = blocksize
        self._latency = max(0, int(getattr(plugin, "reported_latency_samples", 0)))
        parameters = plugin.parameters
        values = plugin_params(plugin)
        self._specs = {
            name: _descriptor(name, parameter, values[name])
            for name, parameter in parameters.items()
        }
        self._fifo = _OutputFifo(blocksize * 2, 0)
        self._learned_buffering = False

    def process(self, block: np.ndarray) -> None:
        if block.shape != (self._blocksize,):
            raise ValueError(f"VST3 effect expected {self._blocksize} frames")
        rendered = self._plugin.process(block, self._samplerate, reset=False)
        rendered_frames = int(np.asarray(rendered).size)
        if rendered_frames > self._blocksize:
            raise RuntimeError("VST3 returned more samples than it received")
        if not self._learned_buffering:
            buffered = self._blocksize - rendered_frames
            self._fifo.prime(buffered)
            self._latency = max(self._latency, buffered)
            self._learned_buffering = True
        self._fifo.append(rendered)
        self._fifo.pop_into(block)

    def reset(self) -> None:
        self._plugin.reset()
        self._fifo.reset()

    def _read(self, name: str) -> ParamValue:
        return read_param(self._plugin, name)

    def set_param(self, name: str, value: ParamValue) -> None:
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"{self.label!r} has no parameter {name!r}")
        setattr(self._plugin, name, spec.coerce(value))

    def params(self) -> dict[str, ParamValue]:
        # Restricted to the parameters this block was built with: a name the
        # descriptors do not know is one set_param() would refuse on the way back
        # in, and saving it would give a file that cannot be reloaded.
        live = plugin_params(self._plugin)
        return {name: live[name] for name in self._specs if name in live}

    def param_specs(self) -> tuple[ParamSpec, ...]:
        return tuple(self._specs.values())

    @property
    def latency_frames(self) -> int:
        return self._latency


def load_vst(
    path: Path,
    params: Mapping[str, ParamValue] | None = None,
    *,
    samplerate: int = 48_000,
    blocksize: int = 256,
    loader: Callable[[str], Any] = load_plugin,
) -> VstEffect:
    """Load and introspect a VST3. Call this from an effect-load worker."""
    if not path.exists():
        raise FileNotFoundError(f"VST3 plugin not found: {path}")
    effect = VstEffect(
        loader(str(path)), path, samplerate=samplerate, blocksize=blocksize
    )
    for name, value in (params or {}).items():
        effect.set_param(name, value)
    return effect
