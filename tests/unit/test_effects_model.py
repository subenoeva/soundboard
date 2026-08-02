"""The rack as the UI sees it: rows, reordering, knobs, and what reaches the engine."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QThreadPool

from soundboard.effects.chain import Effect, EffectChain
from soundboard.effects.params import ParamSpec, ParamValue
from soundboard.effects.registry import BUILT_INS
from soundboard.ui.effects_model import EffectsModel
from soundboard.ui.effects_store import (
    EffectEntry,
    LoadedEffect,
    build_effects,
    load_effects,
)


class FakeEngine:
    """Records what the model pushes, and applies knob moves as the callback would."""

    def __init__(self) -> None:
        self.chains: list[EffectChain] = []
        self.param_calls: list[tuple[Effect, str, ParamValue]] = []

    def set_chain(self, chain: EffectChain) -> None:
        self.chains.append(chain)

    def set_param(self, effect: Effect, name: str, value: ParamValue) -> None:
        self.param_calls.append((effect, name, value))
        effect.set_param(name, value)


def _model(
    tmp_path: Path, entries: list[EffectEntry] | None = None
) -> tuple[EffectsModel, FakeEngine]:
    engine = FakeEngine()
    rows = build_effects(entries or [])
    model = EffectsModel(engine, rows, tmp_path / "effects.json")
    return model, engine


def test_the_saved_chain_reaches_the_engine_at_startup(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(
        tmp_path, [EffectEntry(kind="highpass"), EffectEntry(kind="compressor")]
    )

    # Nothing else knows what the file said, so the model installing the chain it
    # was built with is the only thing that makes a restart sound like the session
    # before it.
    assert model.rowCount() == 2
    assert [slot.effect.kind for slot in engine.chains[-1].slots] == ["highpass", "compressor"]


def test_a_row_that_did_not_build_stays_out_of_the_chain(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(tmp_path, [EffectEntry(kind="flanger"), EffectEntry(kind="gain")])

    # The row is still there for the user to look at and delete, but there is no
    # block to run, and the rest of the rack has to work around it.
    assert model.rowCount() == 2
    assert [slot.effect.kind for slot in engine.chains[-1].slots] == ["gain"]


def test_a_disabled_row_is_bypassed_rather_than_left_out(qtbot: Any, tmp_path: Path) -> None:
    _, engine = _model(tmp_path, [EffectEntry(kind="gain", enabled=False)])

    # A bypassed block keeps its slot: it holds state the user gets back when they
    # switch it on again, and dropping it would rebuild it instead.
    slots = engine.chains[-1].slots
    assert [(slot.effect.kind, slot.enabled) for slot in slots] == [("gain", False)]


def test_the_rows_carry_what_the_rack_draws(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(tmp_path, [EffectEntry(kind="highpass")])
    row = model.index(0)

    assert model.data(row, EffectsModel.KIND_ROLE) == "highpass"
    # The label comes from the registry rather than the file: the file stores the
    # kind, and the text next to it is ours to change.
    assert model.data(row, EffectsModel.LABEL_ROLE) == "High-pass"
    assert model.data(row, EffectsModel.ENABLED_ROLE) is True
    assert model.data(row, EffectsModel.ERROR_ROLE) == ""


def test_the_summary_says_where_the_knobs_sit(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(
        tmp_path, [EffectEntry(kind="highpass", params={"cutoff_frequency_hz": 120.0})]
    )

    # The block face is too small for the parameter panel, so it carries the one
    # line that tells the user what this block is currently doing.
    assert model.data(model.index(0), EffectsModel.SUMMARY_ROLE) == "Cutoff 120 Hz"


def test_a_row_that_did_not_build_shows_why(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(tmp_path, [EffectEntry(kind="flanger")])
    row = model.index(0)

    # Without the reason on the row, a block that vanished from the build looks
    # like a bug in the rack rather than a file naming something we do not have.
    assert "flanger" in model.data(row, EffectsModel.ERROR_ROLE)
    assert model.data(row, EffectsModel.SUMMARY_ROLE) == ""
    assert model.data(row, EffectsModel.LABEL_ROLE) == "flanger"


def test_latency_is_reported_in_milliseconds(qtbot: Any, tmp_path: Path) -> None:
    model = EffectsModel(
        FakeEngine(),
        [LoadedEffect(EffectEntry(kind="neural"), effect=_DelayedEffect(960))],
        tmp_path / "effects.json",
    )

    # Milliseconds are what the rack prints; frames are what the block knows, and
    # 960 of them is the neural block's 20 ms.
    assert model.data(model.index(0), EffectsModel.LATENCY_MS_ROLE) == 20.0


def test_add_appends_a_block_and_installs_the_new_chain(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(tmp_path, [EffectEntry(kind="gain")])

    model.add("limiter")

    assert model.data(model.index(1), EffectsModel.KIND_ROLE) == "limiter"
    assert [slot.effect.kind for slot in engine.chains[-1].slots] == ["gain", "limiter"]


def test_an_added_block_arrives_with_the_defaults_it_declares(
    qtbot: Any, tmp_path: Path
) -> None:
    model, _ = _model(tmp_path)

    model.add("gate")

    # A block dragged in has to improve the microphone immediately, and the rack
    # has to show the settings it came up with rather than an empty face.
    assert load_effects(tmp_path / "effects.json")[0].params["threshold_db"] == -45.0
    assert model.data(model.index(0), EffectsModel.SUMMARY_ROLE).startswith("Threshold -45 dB")


def test_add_reports_a_kind_it_cannot_build_instead_of_raising(
    qtbot: Any, tmp_path: Path
) -> None:
    model, engine = _model(tmp_path)
    messages: list[str] = []
    model.toast.connect(messages.append)

    model.add("flanger")

    # The palette only offers kinds that exist, so this is a QML typo or a stale
    # build -- neither is worth taking the window down for.
    assert model.rowCount() == 0
    assert len(engine.chains) == 1
    assert messages and "flanger" in messages[0]


def test_remove_drops_the_row_and_installs_the_new_chain(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(tmp_path, [EffectEntry(kind="gain"), EffectEntry(kind="limiter")])

    model.remove(0)

    assert [slot.effect.kind for slot in engine.chains[-1].slots] == ["limiter"]
    assert [entry.kind for entry in load_effects(tmp_path / "effects.json")] == ["limiter"]


def test_a_reorder_carries_the_blocks_across_by_identity(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(
        tmp_path,
        [EffectEntry(kind="gate"), EffectEntry(kind="gain"), EffectEntry(kind="limiter")],
    )
    before = [slot.effect for slot in engine.chains[-1].slots]

    model.move(2, 0)

    # Only the container is rebuilt. Building the blocks again would reset the
    # state they carry -- a reverb tail cut, and the neural block's prefill gone
    # for 20 audible milliseconds -- on every drag.
    after = [slot.effect for slot in engine.chains[-1].slots]
    assert [slot.effect.kind for slot in engine.chains[-1].slots] == ["limiter", "gate", "gain"]
    assert after == [before[2], before[0], before[1]]


def test_a_reorder_is_what_the_next_launch_reads_back(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(tmp_path, [EffectEntry(kind="gate"), EffectEntry(kind="gain")])

    model.move(0, 1)

    assert [entry.kind for entry in load_effects(tmp_path / "effects.json")] == ["gain", "gate"]


def test_bypassing_a_block_keeps_the_block(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(tmp_path, [EffectEntry(kind="reverb")])
    before = engine.chains[-1].slots[0].effect

    model.set_enabled(0, False)

    # The switch is a slot flag, not a teardown: the tail the reverb is holding is
    # still there when the user switches it back on.
    slot = engine.chains[-1].slots[0]
    assert (slot.effect, slot.enabled) == (before, False)
    assert model.data(model.index(0), EffectsModel.ENABLED_ROLE) is False
    assert load_effects(tmp_path / "effects.json")[0].enabled is False


def test_a_knob_move_travels_through_the_engine(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(tmp_path, [EffectEntry(kind="gain")])
    effect = engine.chains[-1].slots[0].effect

    model.set_param(0, "gain_db", -6.0)

    # Reaching into the plugin from here would race the callback, so the move is
    # queued like everything else -- and the chain is untouched, or a slider drag
    # would retire one chain per frame.
    assert engine.param_calls == [(effect, "gain_db", -6.0)]
    assert len(engine.chains) == 1


def test_a_knob_move_is_clamped_before_it_is_written_down(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(tmp_path, [EffectEntry(kind="gain")])

    model.set_param(0, "gain_db", 900.0)

    # The plugin clamps whatever it is handed, so saving the raw number would
    # give a file that no longer describes the sound the user is hearing.
    assert load_effects(tmp_path / "effects.json")[0].params["gain_db"] == 24.0
    assert model.data(model.index(0), EffectsModel.SUMMARY_ROLE) == "Gain 24 dB"


def test_a_knob_the_block_does_not_have_is_ignored(qtbot: Any, tmp_path: Path) -> None:
    model, engine = _model(tmp_path, [EffectEntry(kind="gain")])

    model.set_param(0, "wet_level", 0.5)

    # A stale panel bound to the block that used to be selected. Passing it on
    # would raise from inside the audio callback, which nothing there catches.
    assert engine.param_calls == []


def test_the_parameter_panel_reads_the_knobs_off_the_block(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(
        tmp_path, [EffectEntry(kind="highpass", params={"cutoff_frequency_hz": 120.0})]
    )

    # QML cannot see a ParamSpec, and for a VST3 the registry will not know the
    # knobs either -- only the block does.
    assert model.param_specs(0) == [
        {
            "name": "cutoff_frequency_hz",
            "label": "Cutoff",
            "minimum": 20.0,
            "maximum": 500.0,
            "value": 120.0,
            "unit": "Hz",
            "type": "float",
            "choices": [],
        }
    ]


def test_a_knob_the_saved_file_never_had_still_reports_its_position(
    qtbot: Any, tmp_path: Path
) -> None:
    model, _ = _model(tmp_path, [EffectEntry(kind="gate", params={"ratio": 4.0})])

    # A file written before a knob existed, or edited by hand. The block came up
    # with a real value for it either way, and that is the one to show and save.
    assert model.param_specs(0)[0]["value"] == -45.0


def test_opening_the_rack_leaves_the_file_alone(qtbot: Any, tmp_path: Path) -> None:
    _model(tmp_path, [EffectEntry(kind="gate")])

    # Only a change the user made is worth a write. The rows come up filled in
    # from the blocks that built, so saving here would rewrite the file on every
    # launch with settings nobody touched.
    assert not (tmp_path / "effects.json").exists()


def test_the_palette_offers_every_built_in(qtbot: Any, tmp_path: Path) -> None:
    model, _ = _model(tmp_path)

    catalog = model.catalog()

    # The palette is drawn from the registry rather than listed again in QML,
    # where a new block would have to be remembered twice.
    assert {row["kind"] for row in catalog} == set(BUILT_INS) | {"neural"}
    assert {"kind": "reverb", "label": "Reverb"} in catalog
    assert {"kind": "neural", "label": "Reducción neural"} in catalog


def test_a_deferred_block_loads_off_the_qt_thread(qtbot: Any, tmp_path: Path) -> None:
    engine = FakeEngine()
    effect = _DelayedEffect(960)
    loader_threads: list[int] = []

    def load(entry: EffectEntry, blocksize: int) -> Effect:
        loader_threads.append(threading.get_ident())
        assert entry.kind == "neural"
        assert blocksize == 256
        return effect

    model = EffectsModel(
        engine,
        [LoadedEffect(EffectEntry(kind="neural"), loading=True)],
        tmp_path / "effects.json",
        load_effect=load,
        blocksize=256,
    )
    row = model.index(0)

    assert model.data(row, EffectsModel.LOADING_ROLE) is True
    assert engine.chains[-1].slots == ()
    assert QThreadPool.globalInstance().waitForDone(5000)
    qtbot.waitUntil(lambda: model.data(row, EffectsModel.LOADING_ROLE) is False)

    assert loader_threads and loader_threads[0] != threading.get_ident()
    slots = engine.chains[-1].slots
    assert len(slots) == 1
    assert next(iter(slots)).effect is effect


def test_finishing_a_neural_load_enables_callback_safe_gc(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "soundboard.ui.effects_model.enable_realtime_gc",
        lambda: calls.append("enable"),
    )
    model = EffectsModel(
        FakeEngine(),
        [LoadedEffect(EffectEntry(kind="neural"), loading=True)],
        tmp_path / "effects.json",
        load_effect=lambda entry, blocksize: _DelayedEffect(960),
    )

    assert QThreadPool.globalInstance().waitForDone(5000)
    qtbot.waitUntil(lambda: not model._active_workers)

    assert calls == ["enable"]


def test_a_deferred_load_failure_stays_visible_on_its_row(
    qtbot: Any, tmp_path: Path
) -> None:
    def fail(entry: EffectEntry, blocksize: int) -> Effect:
        raise RuntimeError("model file is missing")

    model = EffectsModel(
        FakeEngine(),
        [LoadedEffect(EffectEntry(kind="neural"), loading=True)],
        tmp_path / "effects.json",
        load_effect=fail,
    )
    row = model.index(0)

    assert QThreadPool.globalInstance().waitForDone(5000)
    qtbot.waitUntil(lambda: model.data(row, EffectsModel.LOADING_ROLE) is False)

    assert "model file is missing" in model.data(row, EffectsModel.ERROR_ROLE)
    assert model.data(row, EffectsModel.ENABLED_ROLE) is False
    assert model.rowCount() == 1


def test_a_retired_model_drops_a_late_effect_result(qtbot: Any, tmp_path: Path) -> None:
    release = threading.Event()
    effect = _DelayedEffect(960)

    def load(entry: EffectEntry, blocksize: int) -> Effect:
        release.wait(2)
        return effect

    engine = FakeEngine()
    model = EffectsModel(
        engine,
        [LoadedEffect(EffectEntry(kind="neural"), loading=True)],
        tmp_path / "effects.json",
        load_effect=load,
    )
    model.detach()
    release.set()

    assert QThreadPool.globalInstance().waitForDone(5000)
    qtbot.wait(10)

    assert all(not chain.slots for chain in engine.chains)


def test_adding_neural_persists_the_loading_row_before_it_finishes(
    qtbot: Any, tmp_path: Path
) -> None:
    release = threading.Event()

    def load(entry: EffectEntry, blocksize: int) -> Effect:
        release.wait(2)
        return _DelayedEffect(960)

    model = EffectsModel(
        FakeEngine(), [], tmp_path / "effects.json", load_effect=load
    )

    model.add("neural")

    assert load_effects(tmp_path / "effects.json") == [EffectEntry(kind="neural")]
    assert model.data(model.index(0), EffectsModel.LOADING_ROLE) is True
    release.set()
    assert QThreadPool.globalInstance().waitForDone(5000)
    qtbot.waitUntil(
        lambda: model.data(model.index(0), EffectsModel.LOADING_ROLE) is False
    )


def test_adding_a_vst_persists_its_path_and_loads_it_in_the_worker(
    qtbot: Any, tmp_path: Path
) -> None:
    effect = _TypedVstEffect()
    model = EffectsModel(
        FakeEngine(),
        [],
        tmp_path / "effects.json",
        load_effect=lambda entry, blocksize: effect,
    )
    path = tmp_path / "Voice.vst3"

    model.add_vst(str(path))

    assert load_effects(tmp_path / "effects.json") == [
        EffectEntry(kind="vst3", plugin_path=str(path))
    ]
    assert model.data(model.index(0), EffectsModel.LOADING_ROLE) is True
    assert QThreadPool.globalInstance().waitForDone(5000)
    qtbot.waitUntil(
        lambda: model.data(model.index(0), EffectsModel.LOADING_ROLE) is False
    )
    assert model.data(model.index(0), EffectsModel.LABEL_ROLE) == "Voice shaper"


def test_the_parameter_panel_receives_vst_parameter_types(qtbot: Any, tmp_path: Path) -> None:
    model = EffectsModel(
        FakeEngine(),
        [LoadedEffect(EffectEntry(kind="vst3"), effect=_TypedVstEffect())],
        tmp_path / "effects.json",
    )

    assert model.param_specs(0) == [
        {
            "name": "bypass",
            "label": "Bypass",
            "minimum": 0.0,
            "maximum": 1.0,
            "value": False,
            "unit": "",
            "type": "bool",
            "choices": [],
        },
        {
            "name": "mode",
            "label": "Mode",
            "minimum": 0.0,
            "maximum": 2.0,
            "value": "Clean",
            "unit": "",
            "type": "choice",
            "choices": ["Clean", "Warm", "Bright"],
        },
    ]


class _DelayedEffect:
    """A block that delays the signal, which none of the built-ins do."""

    kind = "neural"

    def __init__(self, latency_frames: int) -> None:
        self._latency_frames = latency_frames

    def process(self, block: Any) -> None:
        pass

    def reset(self) -> None:
        pass

    def set_param(self, name: str, value: ParamValue) -> None:
        pass

    def params(self) -> dict[str, ParamValue]:
        return {}

    def param_specs(self) -> tuple[Any, ...]:
        return ()

    @property
    def latency_frames(self) -> int:
        return self._latency_frames


class _TypedVstEffect:
    kind = "vst3"
    label = "Voice shaper"

    def __init__(self) -> None:
        self._params: dict[str, ParamValue] = {"bypass": False, "mode": "Clean"}

    def process(self, block: Any) -> None:
        pass

    def reset(self) -> None:
        pass

    def set_param(self, name: str, value: ParamValue) -> None:
        self._params[name] = value

    def params(self) -> dict[str, ParamValue]:
        return dict(self._params)

    def param_specs(self) -> tuple[ParamSpec, ...]:
        return (
            ParamSpec("bypass", "Bypass", 0.0, 1.0, False, type="bool"),
            ParamSpec(
                "mode",
                "Mode",
                0.0,
                2.0,
                "Clean",
                type="choice",
                choices=("Clean", "Warm", "Bright"),
            ),
        )

    @property
    def latency_frames(self) -> int:
        return 0
