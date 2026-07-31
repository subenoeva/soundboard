import json
from pathlib import Path

import pytest

from soundboard.ui.layout_store import (
    Cell,
    GridLayout,
    LocalSource,
    RemoteSource,
    default_layout_path,
    load_layout,
    save_layout,
)


def test_load_missing_layout_returns_none(tmp_path: Path) -> None:
    assert load_layout(tmp_path / "missing.json") is None


def test_round_trips_a_layout_with_local_and_remote_cells(tmp_path: Path) -> None:
    path = tmp_path / "ui_layout.json"
    layout = GridLayout(
        rows=2,
        cols=2,
        mic="realtek",
        out="cable",
        blocksize=256,
        cells=[
            Cell(index=0, source=LocalSource(path="clips/airhorn.wav"), name="airhorn",
                 shortcut="<ctrl>+<alt>+1"),
            Cell(index=1, source=RemoteSource(id="abc-123"), name="applause", shortcut=None),
        ],
    )

    save_layout(path, layout)
    loaded = load_layout(path)

    assert loaded == layout


def test_rejects_an_unknown_cell_source_type(tmp_path: Path) -> None:
    path = tmp_path / "ui_layout.json"
    path.write_text(
        '{"rows": 1, "cols": 1, "mic": "m", "out": "o", "blocksize": 256, '
        '"cells": [{"index": 0, "source": {"type": "carrier-pigeon"}, "name": "x", '
        '"shortcut": null}]}'
    )

    with pytest.raises(ValueError, match="carrier-pigeon"):
        load_layout(path)


def test_default_layout_path_lives_under_the_soundboard_config_dir() -> None:
    path = default_layout_path()

    assert path.name == "ui_layout.json"
    assert "soundboard" in str(path).lower()


def test_cell_color_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    layout = GridLayout(rows=1, cols=2, mic="m", out="o", blocksize=256)
    layout.cells = [
        Cell(index=0, source=LocalSource(path="a.wav"), name="a", color="#e8590c"),
        Cell(index=1, source=LocalSource(path="b.wav"), name="b"),
    ]
    save_layout(path, layout)
    loaded = load_layout(path)
    assert loaded is not None
    assert loaded.cells[0].color == "#e8590c"
    assert loaded.cells[1].color is None


def test_legacy_layout_without_color_loads(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps({
        "rows": 1, "cols": 1, "mic": "m", "out": "o", "blocksize": 256,
        "cells": [{"index": 0, "source": {"type": "local", "path": "a.wav"},
                   "name": "a", "shortcut": None}],
    }))
    loaded = load_layout(path)
    assert loaded is not None
    assert loaded.cells[0].color is None
