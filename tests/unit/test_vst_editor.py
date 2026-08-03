import json
import threading
from pathlib import Path
from typing import Any

import pytest

from soundboard.effects.vst_editor import main, run_editor


class FakeParameter:
    def __init__(self, type_: type) -> None:
        self.type = type_


class FakePlugin:
    """A plugin whose editor window is a callable the test controls."""

    def __init__(self, show: Any = None) -> None:
        self.parameters = {"mix": FakeParameter(float), "bypass": FakeParameter(bool)}
        self.mix = 0.5
        self.bypass = False
        self.is_effect = True
        self.name = "Fake"
        self._show = show
        self.applied_before_show: dict[str, Any] = {}

    def show_editor(self, close_event: Any = None) -> None:
        self.applied_before_show = {"mix": self.mix, "bypass": self.bypass}
        self.close_event = close_event
        if self._show is not None:
            self._show(self)


def test_the_window_opens_with_the_values_the_chain_is_already_using() -> None:
    """The editor is a second instance of the plugin, so it starts where the first
    one is — otherwise opening the window would silently undo every knob."""
    plugin = FakePlugin()

    run_editor(plugin, {"mix": 0.25, "bypass": True}, lambda params: None)

    assert plugin.applied_before_show == {"mix": 0.25, "bypass": True}


def test_a_knob_moved_in_the_plugin_window_is_reported_while_it_is_open() -> None:
    """Waiting for the window to close would mean tuning by ear against silence."""
    seen = threading.Event()
    reported: list[dict[str, Any]] = []

    def sink(params: dict[str, Any]) -> None:
        reported.append(params)
        if params.get("mix") == 0.9:
            seen.set()

    def show(plugin: FakePlugin) -> None:
        plugin.mix = 0.9
        assert seen.wait(5.0), "the window closed before the change was reported"

    run_editor(FakePlugin(show), {}, sink, poll=0.005)

    assert {"mix": 0.9} in reported


def test_an_untouched_window_costs_nothing_to_watch() -> None:
    """Reading every parameter is 4.5 ms on a real plugin, twenty times a second,
    for as long as a window is open — on a machine with an audio callback due every
    5.33 ms. raw_state is 0.01 ms and says whether there is anything to read."""
    held = threading.Event()
    plugin = _StatefulPlugin(lambda _: held.wait(0.3))

    run_editor(plugin, {}, lambda params: None, poll=0.005)

    assert plugin.parameter_reads <= 2, "one before the window, one as it closes"


def test_a_plugin_with_no_state_to_compare_is_still_watched() -> None:
    """Then every poll reads the parameters, which is what this did before the
    shortcut existed: slower, and still correct."""
    seen = threading.Event()
    reported: list[dict[str, Any]] = []

    def sink(params: dict[str, Any]) -> None:
        reported.append(params)
        if params.get("mix") == 0.8:
            seen.set()

    def show(plugin: _StatefulPlugin) -> None:
        plugin.mix = 0.8
        assert seen.wait(5.0), "a plugin without raw_state stopped being watched"

    run_editor(_StatefulPlugin(show, stateful=False), {}, sink, poll=0.005)

    assert {"mix": 0.8} in reported


class _StatefulPlugin(FakePlugin):
    """A plugin that counts parameter reads and whose state blob tracks its knobs."""

    parameter_reads = 0

    def __init__(self, show: Any = None, stateful: bool = True) -> None:
        self._stateful = stateful
        super().__init__(show)

    @property
    def parameters(self) -> dict[str, FakeParameter]:
        self.parameter_reads += 1
        return self._parameters

    @parameters.setter
    def parameters(self, value: dict[str, FakeParameter]) -> None:
        self._parameters = value

    @property
    def raw_state(self) -> bytes:
        if not self._stateful:
            raise AttributeError("this plugin has no raw_state")
        return repr((self.mix, self.bypass)).encode("utf-8")


def test_nothing_is_reported_while_the_window_sits_untouched() -> None:
    def show(plugin: FakePlugin) -> None:
        pass

    reported: list[dict[str, Any]] = []
    run_editor(FakePlugin(show), {"mix": 0.5}, reported.append, poll=0.001)

    assert reported == [{"mix": 0.5, "bypass": False}], "only the closing state"


def test_the_state_at_the_moment_the_window_closes_is_always_reported() -> None:
    """A change made in the last few milliseconds falls between two polls; the chain
    would then keep playing a value the user cannot see any more."""

    def show(plugin: FakePlugin) -> None:
        plugin.mix = 0.75

    reported: list[dict[str, Any]] = []
    run_editor(FakePlugin(show), {}, reported.append, poll=30.0)

    assert reported[-1] == {"mix": 0.75, "bypass": False}


def test_the_window_can_be_closed_by_whoever_opened_it() -> None:
    """pedalboard's own way out of the message loop, and the only one that does not
    need the user: it is what closes the window when the app itself goes down."""
    closing = threading.Event()
    plugin = FakePlugin()

    run_editor(plugin, {}, lambda params: None, poll=0.001, close=closing)

    assert plugin.close_event is closing


def test_the_watcher_does_not_outlive_the_window() -> None:
    before = threading.active_count()

    run_editor(FakePlugin(), {}, lambda params: None, poll=0.001)

    assert threading.active_count() == before


def test_main_loads_the_plugin_named_on_the_command_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded: list[str] = []

    def loader(path: str) -> FakePlugin:
        loaded.append(path)
        return FakePlugin()

    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps({"params": {"mix": 0.25}})))

    assert main([str(Path("plugin.vst3"))], loader=loader) == 0
    assert loaded == [str(Path("plugin.vst3"))]


def test_main_writes_one_json_object_per_line_for_the_parent_to_read(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def show(plugin: FakePlugin) -> None:
        plugin.mix = 0.75

    monkeypatch.setattr("sys.stdin", _Stdin(""))

    assert main(["plugin.vst3"], loader=lambda path: FakePlugin(show)) == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert json.loads(lines[-1]) == {"params": {"mix": 0.75, "bypass": False}}


def test_main_applies_the_parameters_the_parent_sends_on_stdin(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = FakePlugin()
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps({"params": {"mix": 0.1}})))

    assert main(["plugin.vst3"], loader=lambda path: plugin) == 0
    assert plugin.applied_before_show["mix"] == 0.1


def test_main_closes_the_window_when_the_parent_lets_go_of_stdin(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The only cue that reaches a window sitting in its own message loop. Without
    it the parent has to kill this process, and the last thing the user did in the
    window never gets back to the chain."""
    showing = threading.Event()

    def show(plugin: FakePlugin) -> None:
        showing.set()
        assert plugin.close_event is not None
        assert plugin.close_event.wait(5.0), "stdin closed but the window stayed up"

    monkeypatch.setattr("sys.stdin", _Stdin("", closes=showing))

    assert main(["plugin.vst3"], loader=lambda path: FakePlugin(show)) == 0


def test_main_reports_a_plugin_that_will_not_load_on_stderr(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent shows this text in a toast, so it has to be the message and not a
    traceback the user cannot act on."""

    def loader(path: str) -> FakePlugin:
        raise RuntimeError("not a VST3")

    monkeypatch.setattr("sys.stdin", _Stdin(""))

    assert main(["plugin.vst3"], loader=loader) == 1
    captured = capsys.readouterr()
    assert "not a VST3" in captured.err
    assert captured.out == ""


class _Stdin:
    """The parent's end of the pipe: one line of parameters, then silence until it
    lets go — which is how the parent asks for the window to close."""

    def __init__(self, text: str, closes: threading.Event | None = None) -> None:
        self._text = text
        self._closes = closes

    def readline(self) -> str:
        return self._text

    def read(self) -> str:
        if self._closes is not None:
            self._closes.wait(5.0)
        return ""
