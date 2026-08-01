"""Serializes the microphone effects chain: which blocks, in what order, set how.

On disk rather than in Supabase, for the reason ``layout_store`` gives: the chain
describes this machine and this microphone, not the account. A block that will not
build is kept as a row with its error rather than dropped, so the rack the user
sees always matches the file.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

from soundboard.effects.chain import Effect
from soundboard.effects.registry import create


@dataclass(frozen=True)
class EffectEntry:
    """One saved block: what it is, whether it runs, and where its knobs sit."""

    kind: str
    enabled: bool = True
    params: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedEffect:
    """A saved entry and the block it produced, or why it produced none."""

    entry: EffectEntry
    effect: Effect | None = None
    error: str | None = None


def build_effects(entries: Iterable[EffectEntry]) -> list[LoadedEffect]:
    """Turn saved entries into blocks, one row per entry, failures included.

    An entry can name a kind this build no longer has -- a file written by a newer
    version, or by hand. That is a row the user has to see and delete themselves;
    building the rest of the chain around it is the whole point of not raising.
    """
    built = []
    for entry in entries:
        try:
            built.append(LoadedEffect(entry, effect=create(entry.kind, entry.params)))
        except KeyError as exc:
            built.append(LoadedEffect(entry, error=str(exc.args[0])))
    return built


def _entry_to_dict(entry: EffectEntry) -> dict[str, Any]:
    return {"kind": entry.kind, "enabled": entry.enabled, "params": dict(entry.params)}


def _entry_from_dict(data: dict[str, Any]) -> EffectEntry:
    return EffectEntry(
        kind=data["kind"],
        enabled=data.get("enabled", True),
        params={str(name): float(value) for name, value in data.get("params", {}).items()},
    )


def save_effects(path: Path, entries: Iterable[EffectEntry]) -> None:
    data = {"effects": [_entry_to_dict(entry) for entry in entries]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_effects(path: Path) -> list[EffectEntry]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [_entry_from_dict(entry) for entry in data["effects"]]


def default_effects_path() -> Path:
    return Path(platformdirs.user_config_dir("soundboard")) / "effects.json"
