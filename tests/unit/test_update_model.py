"""UpdateModel: headless view state over the update flow."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from soundboard.ui.update_model import UpdateModel
from soundboard.updater.errors import FeedUnavailable
from soundboard.updater.fake_feed import FakeReleaseFeed
from soundboard.updater.service import UpdateService

ASSET = b"the v0.4.0 build"
DIGEST = hashlib.sha256(ASSET).hexdigest()
OTHER = hashlib.sha256(b"the linux build").hexdigest()

MANIFEST = (
    "version v0.4.0\n"
    f"{DIGEST}  soundboard-v0.4.0-windows.exe\n"
    f"{OTHER}  soundboard-v0.4.0-linux-x86_64.AppImage\n"
)


@pytest.fixture
def binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "soundboard.exe"
    path.write_bytes(b"the v0.3.0 build")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(path))
    return path


def _service(**kwargs: Any) -> UpdateService:
    defaults: dict[str, Any] = {
        "feed": FakeReleaseFeed(manifest_text=MANIFEST),
        "current_version": "0.3.0",
        "client": httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=ASSET))
        ),
    }
    return UpdateService(**{**defaults, **kwargs})


def _settle(qtbot: Any, model: UpdateModel) -> None:
    qtbot.waitUntil(
        lambda: model.property("state") not in ("checking", "downloading"), timeout=5000
    )


@pytest.mark.usefixtures("binary")
def test_a_newer_release_moves_the_model_to_available(qtbot: Any) -> None:
    model = UpdateModel(_service())

    model.check()
    _settle(qtbot, model)

    assert model.property("state") == "available"
    assert model.property("version") == "0.4.0"


@pytest.mark.usefixtures("binary")
def test_being_up_to_date_leaves_the_model_idle(qtbot: Any) -> None:
    model = UpdateModel(_service(current_version="0.4.0"))

    model.check()
    _settle(qtbot, model)

    assert model.property("state") == "idle"
    assert model.property("version") == ""


@pytest.mark.usefixtures("binary")
def test_the_launch_check_stays_quiet_when_the_network_is_down(qtbot: Any) -> None:
    """Telling someone their soundboard could not phone home, every launch they happen
    to be offline, is noise about a thing they did not ask for."""
    model = UpdateModel(_service(feed=FakeReleaseFeed(error=FeedUnavailable("no route"))))
    toasts: list[str] = []
    model.toast.connect(toasts.append)

    model.check()
    _settle(qtbot, model)

    assert model.property("state") == "idle"
    assert toasts == []


@pytest.mark.usefixtures("binary")
def test_the_manual_check_reports_a_failure(qtbot: Any) -> None:
    """Here the user asked a question, so silence would be the failure."""
    model = UpdateModel(_service(feed=FakeReleaseFeed(error=FeedUnavailable("no route"))))
    toasts: list[str] = []
    model.toast.connect(toasts.append)

    model.check(announce=True)
    _settle(qtbot, model)

    assert model.property("state") == "failed"
    assert "no route" in toasts[0]


@pytest.mark.usefixtures("binary")
def test_the_manual_check_confirms_being_up_to_date(qtbot: Any) -> None:
    model = UpdateModel(_service(current_version="0.4.0"))
    toasts: list[str] = []
    model.toast.connect(toasts.append)

    model.check(announce=True)
    _settle(qtbot, model)

    assert toasts == ["Ya tienes la última versión"]


@pytest.mark.usefixtures("binary")
def test_a_second_check_while_one_is_running_is_ignored(qtbot: Any) -> None:
    feed = FakeReleaseFeed(manifest_text=MANIFEST)
    model = UpdateModel(_service(feed=feed))

    model.check()
    model.check()
    _settle(qtbot, model)

    assert feed.checks == 1


def test_the_model_reports_being_unsupported_in_a_checkout(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QML hides the whole menu entry on this, rather than offering an action that can
    only ever fail."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    model = UpdateModel(_service())

    assert not model.property("supported")


def test_download_installs_and_asks_for_a_restart(qtbot: Any, binary: Path) -> None:
    model = UpdateModel(_service())
    model.check()
    _settle(qtbot, model)

    model.download()
    _settle(qtbot, model)

    assert model.property("state") == "ready"
    assert binary.read_bytes() == ASSET


def test_download_reports_progress(qtbot: Any, binary: Path) -> None:
    model = UpdateModel(_service())
    model.check()
    _settle(qtbot, model)
    seen: list[float] = []
    model.progressChanged.connect(lambda: seen.append(float(model.property("progress"))))

    model.download()
    _settle(qtbot, model)

    assert seen and seen[-1] == pytest.approx(1.0)
    assert seen == sorted(seen)


def test_a_failed_download_is_reported_and_leaves_the_binary_alone(
    qtbot: Any, binary: Path
) -> None:
    service = _service(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"wrong"))
        )
    )
    model = UpdateModel(service)
    model.check()
    _settle(qtbot, model)
    toasts: list[str] = []
    model.toast.connect(toasts.append)

    model.download()
    _settle(qtbot, model)

    assert model.property("state") == "failed"
    assert toasts
    assert binary.read_bytes() == b"the v0.3.0 build"


def test_restart_is_delegated_to_the_controller(qtbot: Any, binary: Path) -> None:
    """The model must not relaunch by itself: the engine, the poll timer and the global
    keyboard hook have to come down first, and that stack belongs to the controller."""
    model = UpdateModel(_service())
    model.check()
    _settle(qtbot, model)
    model.download()
    _settle(qtbot, model)
    requested: list[str] = []
    model.restartRequested.connect(lambda path: requested.append(path))

    model.restart()

    assert requested == [str(binary)]


@pytest.mark.usefixtures("binary")
def test_restart_before_an_update_is_installed_does_nothing(qtbot: Any) -> None:
    model = UpdateModel(_service())
    requested: list[str] = []
    model.restartRequested.connect(lambda path: requested.append(path))

    model.restart()

    assert requested == []
