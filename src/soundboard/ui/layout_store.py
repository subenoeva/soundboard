"""Serializes the clip grid: device selection, grid size, and per-cell assignments.

Lives on disk, not in Supabase — the grid is a property of this machine, not the
account (two installs of the same user can have different layouts).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs


@dataclass(frozen=True)
class LocalSource:
    path: str


@dataclass(frozen=True)
class RemoteSource:
    id: str


CellSource = LocalSource | RemoteSource


@dataclass(frozen=True)
class Cell:
    index: int
    source: CellSource
    name: str
    shortcut: str | None = None
    color: str | None = None


@dataclass
class GridLayout:
    """Mutable: cells are reassigned in place as the user edits the grid."""

    rows: int
    cols: int
    mic: str
    out: str
    blocksize: int
    cells: list[Cell] = field(default_factory=list)


def trim_cells_to_bounds(layout: GridLayout) -> list[Cell]:
    """Drop the cells outside ``rows * cols``, in place; return the dropped ones.

    A cell the grid no longer has room for is unreachable: no pad renders it, so it
    can never be cleared or re-bound, yet its global shortcut would keep firing and
    it would survive in the saved layout forever. Shrinking the grid discards it.
    """
    capacity = layout.rows * layout.cols
    dropped = [cell for cell in layout.cells if cell.index >= capacity]
    if dropped:
        layout.cells = [cell for cell in layout.cells if cell.index < capacity]
    return dropped


def _source_to_dict(source: CellSource) -> dict[str, Any]:
    if isinstance(source, LocalSource):
        return {"type": "local", "path": source.path}
    return {"type": "remote", "id": source.id}


def _source_from_dict(data: dict[str, Any]) -> CellSource:
    if data["type"] == "local":
        return LocalSource(path=data["path"])
    if data["type"] == "remote":
        return RemoteSource(id=data["id"])
    raise ValueError(f"unknown cell source type {data['type']!r}")


def _cell_to_dict(cell: Cell) -> dict[str, Any]:
    return {
        "index": cell.index,
        "source": _source_to_dict(cell.source),
        "name": cell.name,
        "shortcut": cell.shortcut,
        "color": cell.color,
    }


def _cell_from_dict(data: dict[str, Any]) -> Cell:
    return Cell(
        index=data["index"],
        source=_source_from_dict(data["source"]),
        name=data["name"],
        shortcut=data.get("shortcut"),
        color=data.get("color"),
    )


def save_layout(path: Path, layout: GridLayout) -> None:
    data = {
        "rows": layout.rows,
        "cols": layout.cols,
        "mic": layout.mic,
        "out": layout.out,
        "blocksize": layout.blocksize,
        "cells": [_cell_to_dict(cell) for cell in layout.cells],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_layout(path: Path) -> GridLayout | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return GridLayout(
        rows=data["rows"],
        cols=data["cols"],
        mic=data["mic"],
        out=data["out"],
        blocksize=data["blocksize"],
        cells=[_cell_from_dict(c) for c in data["cells"]],
    )


def default_layout_path() -> Path:
    return Path(platformdirs.user_config_dir("soundboard")) / "ui_layout.json"
