import sys
from pathlib import Path

import pytest

from soundboard.updater.errors import NotWritable, UpdateError
from soundboard.updater.locate import current_asset_name, ensure_writable, installed_binary


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)


def test_a_source_checkout_has_no_updatable_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running from a checkout or a pip install means sys.executable is the interpreter.
    Returning None here is what switches the whole feature off in one place."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert installed_binary() is None


@pytest.mark.usefixtures("frozen")
def test_a_frozen_windows_build_updates_its_own_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", r"C:\Users\someone\Downloads\soundboard.exe")

    assert installed_binary() == Path(r"C:\Users\someone\Downloads\soundboard.exe")


@pytest.mark.usefixtures("frozen")
def test_an_appimage_updates_the_outer_file_not_the_mounted_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sys.executable points inside the FUSE mount, which vanishes on exit — replacing
    anything there would update nothing."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", "/tmp/.mount_sound42/usr/bin/soundboard/soundboard")
    monkeypatch.setenv("APPIMAGE", "/home/someone/Apps/soundboard-v0.3.0-linux-x86_64.AppImage")

    assert installed_binary() == Path("/home/someone/Apps/soundboard-v0.3.0-linux-x86_64.AppImage")


@pytest.mark.usefixtures("frozen")
def test_an_extracted_appdir_is_not_updatable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("APPIMAGE", raising=False)

    assert installed_binary() is None


def test_ensure_writable_accepts_a_writable_directory(tmp_path: Path) -> None:
    binary = tmp_path / "soundboard.exe"
    binary.write_bytes(b"stub")

    ensure_writable(binary)


def test_ensure_writable_rejects_a_read_only_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checked before the download so a binary parked in Program Files fails in a
    second rather than after 100MB of traffic."""
    binary = tmp_path / "soundboard.exe"
    binary.write_bytes(b"stub")
    monkeypatch.setattr("os.access", lambda *args, **kwargs: False)

    with pytest.raises(NotWritable, match=str(tmp_path.name)):
        ensure_writable(binary)


def test_current_asset_name_picks_the_running_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert current_asset_name("v0.4.0") == "soundboard-v0.4.0-windows.exe"

    monkeypatch.setattr(sys, "platform", "linux")
    assert current_asset_name("v0.4.0") == "soundboard-v0.4.0-linux-x86_64.AppImage"


def test_current_asset_name_rejects_an_unbuilt_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    with pytest.raises(UpdateError):
        current_asset_name("v0.4.0")
