"""Stateful DPDFNet streaming behind the fixed-block ``Effect`` contract.

The STFT and overlap-add loop is adapted from CEVA's DPDFNet ``StreamEnhancer``
(Copyright 2025 CEVA, Apache-2.0). The app owns the fixed-block adapter around
it: preallocated input storage, latency-aligned dry/wet FIFOs, and bounded
per-callback inference.

ONNX Runtime releases the GIL while computing and must reacquire it before the
callback can finish. Background work in this process therefore must not occupy
the GIL for long; CPU-bound work belongs in a subprocess.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Protocol

import numpy as np

from soundboard.effects.params import ParamSpec

_SAMPLE_RATE = 48_000
_WINDOW_FRAMES = 960
_HOP_FRAMES = 480
_MEASURED_WORST_MS = 2.174
_COST_HISTORY = 256
_MIX = ParamSpec("mix", "Mix", 0.0, 1.0, 1.0)
_MODEL_FILENAME = "dpdfnet2_48khz_hr.onnx"


class Session(Protocol):
    def run(
        self, output_names: list[str], inputs: dict[str, np.ndarray]
    ) -> list[np.ndarray]: ...


@dataclass(frozen=True)
class RuntimeModel:
    """The model state and names the streaming ONNX signature exposes."""

    session: Session
    initial_state: np.ndarray
    input_spec_name: str
    input_state_name: str
    output_spec_name: str
    output_state_name: str


class _AudioFifo:
    """A fixed-capacity SPSC-style FIFO used only by one callback invocation."""

    def __init__(self, capacity: int, prefill: int) -> None:
        self._buffer = np.zeros(capacity, dtype=np.float32)
        self._prefill = prefill
        self.reset()

    def reset(self) -> None:
        self._buffer.fill(0.0)
        self._read = 0
        self._write = self._prefill
        self._length = self._prefill

    def append(self, frames: np.ndarray) -> None:
        count = int(frames.size)
        if self._length + count > self._buffer.size:
            raise RuntimeError("neural output FIFO overflow")
        first = min(count, self._buffer.size - self._write)
        self._buffer[self._write : self._write + first] = frames[:first]
        rest = count - first
        if rest:
            self._buffer[:rest] = frames[first:]
        self._write = (self._write + count) % self._buffer.size
        self._length += count

    def pop_into(self, destination: np.ndarray) -> None:
        count = int(destination.size)
        if count > self._length:
            raise RuntimeError("neural output FIFO underflow")
        first = min(count, self._buffer.size - self._read)
        destination[:first] = self._buffer[self._read : self._read + first]
        rest = count - first
        if rest:
            destination[first:] = self._buffer[:rest]
        self._read = (self._read + count) % self._buffer.size
        self._length -= count


def _vorbis_window(length: int) -> np.ndarray:
    half = length / 2
    indices = np.arange(length)
    inner = np.sin(0.5 * np.pi * (indices + 0.5) / half)
    return np.sin(0.5 * np.pi * inner * inner).astype(np.float32)


class NeuralEffect:
    """DPDFNet with exactly one input block and one output block per call."""

    kind = "neural"

    def __init__(
        self,
        runtime: RuntimeModel,
        *,
        blocksize: int,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        minimum = int(np.ceil(_MEASURED_WORST_MS * _SAMPLE_RATE / 1000.0))
        if not minimum <= blocksize <= _HOP_FRAMES:
            raise ValueError(
                f"blocksize {blocksize} cannot serve the inline neural model "
                f"(expected {minimum}..{_HOP_FRAMES})"
            )
        self._runtime = runtime
        self._blocksize = blocksize
        self._clock_ns = clock_ns
        self._window = _vorbis_window(_WINDOW_FRAMES)
        self._input = np.zeros(_WINDOW_FRAMES, dtype=np.float32)
        self._windowed = np.zeros(_WINDOW_FRAMES, dtype=np.float32)
        self._overlap = np.zeros(_WINDOW_FRAMES, dtype=np.float32)
        self._time_frame = np.zeros(_WINDOW_FRAMES, dtype=np.float32)
        fifo_capacity = _WINDOW_FRAMES + _HOP_FRAMES
        self._wet_fifo = _AudioFifo(fifo_capacity, _WINDOW_FRAMES)
        self._dry_fifo = _AudioFifo(fifo_capacity, _WINDOW_FRAMES)
        self._wet_block = np.zeros(blocksize, dtype=np.float32)
        self._dry_block = np.zeros(blocksize, dtype=np.float32)
        self._costs = np.zeros(_COST_HISTORY, dtype=np.float64)
        self._cost_count = 0
        self._cost_cursor = 0
        self._mix = _MIX.default
        self._input_length: int = 0
        self._state: np.ndarray = runtime.initial_state.copy()
        self.reset()

    def process(self, block: np.ndarray) -> None:
        if block.shape != (self._blocksize,):
            raise ValueError(f"neural effect expected {self._blocksize} frames")
        self._dry_fifo.append(block)
        self._feed(block)
        self._dry_fifo.pop_into(self._dry_block)
        self._wet_fifo.pop_into(self._wet_block)
        np.multiply(self._dry_block, 1.0 - self._mix, out=block)
        np.multiply(self._wet_block, self._mix, out=self._wet_block)
        np.add(block, self._wet_block, out=block)

    def _feed(self, block: np.ndarray) -> None:
        needed = _WINDOW_FRAMES - self._input_length
        first = min(self._blocksize, needed)
        end = self._input_length + first
        self._input[self._input_length : end] = block[:first]
        self._input_length = end
        if self._input_length < _WINDOW_FRAMES:
            return

        self._infer()
        self._input[:_HOP_FRAMES] = self._input[_HOP_FRAMES:]
        self._input_length = _HOP_FRAMES
        remaining = self._blocksize - first
        if remaining:
            end = self._input_length + remaining
            self._input[self._input_length : end] = block[first:]
            self._input_length = end

    def _infer(self) -> None:
        np.multiply(self._input, self._window, out=self._windowed)
        spectrum = np.fft.rfft(self._windowed, n=_WINDOW_FRAMES)
        spectrum_ri = np.stack(
            (spectrum.real.astype(np.float32), spectrum.imag.astype(np.float32)), axis=-1
        )[np.newaxis, np.newaxis, :, :]

        started = self._clock_ns()
        enhanced, self._state = self._runtime.session.run(
            [self._runtime.output_spec_name, self._runtime.output_state_name],
            {
                self._runtime.input_spec_name: spectrum_ri,
                self._runtime.input_state_name: self._state,
            },
        )
        self._record_cost(self._clock_ns() - started)

        frame = enhanced[0, 0]
        complex_frame = frame[:, 0] + 1j * frame[:, 1]
        reconstructed = np.fft.irfft(complex_frame, n=_WINDOW_FRAMES)
        np.multiply(reconstructed, self._window, out=self._time_frame)
        np.add(self._overlap, self._time_frame, out=self._overlap)
        self._wet_fifo.append(self._overlap[:_HOP_FRAMES])
        self._overlap[:_HOP_FRAMES] = self._overlap[_HOP_FRAMES:]
        self._overlap[_HOP_FRAMES:] = 0.0

    def _record_cost(self, nanoseconds: int) -> None:
        self._costs[self._cost_cursor] = nanoseconds / 1_000_000.0
        self._cost_cursor = (self._cost_cursor + 1) % self._costs.size
        self._cost_count = min(self._cost_count + 1, self._costs.size)

    def reset(self) -> None:
        self._state = self._runtime.initial_state.copy()
        self._input.fill(0.0)
        self._input_length = 0
        self._overlap.fill(0.0)
        self._wet_fifo.reset()
        self._dry_fifo.reset()

    def set_param(self, name: str, value: float) -> None:
        if name != _MIX.name:
            raise KeyError(f"{self.kind!r} has no parameter {name!r}")
        self._mix = _MIX.clamp(value)

    def params(self) -> dict[str, float]:
        return {_MIX.name: self._mix}

    def param_specs(self) -> tuple[ParamSpec, ...]:
        return (_MIX,)

    @property
    def latency_frames(self) -> int:
        return _WINDOW_FRAMES

    @property
    def cost_ms(self) -> float:
        if not self._cost_count:
            return 0.0
        return float(np.percentile(self._costs[: self._cost_count], 99))


def _build_runtime(model_path: Path) -> RuntimeModel:
    if not model_path.is_file():
        raise FileNotFoundError(f"ONNX model file not found: {model_path}")
    ort: Any = import_module("onnxruntime")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session: Any = ort.InferenceSession(
        str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
    )
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if len(inputs) < 2 or len(outputs) < 2:
        raise ValueError("expected a streaming ONNX model with two inputs and two outputs")
    metadata: Mapping[str, str] = session.get_modelmeta().custom_metadata_map
    required = ("state_size", "erb_norm_state_size", "spec_norm_state_size")
    try:
        state_size, erb_size, spec_size = (int(metadata[name]) for name in required)
        erb = np.fromstring(metadata["erb_norm_init"], sep=",", dtype=np.float32)
        spec = np.fromstring(metadata["spec_norm_init"], sep=",", dtype=np.float32)
    except KeyError as exc:
        raise ValueError(f"ONNX model is missing required metadata key {exc.args[0]!r}") from exc
    initial_state = np.zeros(state_size, dtype=np.float32)
    initial_state[:erb_size] = erb
    initial_state[erb_size : erb_size + spec_size] = spec
    return RuntimeModel(
        session=session,
        initial_state=np.ascontiguousarray(initial_state),
        input_spec_name=inputs[0].name,
        input_state_name=inputs[1].name,
        output_spec_name=outputs[0].name,
        output_state_name=outputs[1].name,
    )


def load_neural(
    model_path: Path, *, blocksize: int, params: Mapping[str, float] | None = None
) -> NeuralEffect:
    """Build the expensive ONNX session. Call this from an effect-load worker."""
    effect = NeuralEffect(_build_runtime(model_path), blocksize=blocksize)
    for name, value in (params or {}).items():
        effect.set_param(name, value)
    return effect


def default_model_path() -> Path:
    """Where a checkout and a frozen build both place the bundled model."""
    return Path(__file__).with_name("models") / _MODEL_FILENAME
