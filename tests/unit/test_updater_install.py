import os
import sys
from pathlib import Path

import pytest

from soundboard.updater.install import STAGED_PREFIX, install, staged_path, sweep_stale


def _binary(tmp_path: Path) -> Path:
    binary = tmp_path / "soundboard.exe"
    binary.write_bytes(b"old build")
    return binary


def _stale_names(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in tmp_path.iterdir())


def test_install_puts_the_new_build_at_the_original_path(tmp_path: Path) -> None:
    """The path has to survive the swap: shortcuts, taskbar pins and .desktop launchers
    all point at it."""
    binary = _binary(tmp_path)
    staged = staged_path(binary, "v0.4.0")
    staged.write_bytes(b"new build")

    install(staged, binary)

    assert binary.read_bytes() == b"new build"
    assert not staged.exists()


def test_install_keeps_the_previous_build_aside(tmp_path: Path) -> None:
    binary = _binary(tmp_path)
    staged = staged_path(binary, "v0.4.0")
    staged.write_bytes(b"new build")

    install(staged, binary)

    olds = [p for p in tmp_path.iterdir() if p.name.endswith(".old")]
    assert len(olds) == 1
    assert olds[0].read_bytes() == b"old build"


def test_install_rolls_back_when_the_second_rename_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between the two renames the binary does not exist at its own path. If the second
    one fails there, the user is left with no application at all unless we put it back."""
    binary = _binary(tmp_path)
    staged = staged_path(binary, "v0.4.0")
    staged.write_bytes(b"new build")
    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("locked by another process")
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", flaky_replace)

    with pytest.raises(OSError, match="locked"):
        install(staged, binary)

    assert binary.read_bytes() == b"old build"
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".old")]


def test_install_survives_a_second_update_in_one_session(tmp_path: Path) -> None:
    """The first .old cannot be deleted while the process still runs from it on Windows,
    so a fixed name would make the second rename collide."""
    binary = _binary(tmp_path)
    for release in ("v0.4.0", "v0.5.0"):
        staged = staged_path(binary, release)
        staged.write_bytes(f"build {release}".encode())
        install(staged, binary)

    assert binary.read_bytes() == b"build v0.5.0"
    assert len([p for p in tmp_path.iterdir() if p.name.endswith(".old")]) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_install_makes_the_new_build_executable(tmp_path: Path) -> None:
    """The staged file is created by a plain write and has no execute bit; an AppImage
    without one is a file the desktop refuses to launch."""
    binary = _binary(tmp_path)
    staged = staged_path(binary, "v0.4.0")
    staged.write_bytes(b"new build")

    install(staged, binary)

    assert os.access(binary, os.X_OK)


def test_sweep_stale_removes_leftovers_from_earlier_updates(tmp_path: Path) -> None:
    binary = _binary(tmp_path)
    (tmp_path / f"{binary.name}.a1b2c3d4.old").write_bytes(b"older build")
    (tmp_path / f"{STAGED_PREFIX}v0.4.0.tmp").write_bytes(b"interrupted download")

    sweep_stale(binary)

    assert _stale_names(tmp_path) == ["soundboard.exe"]


def test_sweep_stale_leaves_unrelated_files_alone(tmp_path: Path) -> None:
    """The binary usually sits in the user's Downloads folder. A broader glob there is a
    cheap way to delete something that is not ours."""
    binary = _binary(tmp_path)
    (tmp_path / "soundboard-v0.2.0-windows.exe.old").write_bytes(b"a build they kept")
    (tmp_path / "taxes.old").write_bytes(b"not ours")

    sweep_stale(binary)

    assert _stale_names(tmp_path) == [
        "soundboard-v0.2.0-windows.exe.old",
        "soundboard.exe",
        "taxes.old",
    ]


def test_sweep_stale_does_not_raise_when_a_leftover_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing the user can act on, and the app works either way — it is retried on the
    next launch instead of interrupting them."""
    binary = _binary(tmp_path)
    (tmp_path / f"{binary.name}.a1b2c3d4.old").write_bytes(b"older build")

    def locked(*args: object, **kwargs: object) -> None:
        raise PermissionError("still being scanned")

    monkeypatch.setattr(Path, "unlink", locked)

    sweep_stale(binary)
