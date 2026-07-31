"""AppController: owns the session, the engine lifecycle and view navigation.

The QML front end binds to a single instance of this class, exposed as the `App`
context property. It is a persistent object with notify signals rather than a
one-shot startup function, because QML needs something it can bind to and that
reacts to state changes after construction.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from soundboard.audio.backend import AudioBackend
from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import auth
from soundboard.remote.models import RemoteClient, Session
from soundboard.ui import session_actions, update_actions
from soundboard.ui.engine_bridge import EngineBridge
from soundboard.ui.engine_factory import Engine, Store, build_engine
from soundboard.ui.grid_model import GridModel
from soundboard.ui.layout_store import (
    GridLayout,
    load_layout,
    save_layout,
    trim_cells_to_bounds,
)
from soundboard.ui.library_model import LibraryModel
from soundboard.updater.service import UpdateService

_DEFAULT_ROWS = 4
_DEFAULT_COLS = 6


class AppController(QObject):
    viewChanged = Signal()
    sessionChanged = Signal()
    loginErrorChanged = Signal()
    setupErrorChanged = Signal()
    devicesChanged = Signal()
    gridModelChanged = Signal()
    bridgeChanged = Signal()
    toast = Signal(str)

    def __init__(
        self,
        *,
        client: RemoteClient,
        store: Store,
        backend: AudioBackend,
        hotkeys: HotkeyManager,
        cache: SoundCache,
        layout_path: Path,
        engine_factory: Callable[[GridLayout], Engine] | None = None,
        update_service: UpdateService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._store = store
        self._backend = backend
        self._hotkeys = hotkeys
        self._cache = cache
        self._layout_path = layout_path
        self._engine_factory: Callable[[GridLayout], Engine] = engine_factory or (
            lambda layout: build_engine(self._backend, layout)
        )

        self._view = "login"
        self._session: Session | None = None
        self._login_error = ""
        self._setup_error = ""
        self._layout: GridLayout | None = None
        self._engine: Engine | None = None
        self._grid: GridModel | None = None
        self._bridge: EngineBridge | None = None
        self._library = LibraryModel(client, parent=self)
        self._update = update_actions.build_model(self, update_service)

    # -- lifecycle ------------------------------------------------------------

    def bootstrap(self) -> None:
        update_actions.start_launch_check(self._update)
        self._session = session_actions.restore(self._client, self._store)
        if self._session is None:
            self._set_view("login")
            return
        self._after_login()

    def shutdown(self) -> None:
        self._teardown_engine()

    def _after_login(self) -> None:
        self.sessionChanged.emit()
        self._layout = load_layout(self._layout_path)
        self.devicesChanged.emit()
        if self._layout is None:
            self._set_view("setup")
            return
        self._start_engine()

    # -- slots ------------------------------------------------------------

    @Slot(str, str)
    def log_in(self, email: str, password: str) -> None:
        try:
            self._session = session_actions.start(self._client, self._store, email, password)
        except Exception as exc:
            self._login_error = str(exc)
            self.loginErrorChanged.emit()
            return
        self._login_error = ""
        self.loginErrorChanged.emit()
        self._after_login()

    @Slot(str, str)
    def sign_up(self, email: str, password: str) -> None:
        try:
            auth.sign_up(self._client, email, password)
        except Exception as exc:
            self._login_error = str(exc)
            self.loginErrorChanged.emit()
            return
        self._login_error = ""
        self.loginErrorChanged.emit()
        self.toast.emit("Cuenta creada — confirma el email antes de ingresar")

    @Slot()
    def log_out(self) -> None:
        """Retire the engine stack, forget the session, and go back to the login view.

        `layout.json` is left on disk on purpose: the grid belongs to the machine and
        its team, not to whoever is signed in, so the next login finds the same pads.
        """
        self._teardown_engine()
        if (error := session_actions.discard(self._client, self._store)) is not None:
            self.toast.emit(f"No se pudo cerrar la sesión en el servidor: {error}")
        self._session, self._layout = None, None
        self.sessionChanged.emit()
        self.devicesChanged.emit()
        self._set_view("login")

    @Slot(str, str, int, int)
    def apply_devices(self, mic: str, out: str, rows: int, cols: int) -> None:
        previous = deepcopy(self._layout)
        self._teardown_engine()
        if self._layout is None:
            self._layout = GridLayout(rows=rows, cols=cols, mic=mic, out=out, blocksize=256)
        else:
            self._layout.mic, self._layout.out = mic, out
            self._layout.rows, self._layout.cols = rows, cols
        discarded = trim_cells_to_bounds(self._layout)
        self.devicesChanged.emit()
        if not self._start_engine():
            # The engine that was running is already gone and the new devices don't
            # work: keep the last configuration that did on disk (and in the setup
            # form) instead of persisting a layout that boots straight back to setup.
            if previous is not None:
                self._layout = previous
            self.devicesChanged.emit()
            return
        save_layout(self._layout_path, self._layout)
        if discarded:
            self.toast.emit(
                f"Se descartaron {len(discarded)} pads fuera de la nueva grilla"
            )

    @Slot()
    def open_settings(self) -> None:
        self._set_view("setup")

    @Slot()
    def cancel_settings(self) -> None:
        if self._engine is not None:
            self._set_view("board")

    @Slot()
    def stop_all(self) -> None:
        if self._engine is not None:
            self._engine.stop_all()

    # -- engine lifecycle ------------------------------------------------------------

    def _start_engine(self) -> bool:
        assert self._layout is not None and self._session is not None
        try:
            engine = self._engine_factory(self._layout)
        except Exception as exc:
            self._setup_error = str(exc)
            self.setupErrorChanged.emit()
            self._set_view("setup")
            return False
        self._engine = engine
        self._setup_error = ""
        self.setupErrorChanged.emit()
        self._grid = GridModel(
            engine, self._client, self._session, self._cache, self._hotkeys,
            self._layout, self._layout_path, parent=self,
        )
        self._grid.toast.connect(self.toast)
        self._bridge = EngineBridge(engine, parent=self)
        self._bridge.voice_states_updated.connect(self._grid.apply_voice_states)
        self._bridge.start()
        self.gridModelChanged.emit()
        self.bridgeChanged.emit()
        self._set_view("board")
        return True

    def _teardown_engine(self) -> None:
        """Retire the whole engine/model stack, leaving nothing that can still act.

        Both models are parented to this controller, so clearing the attribute only
        drops the Python reference — the C++ object stays alive and functional. They
        are detached (so in-flight work is ignored) and notified as gone before the
        deferred delete, which only runs once QML has rebound off them.
        """
        if self._bridge is not None:
            bridge, self._bridge = self._bridge, None
            bridge.stop()
            self.bridgeChanged.emit()
            bridge.deleteLater()
        # Drops every combo registered on the OS hook; the next GridModel registers
        # the shortcuts of the cells it actually shows, from scratch.
        self._hotkeys.stop()
        if self._grid is not None:
            grid, self._grid = self._grid, None
            grid.detach()
            self.gridModelChanged.emit()
            grid.deleteLater()
        if self._engine is not None:
            self._engine.stop()
            self._engine = None

    def _set_view(self, view: str) -> None:
        if view == self._view:
            return
        self._view = view
        self.viewChanged.emit()

    # -- properties ------------------------------------------------------------

    def _get_view(self) -> str:
        return self._view

    def _get_user_email(self) -> str:
        return self._session.email if self._session is not None else ""

    def _get_login_error(self) -> str:
        return self._login_error

    def _get_setup_error(self) -> str:
        return self._setup_error

    def _get_mic_name(self) -> str:
        return self._layout.mic if self._layout is not None else ""

    def _get_out_name(self) -> str:
        return self._layout.out if self._layout is not None else ""

    def _get_grid_rows(self) -> int:
        return self._layout.rows if self._layout is not None else _DEFAULT_ROWS

    def _get_grid_cols(self) -> int:
        return self._layout.cols if self._layout is not None else _DEFAULT_COLS

    def _get_input_devices(self) -> list[str]:
        return [d.name for d in self._backend.list_devices() if d.max_input_channels > 0]

    def _get_output_devices(self) -> list[str]:
        return [d.name for d in self._backend.list_devices() if d.max_output_channels > 0]

    def _get_grid_model(self) -> QObject | None:
        return self._grid

    def _get_bridge(self) -> QObject | None:
        return self._bridge

    def _get_library_model(self) -> QObject:
        return self._library

    def _get_update_model(self) -> QObject:
        return self._update

    view = Property(str, _get_view, notify=viewChanged)
    userEmail = Property(str, _get_user_email, notify=sessionChanged)
    loginError = Property(str, _get_login_error, notify=loginErrorChanged)
    setupError = Property(str, _get_setup_error, notify=setupErrorChanged)
    micName = Property(str, _get_mic_name, notify=devicesChanged)
    outName = Property(str, _get_out_name, notify=devicesChanged)
    gridRows = Property(int, _get_grid_rows, notify=devicesChanged)
    gridCols = Property(int, _get_grid_cols, notify=devicesChanged)
    # "QVariantList" is a runtime-only PySide6 type name for QML list properties;
    # the Property stub only declares `type: type`, hence the ignores below.
    inputDevices = Property(
        "QVariantList", _get_input_devices, notify=devicesChanged  # type: ignore[arg-type]
    )
    outputDevices = Property(
        "QVariantList", _get_output_devices, notify=devicesChanged  # type: ignore[arg-type]
    )
    gridModel = Property(QObject, _get_grid_model, notify=gridModelChanged)
    bridge = Property(QObject, _get_bridge, notify=bridgeChanged)
    libraryModel = Property(QObject, _get_library_model, constant=True)
    updateModel = Property(QObject, _get_update_model, constant=True)
