"""The adapter that exposes an arbitrary VST3 through the Effect protocol."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from soundboard.effects.vst import VstEffect, load_vst


@dataclass
class FakeParameter:
    name: str
    type: type
    min_value: float | bool | None
    max_value: float | bool | None
    valid_values: list[float | bool | str]
    label: str | None = None


class FakePlugin:
    def __init__(self) -> None:
        self.is_effect = True
        self.name = "Example Voice FX"
        self.reported_latency_samples = 0
        self.drive = 2.5
        self.bypass = False
        self.mode = "Clean"
        self.parameters = {
            "drive": FakeParameter("Drive", float, 0.0, 10.0, [0.0, 10.0], "dB"),
            "bypass": FakeParameter("Bypass", bool, False, True, [False, True]),
            "mode": FakeParameter("Mode", str, None, None, ["Clean", "Warm", "Bright"]),
        }
        self.process_calls: list[tuple[int, bool]] = []
        self.reset_calls = 0

    def process(
        self, block: np.ndarray, samplerate: int, *, reset: bool
    ) -> np.ndarray:
        self.process_calls.append((samplerate, reset))
        return block * 0.5

    def reset(self) -> None:
        self.reset_calls += 1


def _load(tmp_path: Path, plugin: FakePlugin | None = None) -> tuple[VstEffect, FakePlugin]:
    path = tmp_path / "Example Voice FX.vst3"
    path.touch()
    plugin = plugin or FakePlugin()
    effect = load_vst(path, loader=lambda _: plugin)
    return effect, plugin


def test_vst_parameters_keep_the_types_and_ranges_the_plugin_reports(tmp_path: Path) -> None:
    effect, _ = _load(tmp_path)

    specs = effect.param_specs()

    assert [(spec.name, spec.type, spec.default) for spec in specs] == [
        ("drive", "float", 2.5),
        ("bypass", "bool", False),
        ("mode", "choice", "Clean"),
    ]
    assert specs[0].minimum == 0.0
    assert specs[0].maximum == 10.0
    assert specs[0].unit == "dB"
    assert specs[2].choices == ("Clean", "Warm", "Bright")


def test_boolean_parameters_use_the_type_declared_by_pedalboard(tmp_path: Path) -> None:
    class WrappedBool:
        def __init__(self, value: bool) -> None:
            self._value = value

        def __bool__(self) -> bool:
            return self._value

    plugin = FakePlugin()
    plugin.bypass = WrappedBool(False)  # type: ignore[assignment]

    effect, _ = _load(tmp_path, plugin)

    assert effect.params()["bypass"] is False
    assert effect.param_specs()[1].default is False


def test_saved_vst_parameters_are_applied_after_loading(tmp_path: Path) -> None:
    effect, plugin = _load(tmp_path)
    path = tmp_path / "Example Voice FX.vst3"

    effect = load_vst(
        path,
        params={"drive": 7.0, "bypass": True, "mode": "Warm"},
        loader=lambda _: plugin,
    )

    assert effect.params() == {"drive": 7.0, "bypass": True, "mode": "Warm"}


def test_vst_processing_is_in_place_and_keeps_plugin_state(tmp_path: Path) -> None:
    effect, plugin = _load(tmp_path)
    block = np.ones(256, dtype=np.float32)

    effect.process(block)

    assert np.array_equal(block, np.full(256, 0.5, dtype=np.float32))
    assert plugin.process_calls == [(48_000, False)]


def test_reported_plugin_latency_is_prefilled_instead_of_shortening_a_block(
    tmp_path: Path,
) -> None:
    class DelayedPlugin(FakePlugin):
        def __init__(self) -> None:
            super().__init__()
            self.reported_latency_samples = 64
            self.first = True

        def process(
            self, block: np.ndarray, samplerate: int, *, reset: bool
        ) -> np.ndarray:
            if self.first:
                self.first = False
                return np.full(192, 0.5, dtype=np.float32)
            return np.full(256, 0.5, dtype=np.float32)

    effect, _ = _load(tmp_path, DelayedPlugin())
    block = np.ones(256, dtype=np.float32)

    effect.process(block)

    assert effect.latency_frames == 64
    assert np.array_equal(block[:64], np.zeros(64, dtype=np.float32))
    assert np.array_equal(block[64:], np.full(192, 0.5, dtype=np.float32))


def test_buffering_is_inferred_when_a_plugin_does_not_report_latency(
    tmp_path: Path,
) -> None:
    class BufferingPlugin(FakePlugin):
        def process(
            self, block: np.ndarray, samplerate: int, *, reset: bool
        ) -> np.ndarray:
            return np.full(192, 0.5, dtype=np.float32)

    effect, _ = _load(tmp_path, BufferingPlugin())
    block = np.ones(256, dtype=np.float32)

    effect.process(block)

    assert effect.latency_frames == 64
    assert np.array_equal(block[:64], np.zeros(64, dtype=np.float32))
    assert np.array_equal(block[64:], np.full(192, 0.5, dtype=np.float32))


def test_reported_latency_does_not_delay_a_full_plugin_output_twice(
    tmp_path: Path,
) -> None:
    class FullDelayedPlugin(FakePlugin):
        def __init__(self) -> None:
            super().__init__()
            self.reported_latency_samples = 64

        def process(
            self, block: np.ndarray, samplerate: int, *, reset: bool
        ) -> np.ndarray:
            return np.concatenate(
                (np.zeros(64, dtype=np.float32), np.full(192, 0.5, dtype=np.float32))
            )

    effect, _ = _load(tmp_path, FullDelayedPlugin())
    block = np.ones(256, dtype=np.float32)

    effect.process(block)

    assert np.array_equal(
        block,
        np.concatenate(
            (np.zeros(64, dtype=np.float32), np.full(192, 0.5, dtype=np.float32))
        ),
    )


def test_reading_the_parameters_asks_the_plugin_for_its_list_once(tmp_path: Path) -> None:
    """``parameters`` is a property that rebuilds its dictionary on every access —
    3.7 ms for Graillon's 67 of them. Reading it per parameter instead of once made
    a full read 258 ms, which is what the plugin editor polls."""
    plugin = _CountingPlugin()
    effect, _ = _load(tmp_path, plugin)
    plugin.parameter_reads = 0

    values = effect.params()

    assert values == {"drive": 2.5, "bypass": False, "mode": "Clean"}
    assert plugin.parameter_reads == 1


class _CountingPlugin(FakePlugin):
    """A plugin that counts how often its parameter list is asked for."""

    parameter_reads = 0

    @property
    def parameters(self) -> dict[str, FakeParameter]:
        self.parameter_reads += 1
        return self._parameters

    @parameters.setter
    def parameters(self, value: dict[str, FakeParameter]) -> None:
        self._parameters = value


def test_an_instrument_cannot_enter_the_microphone_effect_chain(tmp_path: Path) -> None:
    plugin = FakePlugin()
    plugin.is_effect = False
    path = tmp_path / "synth.vst3"
    path.touch()

    with pytest.raises(ValueError, match="instrument"):
        load_vst(path, loader=lambda _: plugin)


def test_a_missing_vst_path_is_reported_before_loading() -> None:
    with pytest.raises(FileNotFoundError, match="VST3"):
        load_vst(Path("missing.vst3"), loader=lambda _: Any)
