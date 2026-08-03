"""Presentation helpers shared by the effects list model and its QML view."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from soundboard.effects.params import ParamValue
from soundboard.effects.registry import label_for
from soundboard.ui.effects_store import LoadedEffect


def adopted(row: LoadedEffect) -> LoadedEffect:
    """Fill a saved row with every parameter reported by its loaded block."""
    if row.effect is None:
        return row
    return replace(row, entry=replace(row.entry, params=row.effect.params()))


def parameter_rows(row: LoadedEffect) -> list[dict[str, Any]]:
    """Describe one effect's controls in values QML can consume."""
    if row.effect is None:
        return []
    return [
        {
            "name": spec.name,
            "label": spec.label,
            "minimum": spec.minimum,
            "maximum": spec.maximum,
            "value": row.entry.params.get(spec.name, spec.default),
            "unit": spec.unit,
            "type": spec.type,
            "choices": list(spec.choices),
        }
        for spec in row.effect.param_specs()
    ]


def row_label(row: LoadedEffect) -> str:
    effect_label = getattr(row.effect, "label", None)
    if effect_label:
        return str(effect_label)
    if row.entry.kind == "vst3" and row.entry.plugin_path:
        return Path(row.entry.plugin_path).stem
    return label_for(row.entry.kind)


def summary(row: LoadedEffect) -> str:
    if row.effect is None:
        return ""
    params = row.entry.params
    return " · ".join(
        f"{spec.label} {_format_param(params.get(spec.name, spec.default))}"
        f"{' ' + spec.unit if spec.unit else ''}"
        for spec in row.effect.param_specs()
    )


def _format_param(value: ParamValue) -> str:
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, float):
        return f"{value:g}"
    return value
