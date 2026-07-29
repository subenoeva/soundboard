from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundboard.audio.fake_backend import FakeBackend
from soundboard.cli import _run, build_parser, parse_sound_argument


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
