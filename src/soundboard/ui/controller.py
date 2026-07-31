"""AppController: owns the session, the engine lifecycle and view navigation.

The QML front end binds to a single instance of this class. It plays the role
`app.py::run_gui` and `MainWindow` played for the QWidgets UI, but as a persistent
object with notify signals instead of a one-shot startup function — QML needs
something it can bind to and that reacts to state changes after construction.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from soundboard.audio.backend import AudioBackend
from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import auth
from soundboard.remote.models import RemoteClient, Session
from soundboard.ui.engine_bridge import EngineBridge
from soundboard.ui.engine_factory import Engine, Store, build_engine
from soundboard.ui.grid_model import GridModel
from soundboard.ui.layout_store import GridLayout, load_layout, save_layout
from soundboard.ui.library_model import LibraryModel

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

    # -- lifecycle ------------------------------------------------------------

    def bootstrap(self) -> None:
        if self._store.load() is not None:
            try:
                # auth.require_session is typed against the concrete SessionStore,
                # not the Store protocol self._store is declared with; it is
                # structurally compatible (SessionStore itself, or the tests'
                # duck-typed double).
                self._session = auth.require_session(
                    self._client, self._store  # type: ignore[arg-type]
                )
            except Exception:
                # Supabase rotates the refresh token; a token already consumed must
                # be treated as "no session", not as a crash (same reasoning as
                # app.py used to document).
                self._store.clear()
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
            self._session = auth.log_in(
                self._client, self._store,  # type: ignore[arg-type]
                email, password, lambda: email.split("@")[0],
            )
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

    @Slot(str, str, int, int)
    def apply_devices(self, mic: str, out: str, rows: int, cols: int) -> None:
        if self._layout is None:
            self._layout = GridLayout(rows=rows, cols=cols, mic=mic, out=out, blocksize=256)
        else:
            self._layout.mic, self._layout.out = mic, out
            self._layout.rows, self._layout.cols = rows, cols
        save_layout(self._layout_path, self._layout)
        self.devicesChanged.emit()
        self._teardown_engine()
        self._start_engine()

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

    def _start_engine(self) -> None:
        assert self._layout is not None and self._session is not None
        try:
            engine = self._engine_factory(self._layout)
        except Exception as exc:
            self._setup_error = str(exc)
            self.setupErrorChanged.emit()
            self._set_view("setup")
            return
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

    def _teardown_engine(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
            self.bridgeChanged.emit()
        if self._grid is not None:
            self._grid = None
            self.gridModelChanged.emit()
        self._hotkeys.stop()  # el GridModel nuevo re-registra los atajos de sus celdas
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
