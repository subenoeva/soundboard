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

import pytest

from soundboard.audio.fake_backend import FakeBackend
from soundboard.effects.chain import EffectChain
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.remote.models import Session
from soundboard.ui.controller import AppController
from soundboard.ui.grid_model import GridModel
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, load_layout, save_layout


class FakeStore:
    def __init__(self) -> None:
        self._session: Session | None = None

    def load(self) -> Session | None:
        return self._session

    def save(self, session: Session) -> None:
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

    def drain_retired(self) -> list[EffectChain]:
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
    client: FakeRemoteClient | None = None,
    hotkeys: FakeHotkeyManager | None = None,
) -> tuple[AppController, FakeRemoteClient, FakeStore]:
    client = client or FakeRemoteClient()
    store = store or FakeStore()
    controller = AppController(
        client=client, store=store, backend=FakeBackend(),
        hotkeys=hotkeys or FakeHotkeyManager(), cache=SoundCache(tmp_path / "cache"),
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
    assert engines[0].stopped  # the engine that was running got shut down
    assert controller.view == "board"  # type: ignore[comparison-overlap]
    controller.stop_all()
    assert engines[-1].stop_all_called


def test_shrinking_the_grid_discards_the_pads_that_no_longer_fit(
    tmp_path: Path, qtbot: object
) -> None:
    controller, client, _ = make_controller(tmp_path)
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 4, 6)
    grid = controller.gridModel
    assert isinstance(grid, GridModel)
    grid.assign_remote(20, "sound-id-1", "airhorn")
    grid.set_shortcut(20, "<ctrl>+<alt>+9")

    messages: list[str] = []
    controller.toast.connect(messages.append)
    controller.apply_devices("mic", "out", 2, 3)

    # Cell 20 has no pad on a 2x3 board: keeping it would leave a global shortcut
    # firing with nothing on screen to clear or rebind it.
    saved = load_layout(tmp_path / "layout.json")
    assert saved is not None
    assert saved.cells == []
    assert messages == ["Se descartaron 1 pads fuera de la nueva grilla"]


def test_failed_device_change_keeps_the_last_working_layout_on_disk(
    tmp_path: Path, qtbot: object
) -> None:
    engines: list[FakeEngine] = []

    def factory(layout):  # type: ignore[no-untyped-def]
        if layout.mic == "broken":
            raise RuntimeError("no such device")
        engines.append(FakeEngine())
        return engines[-1]

    controller, client, _ = make_controller(tmp_path, engine_factory=factory)
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)

    controller.apply_devices("broken", "out", 2, 3)

    assert controller.view == "setup"  # type: ignore[comparison-overlap]
    # The next cold start must find the configuration that worked, not the one that
    # just failed — otherwise a bad pick costs the user their working setup.
    saved = load_layout(tmp_path / "layout.json")
    assert saved is not None
    assert saved.mic == "mic"
    assert controller.micName == "mic"  # type: ignore[comparison-overlap]


def test_a_cell_left_over_from_a_bigger_grid_is_dropped_on_the_next_change(
    tmp_path: Path, qtbot: object
) -> None:
    save_layout(
        tmp_path / "layout.json",
        GridLayout(
            rows=2, cols=3, mic="m", out="o", blocksize=256,
            cells=[Cell(index=9, source=LocalSource(path="a.wav"), name="ghost")],
        ),
    )
    controller, client, store = make_controller(tmp_path)
    store.save(client.sign_in_as_new_user("user@example.com"))
    controller.bootstrap()

    controller.apply_devices("mic", "out", 2, 3)

    saved = load_layout(tmp_path / "layout.json")
    assert saved is not None
    assert saved.cells == []


def test_log_out_retires_the_engine_stack_and_returns_to_login(
    tmp_path: Path, qtbot: object
) -> None:
    engines: list[FakeEngine] = []

    def factory(layout):  # type: ignore[no-untyped-def]
        engines.append(FakeEngine())
        return engines[-1]

    hotkeys = FakeHotkeyManager()
    controller, client, store = make_controller(
        tmp_path, engine_factory=factory, hotkeys=hotkeys
    )
    client.sign_up("user@example.com", "password")
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    grid = controller.gridModel
    assert isinstance(grid, GridModel)
    grid.assign_remote(0, "sound-id-1", "airhorn")
    grid.set_shortcut(0, "<ctrl>+1")

    controller.log_out()

    assert controller.view == "login"  # type: ignore[comparison-overlap]
    assert controller.userEmail == ""  # type: ignore[comparison-overlap]
    assert store.load() is None
    assert controller.gridModel is None
    assert controller.bridge is None
    assert engines[-1].stopped
    # A global hotkey surviving the session would play into a dead engine, from a
    # board the user can no longer see to unbind it.
    with pytest.raises(KeyError):
        hotkeys.trigger("<ctrl>+1")
    # The grid belongs to the machine, not to the session: signing back in has to
    # find the same pads.
    assert load_layout(tmp_path / "layout.json") is not None


def test_log_out_drops_the_local_session_even_if_the_server_call_fails(
    tmp_path: Path, qtbot: object
) -> None:
    class OfflineClient(FakeRemoteClient):
        def sign_out(self) -> None:
            raise RuntimeError("connection refused")

    client = OfflineClient()
    client.sign_up("user@example.com", "password")
    controller, _, store = make_controller(tmp_path, client=client)
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    messages: list[str] = []
    controller.toast.connect(messages.append)

    controller.log_out()

    # Keeping the session on disk because the server was unreachable would sign the
    # user straight back in on the next start — the one thing logout must prevent.
    assert store.load() is None
    assert controller.view == "login"  # type: ignore[comparison-overlap]
    assert len(messages) == 1
    assert "connection refused" in messages[0]
