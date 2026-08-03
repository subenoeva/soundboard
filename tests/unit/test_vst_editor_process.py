import sys
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from soundboard.ui.vst_editor_process import LineReader, VstEditor, editor_command

ECHO_STDIN = "import sys; sys.stdout.write(sys.stdin.readline())"
TWO_UPDATES = (
    "import json, sys; sys.stdin.readline(); "
    "print(json.dumps({'params': {'mix': 0.25}})); "
    "print(json.dumps({'params': {'mix': 0.5, 'bypass': True}}))"
)
FAILS = "import sys; sys.stdin.readline(); sys.stderr.write('error: not a VST3\\n'); sys.exit(1)"
# What the real editor does: shows a window until the parent lets go of stdin,
# then reports the state it is closing on.
WAITS_FOR_EOF = (
    "import json, sys; sys.stdin.readline(); sys.stdin.read(); "
    "print(json.dumps({'params': {'mix': 0.9}}))"
)
IGNORES_EOF = "import sys, time; sys.stdin.readline(); time.sleep(30)"


def _stub(script: str) -> tuple[str, list[str]]:
    return sys.executable, ["-c", script]


def test_the_editor_runs_this_program_again_rather_than_a_python_it_may_not_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frozen build has no interpreter beside it, so the editor subcommand is served
    by the same executable the user launched."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    program, args = editor_command()

    assert program == sys.executable
    assert args == ["vst-editor"]


def test_from_a_checkout_the_editor_runs_through_the_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    program, args = editor_command()

    assert program == sys.executable
    assert args == ["-m", "soundboard", "vst-editor"]


def test_a_moved_knob_arrives_as_a_signal(qtbot: QtBot) -> None:
    editor = VstEditor(command=_stub(TWO_UPDATES))
    seen: list[dict[str, object]] = []
    editor.changed.connect(seen.append)

    with qtbot.waitSignal(editor.closed, timeout=15_000):
        editor.open(Path("plugin.vst3"), {})

    assert seen == [{"mix": 0.25}, {"mix": 0.5, "bypass": True}]


def test_the_window_opens_on_the_values_the_chain_is_using(qtbot: QtBot) -> None:
    """The parameters travel on stdin rather than the command line: a plugin can have
    hundreds of them, and Windows caps a command line at 32k characters."""
    editor = VstEditor(command=_stub(ECHO_STDIN))
    seen: list[dict[str, object]] = []
    editor.changed.connect(seen.append)

    with qtbot.waitSignal(editor.closed, timeout=15_000):
        editor.open(Path("plugin.vst3"), {"mix": 0.25})

    assert seen == [{"mix": 0.25}]


def test_an_editor_that_will_not_start_reports_why(qtbot: QtBot) -> None:
    editor = VstEditor(command=_stub(FAILS))

    with qtbot.waitSignal(editor.failed, timeout=15_000) as blocker:
        editor.open(Path("plugin.vst3"), {})

    assert "not a VST3" in blocker.args[0]


def test_a_missing_program_is_reported_rather_than_ignored(qtbot: QtBot) -> None:
    editor = VstEditor(command=("soundboard-no-such-program", []))

    with qtbot.waitSignal(editor.failed, timeout=15_000):
        editor.open(Path("plugin.vst3"), {})

    assert not editor.is_open


def test_closing_the_app_asks_the_window_to_go_rather_than_killing_it(
    qtbot: QtBot,
) -> None:
    """Measured against a real plugin: QProcess.terminate() does not close a JUCE
    window, so a hard kill three seconds later was the only thing ending it — and
    with it went whatever the user had just set. Letting go of stdin is the cue the
    editor process itself waits for, and it reports its last state on the way out."""
    editor = VstEditor(command=_stub(WAITS_FOR_EOF))
    seen: list[dict[str, object]] = []
    editor.changed.connect(seen.append)
    editor.open(Path("plugin.vst3"), {})
    assert editor.is_open

    with qtbot.waitSignal(editor.closed, timeout=15_000):
        editor.close()

    assert not editor.is_open
    assert seen == [{"mix": 0.9}], "the state it closed on has to survive the close"


def test_a_window_that_ignores_the_cue_is_still_taken_down(qtbot: QtBot) -> None:
    """An editor left running would hold a second instance of the plugin, and on
    Windows a window with nobody left to close it."""
    editor = VstEditor(command=_stub(IGNORES_EOF))
    editor.open(Path("plugin.vst3"), {})

    with qtbot.waitSignal(editor.closed, timeout=15_000):
        editor.close()

    assert not editor.is_open


def test_two_windows_for_one_block_are_refused(qtbot: QtBot) -> None:
    editor = VstEditor(command=_stub(IGNORES_EOF))
    editor.open(Path("plugin.vst3"), {})

    with pytest.raises(RuntimeError):
        editor.open(Path("plugin.vst3"), {})

    with qtbot.waitSignal(editor.closed, timeout=15_000):
        editor.close()


def test_an_update_split_across_two_reads_is_still_one_update() -> None:
    """stdout arrives in whatever chunks the OS felt like; a line is not a read."""
    reader = LineReader()

    assert reader.feed(b'{"params": {"mix": 0') == []
    assert reader.feed(b'.25}}\n') == [{"mix": 0.25}]


def test_two_updates_in_one_read_are_both_delivered() -> None:
    reader = LineReader()

    updates = reader.feed(b'{"params": {"mix": 0.1}}\n{"params": {"mix": 0.2}}\n')

    assert updates == [{"mix": 0.1}, {"mix": 0.2}]


def test_whatever_the_plugin_itself_prints_is_not_mistaken_for_an_update() -> None:
    """JUCE plugins log to stdout, and that is their business, not a broken editor."""
    reader = LineReader()

    assert reader.feed(b"JUCE v7.0.9\n") == []
    assert reader.feed(b'{"nothing": 1}\n') == []
    assert reader.feed(b'{"params": {"mix": 0.3}}\n') == [{"mix": 0.3}]
