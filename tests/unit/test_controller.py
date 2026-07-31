"""AppController: session bootstrap, engine lifecycle, view navigation.

Note: `bootstrap()`'s handling of a session that fails to restore (Supabase
rotating a consumed refresh token — see `app.py`'s `run_gui`) is not covered here.
`FakeRemoteClient.restore_session` never raises, so that path cannot be exercised
without a bespoke client double; the behavior is inherited unchanged from the
legacy `app.py` flow it was ported from.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.controller import AppController
from soundboard.ui.layout_store import GridLayout, save_layout


class FakeStore:
    def __init__(self) -> None:
        self._session = None

    def load(self):  # type: ignore[no-untyped-def]
        return self._session

    def save(self, session) -> None:  # type: ignore[no-untyped-def]
        self._session = session

    def clear(self) -> None:
        self._session = None


class FakeEngine:
    def __init__(self) -> None:
        self.stopped = False
        self.stop_all_called = False
        self.last_peak = 0.0

    def play(self, pcm, **kwargs):  # type: ignore[no-untyped-def]
        return 1

    def stop_all(self) -> None:
        self.stop_all_called = True

    def stop(self) -> None:
        self.stopped = True

    def voice_states(self) -> list[tuple[int, float]]:
        return []

    @property
    def metrics(self):  # type: ignore[no-untyped-def]
        from soundboard.audio.engine import EngineMetrics
        return EngineMetrics(underruns=0, overruns=0, fill=0, ratio=1.0, active_voices=0)


def make_controller(
    tmp_path: Path,
    *,
    engine_factory: Callable[[GridLayout], FakeEngine] | None = None,
    store: FakeStore | None = None,
) -> tuple[AppController, FakeRemoteClient, FakeStore]:
    client = FakeRemoteClient()
    store = store or FakeStore()
    controller = AppController(
        client=client, store=store, backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(), cache=SoundCache(tmp_path / "cache"),
        layout_path=tmp_path / "layout.json",
        engine_factory=engine_factory or (lambda layout: FakeEngine()),
    )
    return controller, client, store


def test_bootstrap_without_session_lands_on_login(tmp_path: Path, qtbot: object) -> None:
    controller, _, _ = make_controller(tmp_path)
    controller.bootstrap()
    assert controller.view == "login"  # type: ignore[comparison-overlap]


def test_login_without_layout_lands_on_setup(tmp_path: Path, qtbot: object) -> None:
    controller, client, _ = make_controller(tmp_path)
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    assert controller.view == "setup"  # type: ignore[comparison-overlap]
    assert controller.userEmail == "user@example.com"  # type: ignore[comparison-overlap]


def test_bad_login_sets_login_error(tmp_path: Path, qtbot: object) -> None:
    controller, _, _ = make_controller(tmp_path)
    controller.bootstrap()
    controller.log_in("nobody@example.com", "wrong")
    assert controller.view == "login"  # type: ignore[comparison-overlap]
    assert controller.loginError != ""  # type: ignore[comparison-overlap]


def test_apply_devices_starts_engine_and_lands_on_board(tmp_path: Path, qtbot: object) -> None:
    controller, client, _ = make_controller(tmp_path)
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    assert controller.view == "board"  # type: ignore[comparison-overlap]
    assert controller.gridModel is not None
    assert controller.bridge is not None
    assert (tmp_path / "layout.json").exists()


def test_engine_failure_shows_setup_error(tmp_path: Path, qtbot: object) -> None:
    def exploding_factory(layout):  # type: ignore[no-untyped-def]
        raise RuntimeError("no such device")
    controller, client, _ = make_controller(tmp_path, engine_factory=exploding_factory)
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    assert controller.view == "setup"  # type: ignore[comparison-overlap]
    assert "no such device" in controller.setupError  # type: ignore[operator]


def test_saved_session_and_layout_boot_straight_to_board(tmp_path: Path, qtbot: object) -> None:
    controller, client, store = make_controller(tmp_path)
    save_layout(tmp_path / "layout.json",
                GridLayout(rows=2, cols=2, mic="m", out="o", blocksize=256))
    store.save(client.sign_in_as_new_user("user@example.com"))
    controller.bootstrap()
    assert controller.view == "board"  # type: ignore[comparison-overlap]


def test_settings_round_trip_and_stop_all(tmp_path: Path, qtbot: object) -> None:
    engines: list[FakeEngine] = []
    def factory(layout):  # type: ignore[no-untyped-def]
        engines.append(FakeEngine())
        return engines[-1]
    controller, client, _ = make_controller(tmp_path, engine_factory=factory)
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    controller.open_settings()
    assert controller.view == "setup"  # type: ignore[comparison-overlap]
    controller.cancel_settings()
    assert controller.view == "board"  # type: ignore[comparison-overlap]
    controller.apply_devices("mic2", "out2", 3, 3)
    assert engines[0].stopped  # el engine anterior se apagó
    assert controller.view == "board"  # type: ignore[comparison-overlap]
    controller.stop_all()
    assert engines[-1].stop_all_called
