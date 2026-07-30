from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import Qt

from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.clip_button import ClipState
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, RemoteSource
from soundboard.ui.main_window import MainWindow


class _RecordingEngine:
    def __init__(self) -> None:
        self.played: list[np.ndarray] = []
        self.stopped_all = 0

    def play(self, pcm: np.ndarray, **kwargs: object) -> None:
        self.played.append(pcm)

    def stop_all(self) -> None:
        self.stopped_all += 1

    def stop(self) -> None:
        pass


def test_clicking_a_local_cell_plays_it(qtbot: Any, tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.5, dtype=np.float32), 48_000)
    engine = _RecordingEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip", shortcut=None)],
    )
    window = MainWindow(
        engine, FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window._grid.button_at(0), Qt.MouseButton.LeftButton)

    assert len(engine.played) == 1


def test_clicking_a_remote_cell_loads_then_plays(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.5, dtype=np.float32), 48_000)
    sound = sounds.add_sound(client, session, str(clip), name="laugh")
    engine = _RecordingEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id=sound.id), name="laugh", shortcut=None)],
    )
    window = MainWindow(
        engine, client, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window._grid.button_at(0), Qt.MouseButton.LeftButton)

    assert window._grid.button_at(0).state is ClipState.LOADING
    qtbot.waitUntil(lambda: len(engine.played) == 1, timeout=2000)
    assert window._grid.button_at(0).state is ClipState.IDLE


def test_a_remote_download_failure_shows_the_error_and_resets_the_button(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    engine = _RecordingEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id="missing-id"), name="ghost", shortcut=None)],
    )
    window = MainWindow(
        engine, client, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window._grid.button_at(0), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._grid.button_at(0).state is ClipState.IDLE, timeout=2000)

    assert engine.played == []
    assert window.statusBar().currentMessage()


def test_dropping_a_file_assigns_the_cell_and_persists_the_layout(
    qtbot: Any, tmp_path: Path
) -> None:
    clip = tmp_path / "airhorn.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    layout_path = tmp_path / "ui_layout.json"
    window = MainWindow(
        _RecordingEngine(), FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, layout_path,
    )
    qtbot.addWidget(window)

    window._grid.button_at(0).file_dropped.emit(0, str(clip))

    assert window._grid.button_at(0).state is ClipState.IDLE
    assert "airhorn" in window._grid.button_at(0).text()
    assert layout_path.exists()


def test_dropping_an_undecodable_file_shows_an_error_and_leaves_the_cell_empty(
    qtbot: Any, tmp_path: Path
) -> None:
    bogus = tmp_path / "not_audio.txt"
    bogus.write_text("hello")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        _RecordingEngine(), FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
        message_box=lambda *_args: None,
    )
    qtbot.addWidget(window)

    window._grid.button_at(0).file_dropped.emit(0, str(bogus))

    assert window._grid.button_at(0).state is ClipState.EMPTY


def test_a_registered_hotkey_triggers_playback(qtbot: Any, tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.5, dtype=np.float32), 48_000)
    engine = _RecordingEngine()
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip",
                     shortcut="<ctrl>+<alt>+1")],
    )
    window = MainWindow(
        engine, FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        hotkeys, layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    hotkeys.trigger("<ctrl>+<alt>+1")

    assert len(engine.played) == 1


def test_clear_cell_unregisters_its_hotkey_and_empties_the_button(
    qtbot: Any, tmp_path: Path
) -> None:
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path="x.wav"), name="clip",
                     shortcut="<ctrl>+<alt>+1")],
    )
    window = MainWindow(
        _RecordingEngine(), FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        hotkeys, layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    window._grid.clear_requested.emit(0)

    assert window._grid.button_at(0).state is ClipState.EMPTY
    with pytest.raises(KeyError):
        hotkeys.trigger("<ctrl>+<alt>+1")


def test_stop_all_toolbar_action_calls_the_engine(qtbot: Any, tmp_path: Path) -> None:
    engine = _RecordingEngine()
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        engine, FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    window._stop_all_action.trigger()

    assert engine.stopped_all == 1


def test_closing_the_window_hides_it_instead_of_closing(qtbot: Any, tmp_path: Path) -> None:
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        _RecordingEngine(), FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)
    window.show()

    window.close()

    assert not window.isVisible()
    assert window.isHidden()


def test_assign_shortcut_registers_it_and_persists_the_layout(qtbot: Any, tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip", shortcut=None)],
    )
    layout_path = tmp_path / "ui_layout.json"
    window = MainWindow(
        _RecordingEngine(), FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        hotkeys, layout, layout_path,
        prompt_shortcut=lambda *_args: ("<ctrl>+<alt>+5", True),
    )
    qtbot.addWidget(window)

    window._grid.assign_shortcut_requested.emit(0)

    hotkeys.trigger("<ctrl>+<alt>+5")  # raises KeyError if registration didn't happen
    assert layout_path.exists()
    assert "<ctrl>+<alt>+5" in window._grid.button_at(0).text()


def test_assign_shortcut_with_a_malformed_combo_shows_an_error_and_registers_nothing(
    qtbot: Any, tmp_path: Path
) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip", shortcut=None)],
    )
    errors = []
    window = MainWindow(
        _RecordingEngine(), FakeRemoteClient(), SoundCache(tmp_path / "cache"),
        hotkeys, layout, tmp_path / "ui_layout.json",
        message_box=lambda _parent, _title, message: errors.append(message),
        prompt_shortcut=lambda *_args: ("not-a-combo!!", True),
    )
    qtbot.addWidget(window)

    window._grid.assign_shortcut_requested.emit(0)

    assert errors
    cell = window._cell_at(0)
    assert cell is not None
    assert cell.shortcut is None
