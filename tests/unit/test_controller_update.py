"""AppController's side of the update flow: the model it exposes and the restart."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from PySide6.QtCore import QCoreApplication

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui import update_actions
from soundboard.ui.controller import AppController
from soundboard.updater.fake_feed import FakeReleaseFeed
from soundboard.updater.service import UpdateService, relaunch

from .test_controller import FakeStore

ASSET = b"the v0.4.0 build"
DIGEST = hashlib.sha256(ASSET).hexdigest()
OTHER = hashlib.sha256(b"the linux build").hexdigest()

MANIFEST = (
    "version v0.4.0\n"
    f"{DIGEST}  soundboard-v0.4.0-windows.exe\n"
    f"{OTHER}  soundboard-v0.4.0-linux-x86_64.AppImage\n"
)


@pytest.fixture
def controller(tmp_path: Path) -> AppController:
    return AppController(
        client=FakeRemoteClient(),
        store=FakeStore(),
        backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(),
        cache=SoundCache(tmp_path / "cache"),
        layout_path=tmp_path / "layout.json",
        update_service=UpdateService(
            feed=FakeReleaseFeed(manifest_text=MANIFEST),
            current_version="0.3.0",
            client=httpx.Client(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, content=ASSET))
            ),
        ),
    )


def test_the_update_model_is_exposed_to_qml(controller: AppController) -> None:
    assert controller.property("updateModel") is not None


def test_update_toasts_reach_the_shared_toast_signal(
    qtbot: Any, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The banner shows progress; errors go through the same Toast the rest of the app
    uses, so an update failure is as visible as any other."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    toasts: list[str] = []
    controller.toast.connect(toasts.append)
    model = controller.property("updateModel")

    model.check(True)
    qtbot.waitUntil(lambda: model.property("state") != "checking", timeout=5000)

    assert toasts == ["Ya tienes la última versión"]


def test_restart_tears_the_engine_down_before_relaunching(
    controller: AppController, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Order matters: an audio device still claimed, or a global keyboard hook still
    installed, would fight the instance that is starting."""
    events: list[str] = []
    monkeypatch.setattr(controller, "shutdown", lambda: events.append("shutdown"))
    monkeypatch.setattr(
        update_actions, "relaunch", lambda binary: events.append(f"relaunch {binary.name}")
    )
    monkeypatch.setattr(QCoreApplication, "quit", lambda: events.append("quit"))

    update_actions.restart(controller, str(tmp_path / "soundboard.exe"))

    assert events == ["shutdown", "relaunch soundboard.exe", "quit"]


def test_relaunch_detaches_the_new_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without detaching, the new instance dies with the process group of the old one."""
    calls: list[dict[str, Any]] = []

    def spawn(argv: list[str], **kwargs: Any) -> None:
        calls.append({"argv": argv, **kwargs})

    binary = Path("/home/someone/soundboard.AppImage")
    monkeypatch.setattr(sys, "platform", "linux")
    relaunch(binary, spawn=spawn)

    assert calls[0]["argv"] == [str(binary)]
    assert calls[0]["start_new_session"] is True


def test_the_launch_check_honours_the_opt_out(
    controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOUNDBOARD_NO_UPDATE_CHECK", "1")
    model = controller.property("updateModel")

    update_actions.start_launch_check(model)

    assert model.property("state") == "idle"
