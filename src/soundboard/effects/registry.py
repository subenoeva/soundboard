"""The catalogue of built-in blocks: what the palette offers and how it builds them.

Defaults here are the ones a voice wants, not the ones pedalboard ships. A block
the user drags in should improve the microphone immediately; a compressor at
ratio 1.0 does nothing and reads as broken.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pedalboard import (
    Compressor,
    Gain,
    HighpassFilter,
    Limiter,
    LowpassFilter,
    NoiseGate,
    Plugin,
    Reverb,
)

from soundboard.effects.params import ParamSpec, ParamValue
from soundboard.effects.pedal import PedalEffect


@dataclass(frozen=True)
class EffectSpec:
    """A block as the palette sees it: a label, a plugin to build and its knobs."""

    kind: str
    label: str
    plugin: Callable[[], Plugin]
    params: tuple[ParamSpec, ...]


def _knob(
    name: str, label: str, minimum: float, maximum: float, default: float, unit: str = ""
) -> ParamSpec:
    return ParamSpec(
        name=name, label=label, minimum=minimum, maximum=maximum, default=default, unit=unit
    )


_ATTACK = _knob("attack_ms", "Attack", 0.1, 100.0, 5.0, "ms")
_RELEASE = _knob("release_ms", "Release", 5.0, 1000.0, 120.0, "ms")

BUILT_INS: Mapping[str, EffectSpec] = MappingProxyType(
    {
        spec.kind: spec
        for spec in (
            EffectSpec(
                kind="gate",
                label="Noise gate",
                plugin=NoiseGate,
                params=(
                    _knob("threshold_db", "Threshold", -80.0, 0.0, -45.0, "dB"),
                    _knob("ratio", "Ratio", 1.0, 20.0, 10.0),
                    _ATTACK,
                    _RELEASE,
                ),
            ),
            EffectSpec(
                kind="compressor",
                label="Compressor",
                plugin=Compressor,
                params=(
                    _knob("threshold_db", "Threshold", -60.0, 0.0, -18.0, "dB"),
                    _knob("ratio", "Ratio", 1.0, 20.0, 3.0),
                    _ATTACK,
                    _RELEASE,
                ),
            ),
            EffectSpec(
                kind="highpass",
                label="High-pass",
                plugin=HighpassFilter,
                params=(_knob("cutoff_frequency_hz", "Cutoff", 20.0, 500.0, 80.0, "Hz"),),
            ),
            EffectSpec(
                kind="lowpass",
                label="Low-pass",
                plugin=LowpassFilter,
                params=(_knob("cutoff_frequency_hz", "Cutoff", 2000.0, 20000.0, 16000.0, "Hz"),),
            ),
            EffectSpec(
                kind="limiter",
                label="Limiter",
                plugin=Limiter,
                params=(
                    _knob("threshold_db", "Ceiling", -24.0, 0.0, -1.0, "dB"),
                    _knob("release_ms", "Release", 5.0, 1000.0, 100.0, "ms"),
                ),
            ),
            EffectSpec(
                kind="gain",
                label="Gain",
                plugin=Gain,
                params=(_knob("gain_db", "Gain", -24.0, 24.0, 0.0, "dB"),),
            ),
            EffectSpec(
                kind="reverb",
                label="Reverb",
                plugin=Reverb,
                params=(
                    _knob("room_size", "Room", 0.0, 1.0, 0.35),
                    _knob("damping", "Damping", 0.0, 1.0, 0.5),
                    _knob("wet_level", "Wet", 0.0, 1.0, 0.15),
                    _knob("dry_level", "Dry", 0.0, 1.0, 0.85),
                    _knob("width", "Width", 0.0, 1.0, 1.0),
                ),
            ),
        )
    }
)


def catalog() -> list[dict[str, str]]:
    """Every block the palette can add, including asynchronously built ones."""
    rows = [{"kind": spec.kind, "label": spec.label} for spec in BUILT_INS.values()]
    rows.append({"kind": "neural", "label": "Reducción neural"})
    return rows


def label_for(kind: str) -> str:
    if kind == "neural":
        return "Reducción neural"
    spec = BUILT_INS.get(kind)
    return spec.label if spec else kind


def create(
    kind: str, params: Mapping[str, ParamValue] | None = None, *, samplerate: int = 48_000
) -> PedalEffect:
    """Build one block, its declared defaults applied and then ``params`` on top.

    Both an unknown kind and an unknown parameter name raise: they mean a stale
    ``effects.json`` or a typo in the table above, and a block that silently comes
    up as something other than what was asked for is worse than one that refuses.
    """
    spec = BUILT_INS.get(kind)
    if spec is None:
        raise KeyError(f"unknown effect kind {kind!r}")
    effect = PedalEffect(spec.kind, spec.plugin(), spec.params, samplerate=samplerate)
    for knob in spec.params:
        effect.set_param(knob.name, knob.default)
    for name, value in (params or {}).items():
        effect.set_param(name, value)
    return effect
