import hashlib
import json
import sys
from pathlib import Path

import httpx
import pytest

from soundboard.updater.errors import NotWritable
from soundboard.updater.fake_feed import FakeReleaseFeed
from soundboard.updater.service import UpdateService, automatic_check_enabled

ASSET = b"the v0.4.0 build"
DIGEST = hashlib.sha256(ASSET).hexdigest()
OTHER_DIGEST = hashlib.sha256(b"the linux build").hexdigest()

MANIFEST = (
    "version v0.4.0\n"
    f"{DIGEST}  soundboard-v0.4.0-windows.exe\n"
    f"{OTHER_DIGEST}  soundboard-v0.4.0-linux-x86_64.AppImage\n"
)


@pytest.fixture
def binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "soundboard.exe"
    path.write_bytes(b"the v0.3.0 build")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(path))
    return path


def _service(**kwargs: object) -> UpdateService:
    defaults: dict[str, object] = {
        "feed": FakeReleaseFeed(manifest_text=MANIFEST),
        "current_version": "0.3.0",
        "client": httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=ASSET))
        ),
    }
    return UpdateService(**{**defaults, **kwargs})  # type: ignore[arg-type]


@pytest.mark.usefixtures("binary")
def test_check_reports_a_newer_release() -> None:
    update = _service().check()

    assert update is not None
    assert update.version == "0.4.0"
    assert update.asset_name == "soundboard-v0.4.0-windows.exe"


@pytest.mark.usefixtures("binary")
def test_check_is_quiet_when_already_on_the_latest_release() -> None:
    assert _service(current_version="0.4.0").check() is None


@pytest.mark.usefixtures("binary")
def test_check_never_offers_a_downgrade() -> None:
    """A validly signed but older manifest, replayed, must not walk anyone backwards."""
    assert _service(current_version="1.0.0").check() is None


def test_check_is_disabled_outside_a_packaged_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert _service().check() is None


def test_apply_installs_the_verified_asset(binary: Path) -> None:
    service = _service()
    update = service.check()
    assert update is not None

    service.apply(update)

    assert binary.read_bytes() == ASSET


def test_apply_refuses_before_downloading_when_the_directory_is_read_only(
    binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordering matters: the user finds out in a second, not after 100MB of traffic."""
    service = _service()
    update = service.check()
    assert update is not None
    monkeypatch.setattr("os.access", lambda *args, **kwargs: False)
    requested: list[str] = []
    monkeypatch.setattr(
        "soundboard.updater.service.fetch",
        lambda *args, **kwargs: requested.append("fetched"),
    )

    with pytest.raises(NotWritable):
        service.apply(update)

    assert requested == []
    assert binary.read_bytes() == b"the v0.3.0 build"


def test_apply_reports_progress(binary: Path) -> None:
    service = _service()
    update = service.check()
    assert update is not None
    seen: list[tuple[int, int | None]] = []

    service.apply(update, progress=lambda done, total: seen.append((done, total)))

    assert seen[-1] == (len(ASSET), len(ASSET))


def test_automatic_check_is_on_by_default(tmp_path: Path) -> None:
    assert automatic_check_enabled(env={}, settings_path=tmp_path / "absent.json")


def test_automatic_check_can_be_turned_off_in_settings(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"update_check": False}))

    assert not automatic_check_enabled(env={}, settings_path=settings)


def test_automatic_check_can_be_turned_off_by_environment(tmp_path: Path) -> None:
    assert not automatic_check_enabled(
        env={"SOUNDBOARD_NO_UPDATE_CHECK": "1"}, settings_path=tmp_path / "absent.json"
    )


def test_unreadable_settings_do_not_disable_the_check(tmp_path: Path) -> None:
    """Falling back to the default keeps a corrupt settings file from silently costing
    the user every future security fix."""
    settings = tmp_path / "settings.json"
    settings.write_text("{ not json")

    assert automatic_check_enabled(env={}, settings_path=settings)
