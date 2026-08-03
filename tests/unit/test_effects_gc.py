"""Process-wide GC control while ONNX allocations happen in the callback."""

from __future__ import annotations

import gc

from pytest import MonkeyPatch

from soundboard.effects import realtime_gc


def test_enabling_realtime_gc_freezes_once_and_stops_automatic_collections(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(gc, "isenabled", lambda: True)
    monkeypatch.setattr(gc, "freeze", lambda: calls.append("freeze"))
    monkeypatch.setattr(gc, "disable", lambda: calls.append("disable"))
    monkeypatch.setattr(realtime_gc, "_active", False)

    realtime_gc.enable()
    realtime_gc.enable()

    assert calls == ["freeze", "disable"]


def test_manual_collection_only_runs_while_realtime_gc_is_active(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(gc, "collect", lambda: calls.append("collect"))
    monkeypatch.setattr(realtime_gc, "_active", False)

    realtime_gc.collect()
    monkeypatch.setattr(realtime_gc, "_active", True)
    realtime_gc.collect()

    assert calls == ["collect"]


def test_restoring_reenables_gc_only_if_it_was_enabled_before(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(gc, "enable", lambda: calls.append("enable"))
    monkeypatch.setattr(realtime_gc, "_active", True)
    monkeypatch.setattr(realtime_gc, "_was_enabled", True)

    realtime_gc.restore()
    realtime_gc.restore()

    assert calls == ["enable"]
