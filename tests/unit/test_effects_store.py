"""The chain on disk: what gets written, what comes back, and what does not build."""

from __future__ import annotations

from pathlib import Path

from soundboard.ui.effects_store import (
    EffectEntry,
    LoadedEffect,
    build_effects,
    default_effects_path,
    load_effects,
    save_effects,
)
from soundboard.ui.layout_store import default_layout_path


def test_saved_effects_come_back_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "effects.json"
    entries = [
        EffectEntry(kind="highpass", params={"cutoff_frequency_hz": 120.0}),
        EffectEntry(kind="reverb", enabled=False, params={"wet_level": 0.2}),
    ]

    save_effects(path, entries)

    # Order is the signal path and the bypass flag is a user decision, so both
    # have to survive a restart along with the knob positions.
    assert load_effects(path) == entries


def test_loading_an_absent_file_gives_no_effects(tmp_path: Path) -> None:
    # First launch. An empty chain is what the engine already holds, so there is
    # nothing to distinguish from "never configured".
    assert load_effects(tmp_path / "effects.json") == []


def test_build_applies_the_saved_parameters() -> None:
    built = build_effects([EffectEntry(kind="gain", params={"gain_db": -6.0})])

    assert built[0].effect is not None
    assert built[0].effect.params()["gain_db"] == -6.0
    assert built[0].error is None


def test_a_block_whose_kind_no_longer_exists_survives_as_an_error() -> None:
    entries = [
        EffectEntry(kind="gain"),
        EffectEntry(kind="flanger"),
        EffectEntry(kind="limiter"),
    ]

    built = build_effects(entries)

    # Dropping it would silently reorder the rack and lose the block on the next
    # save; the user has to see which one broke and why, and the blocks around it
    # have to stay where they were.
    assert [row.entry.kind for row in built] == ["gain", "flanger", "limiter"]
    assert built[1].effect is None
    assert built[1].error is not None
    assert "flanger" in built[1].error


def test_the_neural_block_is_left_for_the_background_loader() -> None:
    built = build_effects([EffectEntry(kind="neural", params={"mix": 0.7})])

    assert built == [
        LoadedEffect(EffectEntry(kind="neural", params={"mix": 0.7}), loading=True)
    ]


def test_the_chain_file_sits_beside_the_layout() -> None:
    assert default_effects_path().parent == default_layout_path().parent
    assert default_effects_path().name == "effects.json"
