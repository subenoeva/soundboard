import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundboard.audio.fake_backend import FakeBackend
from soundboard.cli import _run, build_parser, main, parse_sound_argument
from soundboard.library.cache import SoundCache
from soundboard.remote import categories, sounds
from soundboard.remote.client import SessionStore
from soundboard.remote.fake_client import FakeRemoteClient


def test_parses_a_sound_assignment() -> None:
    key, path = parse_sound_argument("a=C:/clips/laugh.wav")

    assert key == "a"
    assert path == "C:/clips/laugh.wav"


def test_rejects_a_sound_argument_without_a_key() -> None:
    with pytest.raises(ValueError, match="KEY=PATH"):
        parse_sound_argument("laugh.wav")


def test_devices_subcommand_is_available() -> None:
    args = build_parser().parse_args(["devices"])

    assert args.command == "devices"


def test_run_subcommand_collects_sounds() -> None:
    args = build_parser().parse_args(
        ["run", "--mic", "realtek", "--out", "cable", "--sound", "a=x.wav", "--sound", "b=y.wav"]
    )

    assert args.mic == "realtek"
    assert args.out == "cable"
    assert args.sound == ["a=x.wav", "b=y.wav"]


class _AdvancingStdin:
    """Feeds scripted lines to ``_run``, advancing ``FakeBackend``'s simulated
    clock between them.

    ``FakeBackend`` never runs its own thread, so without this the commands
    ``_run`` queues on the engine (``play``, ``stop_all``) would sit in the
    deque forever - nothing would ever call the output callback that drains
    them. Advancing on every ``__next__`` (i.e. right before handing back the
    *next* line) means each command has had a chance to be processed by the
    time the test inspects ``backend.captured`` at the following step.
    """

    def __init__(self, lines: list[str], backend: FakeBackend, blocks_per_line: int) -> None:
        self._lines = iter(lines)
        self._backend = backend
        self._blocks_per_line = blocks_per_line

    def __iter__(self) -> "_AdvancingStdin":
        return self

    def __next__(self) -> str:
        self._backend.advance(self._blocks_per_line)
        return next(self._lines)


def test_run_drives_the_engine_end_to_end_against_a_fake_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip_path = tmp_path / "clip.wav"
    sf.write(clip_path, np.full(64 * 50, 0.5, dtype=np.float32), 48_000)

    backend = FakeBackend()
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)

    args = build_parser().parse_args(
        [
            "run",
            "--mic",
            "microphone",
            "--out",
            "cable",
            "--sound",
            f"a={clip_path}",
            "--blocksize",
            "64",
        ]
    )

    # "a" triggers the clip, "stop" silences it, "quit" exits the loop.
    monkeypatch.setattr("sys.stdin", _AdvancingStdin(["a", "stop", "quit"], backend, 5))

    exit_code = _run(args, backend)

    assert exit_code == 0
    # The `finally: engine.stop()` ran, closing every stream.
    assert backend.streams == []
    # Fetching "stop" advanced past the batch that processed the queued "a"
    # play command; the clip's signal should be audible by its last block.
    assert np.max(backend.captured[9]) > 0.4
    # Fetching "quit" advanced past the batch that processed stop_all; the
    # mixer should be silent again by its last block.
    assert np.max(np.abs(backend.captured[14])) < 1e-6


def test_run_reports_a_bad_device_needle_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    backend = FakeBackend()
    args = build_parser().parse_args(["run", "--mic", "nonexistent", "--out", "cable"])

    exit_code = _run(args, backend)

    assert exit_code == 1
    assert backend.streams == []
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "nonexistent" in err


def test_run_reports_a_bad_clip_path_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = FakeBackend()
    missing = tmp_path / "missing.wav"
    args = build_parser().parse_args(
        ["run", "--mic", "microphone", "--out", "cable", "--sound", f"a={missing}"]
    )

    exit_code = _run(args, backend)

    assert exit_code == 1
    assert backend.streams == []
    err = capsys.readouterr().err
    assert err.startswith("error:")


class _DictKeyringBackend:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


def test_auth_signup_and_login_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    from soundboard.cli import _auth, build_parser

    client = FakeRemoteClient()
    store = SessionStore(backend=_DictKeyringBackend())

    signup_args = build_parser().parse_args(["auth", "signup", "--email", "a@x.com"])
    exit_code = _auth(signup_args, client=client, store=store, password_prompt=lambda: "hunter2")
    assert exit_code == 0

    login_args = build_parser().parse_args(["auth", "login", "--email", "a@x.com"])
    exit_code = _auth(
        login_args,
        client=client,
        store=store,
        password_prompt=lambda: "hunter2",
        display_name_prompt=lambda: "Pablo",
    )
    assert exit_code == 0
    assert store.load() is not None

    whoami_args = build_parser().parse_args(["auth", "whoami"])
    exit_code = _auth(whoami_args, client=client, store=store)
    assert exit_code == 0
    assert "a@x.com" in capsys.readouterr().out


def test_auth_whoami_without_a_session_reports_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from soundboard.cli import _auth, build_parser

    args = build_parser().parse_args(["auth", "whoami"])
    exit_code = _auth(
        args, client=FakeRemoteClient(), store=SessionStore(backend=_DictKeyringBackend())
    )

    assert exit_code == 1
    assert "auth login" in capsys.readouterr().err


def test_sounds_add_list_edit_rm_subcommands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from soundboard.cli import _sounds, build_parser

    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.3, dtype=np.float32), 48_000)

    add_args = build_parser().parse_args(["sounds", "add", str(clip), "--name", "laugh"])
    assert _sounds(add_args, client=client, store=store) == 0

    added = sounds.list_sounds(client)[0]

    list_args = build_parser().parse_args(["sounds", "list"])
    assert _sounds(list_args, client=client, store=store) == 0
    assert "laugh" in capsys.readouterr().out

    edit_args = build_parser().parse_args(
        ["sounds", "edit", added.id, "--name", "renamed"]
    )
    assert _sounds(edit_args, client=client, store=store) == 0
    assert sounds.get_sound(client, added.id).name == "renamed"

    rm_args = build_parser().parse_args(["sounds", "rm", added.id])
    assert _sounds(rm_args, client=client, store=store) == 0
    assert sounds.list_sounds(client) == []


def test_sounds_edit_by_a_stranger_reports_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from soundboard.cli import _sounds, build_parser

    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    added = sounds.add_sound(client, owner, str(clip), name="laugh")

    stranger = client.sign_in_as_new_user("stranger@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(stranger)

    edit_args = build_parser().parse_args(["sounds", "edit", added.id, "--name", "hijacked"])
    exit_code = _sounds(edit_args, client=client, store=store)

    assert exit_code == 1
    assert "not" in capsys.readouterr().err.lower()


def test_categories_add_list_rm_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    from soundboard.cli import _categories, build_parser

    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)

    add_args = build_parser().parse_args(["categories", "add", "memes"])
    assert _categories(add_args, client=client, store=store) == 0

    list_args = build_parser().parse_args(["categories", "list"])
    assert _categories(list_args, client=client, store=store) == 0
    assert "memes" in capsys.readouterr().out

    rm_args = build_parser().parse_args(["categories", "rm", "memes"])
    assert _categories(rm_args, client=client, store=store) == 0
    assert categories.list_categories(client) == []


def test_run_sound_resolves_a_remote_id_when_no_local_file_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from soundboard.cli import _run, build_parser

    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(64 * 50, 0.5, dtype=np.float32), 48_000)
    added = sounds.add_sound(client, session, str(clip), name="laugh")

    backend = FakeBackend()
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)
    args = build_parser().parse_args(
        [
            "run",
            "--mic",
            "microphone",
            "--out",
            "cable",
            "--sound",
            f"a={added.id}",
            "--blocksize",
            "64",
        ]
    )
    monkeypatch.setattr("sys.stdin", _AdvancingStdin(["a", "stop", "quit"], backend, 5))

    exit_code = _run(args, backend, remote_client=client, cache=SoundCache(tmp_path / "cache"))

    assert exit_code == 0
    assert np.max(backend.captured[9]) > 0.4


def test_gui_subcommand_is_available() -> None:
    args = build_parser().parse_args(["gui"])

    assert args.command == "gui"


def test_vst_editor_subcommand_takes_the_plugin_to_open() -> None:
    args = build_parser().parse_args(["vst-editor", "C:/plugins/Voice.vst3"])

    assert args.command == "vst-editor"
    assert args.path == "C:/plugins/Voice.vst3"


def test_vst_editor_subcommand_runs_the_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    """The GUI reaches the plugin window by running this program again, so the
    subcommand is the whole interface between the two processes."""
    import soundboard.effects.vst_editor as editor

    opened: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        opened.append(argv)
        return 0

    monkeypatch.setattr(editor, "main", fake_main)

    assert main(["vst-editor", "Voice.vst3"]) == 0
    assert opened == [["Voice.vst3"]]


def test_importing_cli_does_not_import_pyside6() -> None:
    # A fresh subprocess, not a plain `sys.modules` check in-process: other test
    # modules in the same pytest run already import PySide6 for their own widget
    # tests, which would make an in-process check pass or fail depending on test
    # order rather than on whether `cli.py` itself ever imports it.
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import soundboard.cli, sys; assert 'PySide6' not in sys.modules"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_main_launches_the_gui_when_invoked_without_any_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run_gui() -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr("soundboard.ui.app.run_gui", fake_run_gui)
    monkeypatch.setattr(sys, "argv", ["soundboard"])

    exit_code = main()

    assert exit_code == 0
    assert calls == [True]


def test_main_with_an_empty_explicit_argv_also_launches_the_gui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run_gui() -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr("soundboard.ui.app.run_gui", fake_run_gui)

    exit_code = main([])

    assert exit_code == 0
    assert calls == [True]
