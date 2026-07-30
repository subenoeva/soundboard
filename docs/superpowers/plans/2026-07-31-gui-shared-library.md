# Compartir sonidos desde la GUI — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que soltar un archivo sobre una celda vacía de la rejilla lo suba automáticamente
a Supabase (nunca lo asigne como `LocalSource`), y que cualquier usuario pueda asignar a
una celda vacía un sonido que **otro** usuario ya subió, mediante un navegador de
biblioteca, sin salir de la GUI.

**Architecture:** Dos caminos nuevos hacia una celda vacía, ambos terminando en
`MainWindow._set_cell(Cell(source=RemoteSource(...)))`. Camino 1 (`ClipButton.file_dropped`
→ `MainWindow._assign_local_file`): valida el archivo con `audioio.load_mono_48k`, pone el
botón en `LOADING` y sube en background con un `UploadWorker(QRunnable)` nuevo que llama
`sounds.add_sound(client, session, path, name)` — copia estructural de
`download_worker.py`. Camino 2 (menú contextual → `assign_from_library_requested` →
`MainWindow._open_library_dialog`): abre `LibraryDialog` (nuevo `QDialog`), que carga
`sounds.list_sounds` + `auth.display_names` de forma síncrona al abrir, y devuelve
`(selected_id, selected_name)` a través de la callable inyectable `pick_library_sound`
(mismo patrón que `prompt_shortcut`). `MainWindow` gana un parámetro `session: Session`
obligatorio porque `add_sound` necesita `owner_id`; `ui/app.py` captura esa `Session`
(hoy descartada) y se la pasa.

**Tech Stack:** Python 3.13, `PySide6` (Qt6), `pytest-qt` (dev). Sin dependencias nuevas —
todo lo usado ya está instalado desde `2026-07-30-gui-design.md` §13.

**Spec:** `docs/superpowers/specs/2026-07-31-gui-shared-library-design.md` (extiende
`docs/superpowers/specs/2026-07-30-gui-design.md`).

## Global Constraints

- Python `>=3.13`.
- Frecuencia interna fija: **48000 Hz**, mono, `float32` — sin cambios en este plan.
- Nada bajo `src/soundboard/audio/` puede importar `ui/` ni PySide6. `ui/` es la única
  capa que importa PySide6; `sounds.add_sound` / `sounds.list_sounds` / `auth.display_names`
  ya viven en `remote/` y no cambian.
- Código, identificadores, docstrings y mensajes de commit en **inglés**. Documentación
  de producto (specs, planes) en **español**.
- Ningún fallo se traga en silencio: subida fallida, carga de biblioteca fallida — todo
  con mensaje explícito, nunca un éxito falso ni una excepción tragada.
- Límite de tamaño: si un fichero supera ~300 líneas, dividirlo.
- Sin dependencias nuevas (spec §10).
- Comandos: `.venv\Scripts\pytest.exe`, `.venv\Scripts\ruff.exe` y
  `.venv\Scripts\mypy.exe` ya funcionan directamente en este worktree (entorno
  sincronizado).

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `src/soundboard/ui/upload_worker.py` (nuevo) | `UploadWorker(QRunnable)`: sube en `QThreadPool`, señales `finished(object)` / `failed(str)` |
| `src/soundboard/ui/library_dialog.py` (nuevo) | `LibraryDialog(QDialog)`: lista sonidos compartidos (nombre + dueño), expone `selected_id`/`selected_name` |
| `src/soundboard/ui/grid.py` | + señal `assign_from_library_requested(int)`; `_show_context_menu` la ofrece solo si la celda está vacía |
| `src/soundboard/ui/main_window.py` | + parámetro `session`; `_assign_local_file` reescrito para subir; `_on_upload_ready`/`_on_upload_failed`; `_open_library_dialog`; `_active_uploads` |
| `src/soundboard/ui/app.py` | Captura la `Session` (hoy descartada) y la pasa a `MainWindow(...)` |
| `tests/unit/test_upload_worker.py` (nuevo) | `run()` con callable que devuelve `Sound` → `finished`; callable que lanza → `failed` |
| `tests/unit/test_library_dialog.py` (nuevo) | Carga de la lista, selección + aceptar, fallo de carga + reintentar |
| `tests/unit/test_grid.py` | + 2 tests: el ítem de menú aparece solo si la celda está vacía, y emite la señal correcta |
| `tests/unit/test_main_window.py` | Los 11 sitios existentes pasan `session`; `test_dropping_a_file_assigns_the_cell_and_persists_the_layout` reescrito para `RemoteSource`; 4 tests nuevos (owner_id correcto, subida fallida, asignar desde biblioteca vacía/ocupada) |
| `tests/unit/test_app.py` | + 2 tests: la `Session` correcta llega a `MainWindow` en ambas ramas (sesión ya guardada / login inline) |

---

### Task 1: `UploadWorker` — subida fuera del hilo de UI

**Files:**
- Create: `src/soundboard/ui/upload_worker.py`
- Test: `tests/unit/test_upload_worker.py`

**Interfaces:**
- Consumes: nada directamente (envuelve cualquier `Callable[[], Sound]`; en
  `main_window` esa callable es `lambda: sounds.add_sound(client, session, path, name)`).
- Produces:
  - `UploadWorker(upload: Callable[[], Sound])` — `QRunnable`.
    - `.signals.finished: Signal(object)` — emite el `Sound` subido.
    - `.signals.failed: Signal(str)` — emite el mensaje de la excepción.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_upload_worker.py`:

```python
from typing import Any

from PySide6.QtCore import QThreadPool

from soundboard.remote.models import Sound
from soundboard.ui.upload_worker import UploadWorker

_SOUND = Sound(
    id="sound-1",
    owner_id="owner-1",
    category_id=None,
    name="airhorn",
    sha256="deadbeef",
    storage_path="deadbeef.f32",
    source_filename="airhorn.wav",
    duration_frames=480,
    orig_samplerate=48_000,
    orig_channels=1,
    gain_db=0.0,
    trim_start_frames=0,
    trim_end_frames=None,
    loop=False,
    color=None,
)


def test_upload_worker_emits_finished_with_the_uploaded_sound(qtbot: Any) -> None:
    worker = UploadWorker(lambda: _SOUND)

    with qtbot.waitSignal(worker.signals.finished, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert blocker.args[0] is _SOUND


def test_upload_worker_emits_failed_with_the_exception_message(qtbot: Any) -> None:
    def _raise() -> Sound:
        raise RuntimeError("no network")

    worker = UploadWorker(_raise)

    with qtbot.waitSignal(worker.signals.failed, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert blocker.args[0] == "no network"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_upload_worker.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.ui.upload_worker'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/ui/upload_worker.py`:

```python
"""Uploads a locally-dropped file to the shared library, off the Qt UI thread."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from soundboard.remote.models import Sound


class _UploadSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class UploadWorker(QRunnable):
    def __init__(self, upload: Callable[[], Sound]) -> None:
        super().__init__()
        self._upload = upload
        self.signals = _UploadSignals()

    def run(self) -> None:
        try:
            sound = self._upload()
        except Exception as exc:  # background-thread boundary: never crash silently
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(sound)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_upload_worker.py -v`
Expected: 2 passed.

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/ui/upload_worker.py tests/unit/test_upload_worker.py
git commit -m "feat: add UploadWorker to upload a dropped file off the Qt thread"
```

---

### Task 2: `ClipGrid` — opción "Asignar desde biblioteca" en celdas vacías

**Files:**
- Modify: `src/soundboard/ui/grid.py`
- Test: `tests/unit/test_grid.py`

**Interfaces:**
- Consumes: `ClipButton.state -> ClipState` (ya existe, `ClipState.EMPTY`).
- Produces:
  - Nueva señal `assign_from_library_requested = Signal(int)`.
  - `_show_context_menu` añade la opción "Asignar desde biblioteca" (tercera, después de
    "Asignar atajo" y "Vaciar celda") solo cuando `button_at(index).state is
    ClipState.EMPTY`.

- [ ] **Step 1: Write the failing tests**

Añadir al final de `tests/unit/test_grid.py` (los imports existentes — `QMenu`,
`ClipGrid` — ya alcanzan, no hace falta agregar ninguno):

```python
def test_context_menu_offers_assign_from_library_only_when_the_cell_is_empty(
    qtbot, monkeypatch
) -> None:
    grid = ClipGrid(rows=1, cols=1)
    qtbot.addWidget(grid)
    captured_menus = []

    def fake_exec(self: QMenu, _pos: object) -> object:
        captured_menus.append(self)
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)

    grid._show_context_menu(0)
    assert [a.text() for a in captured_menus[0].actions()] == [
        "Asignar atajo",
        "Vaciar celda",
        "Asignar desde biblioteca",
    ]

    grid.button_at(0).assign("airhorn", None)
    grid._show_context_menu(0)
    assert [a.text() for a in captured_menus[1].actions()] == [
        "Asignar atajo",
        "Vaciar celda",
    ]


def test_context_menu_assign_from_library_emits_the_right_signal(qtbot, monkeypatch) -> None:
    grid = ClipGrid(rows=1, cols=1)
    qtbot.addWidget(grid)
    received = []
    grid.assign_from_library_requested.connect(received.append)

    def fake_exec(self: QMenu, _pos: object) -> object:
        return self.actions()[2]  # "Asignar desde biblioteca" is added third, cell empty

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    grid._show_context_menu(0)

    assert received == [0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_grid.py -v`
Expected: FAIL — `AttributeError: 'ClipGrid' object has no attribute
'assign_from_library_requested'` (o el assert de la lista de textos, según cuál test
corra primero).

- [ ] **Step 3: Write the implementation**

`src/soundboard/ui/grid.py` (reemplaza el contenido completo):

```python
"""The clip grid widget: click to play, drag a file in to assign, right-click to manage."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGridLayout, QMenu, QWidget

from soundboard.ui.clip_button import ClipButton, ClipState


class ClipGrid(QWidget):
    play_requested = Signal(int)
    file_dropped = Signal(int, str)
    assign_shortcut_requested = Signal(int)
    clear_requested = Signal(int)
    assign_from_library_requested = Signal(int)

    def __init__(self, rows: int, cols: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[ClipButton] = []
        layout = QGridLayout(self)
        for index in range(rows * cols):
            button = ClipButton(index)
            button.clicked.connect(lambda _checked=False, i=index: self.play_requested.emit(i))
            button.file_dropped.connect(self.file_dropped)
            button.customContextMenuRequested.connect(
                lambda _pos, i=index: self._show_context_menu(i)
            )
            layout.addWidget(button, index // cols, index % cols)
            self._buttons.append(button)

    def button_at(self, index: int) -> ClipButton:
        return self._buttons[index]

    def _show_context_menu(self, index: int) -> None:
        menu = QMenu(self)
        assign_action = menu.addAction("Asignar atajo")
        clear_action = menu.addAction("Vaciar celda")
        library_action = None
        if self.button_at(index).state is ClipState.EMPTY:
            library_action = menu.addAction("Asignar desde biblioteca")
        chosen = menu.exec(QCursor.pos())
        if chosen is assign_action:
            self.assign_shortcut_requested.emit(index)
        elif chosen is clear_action:
            self.clear_requested.emit(index)
        elif library_action is not None and chosen is library_action:
            self.assign_from_library_requested.emit(index)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_grid.py -v`
Expected: 7 passed (5 existentes + 2 nuevos).

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/ui/grid.py tests/unit/test_grid.py
git commit -m "feat: offer 'assign from library' in the context menu of empty cells"
```

---

### Task 3: `LibraryDialog` — navegador de sonidos compartidos

**Files:**
- Create: `src/soundboard/ui/library_dialog.py`
- Test: `tests/unit/test_library_dialog.py`

**Interfaces:**
- Consumes: `sounds.list_sounds(client: RemoteClient) -> list[Sound]`,
  `auth.display_names(client: RemoteClient, user_ids: Iterable[str]) -> dict[str, str]`
  (ambas ya existen, sin cambios).
- Produces:
  - `LibraryDialog(client: RemoteClient, parent: QWidget | None = None)` — `QDialog`.
    - `.selected_id: str | None`, `.selected_name: str | None` — fijados tras aceptar
      con una fila seleccionada.
    - Carga la lista de forma síncrona en `__init__`; si falla, oculta la lista y
      muestra el error + botón "Reintentar" (`._error`, `._retry_button`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_library_dialog.py`:

```python
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from PySide6.QtWidgets import QDialog

from soundboard.remote import sounds
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.remote.models import Sound
from soundboard.ui.library_dialog import LibraryDialog


def _add_sound(
    client: FakeRemoteClient, owner_email: str, tmp_path: Path, filename: str, sound_name: str
) -> Sound:
    session = client.sign_in_as_new_user(owner_email)
    client.insert(
        "profiles", {"id": session.user_id, "display_name": owner_email.split("@")[0]}
    )
    path = tmp_path / filename
    sf.write(str(path), np.zeros(480, dtype=np.float32), 48_000)
    return sounds.add_sound(client, session, str(path), name=sound_name)


def test_library_dialog_lists_each_sounds_name_and_owner(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    _add_sound(client, "beto@x.com", tmp_path, "b.wav", "applause")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)

    texts = {dialog._list.item(i).text() for i in range(dialog._list.count())}

    assert texts == {"airhorn — ana", "applause — beto"}


def test_selecting_a_row_and_accepting_exposes_selected_id_and_name(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    sound = _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)
    dialog._list.setCurrentRow(0)

    dialog._accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_id == sound.id
    assert dialog.selected_name == "airhorn"


def test_accepting_without_a_selection_does_nothing(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)

    dialog._accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.selected_id is None


class _FlakyOnceClient(FakeRemoteClient):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_select = False

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if table == "sounds" and self.fail_next_select:
            self.fail_next_select = False
            raise RuntimeError("sin red")
        return super().select(table, filters=filters)


def test_a_failed_load_shows_the_error_and_retry_reloads_it(qtbot: Any, tmp_path: Path) -> None:
    client = _FlakyOnceClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    client.fail_next_select = True

    dialog = LibraryDialog(client)
    qtbot.addWidget(dialog)

    assert "sin red" in dialog._error.text()
    assert dialog._list.isHidden()
    assert not dialog._error.isHidden()

    dialog._retry_button.click()

    assert dialog._list.count() == 1
    assert not dialog._list.isHidden()
    assert dialog._error.isHidden()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_library_dialog.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.ui.library_dialog'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/ui/library_dialog.py`:

```python
"""Lists every sound shared to the library so the user can assign one to an empty cell."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from soundboard.remote import auth, sounds
from soundboard.remote.models import RemoteClient, Sound


class LibraryDialog(QDialog):
    def __init__(self, client: RemoteClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de sonidos")
        self._client = client
        self.selected_id: str | None = None
        self.selected_name: str | None = None
        self._rows: list[tuple[str, str]] = []

        self._list = QListWidget()

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._retry_button = QPushButton("Reintentar")
        self._retry_button.clicked.connect(self._load)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addWidget(self._error)
        layout.addWidget(self._retry_button)
        layout.addWidget(buttons)

        self._load()

    def _load(self) -> None:
        try:
            available = sounds.list_sounds(self._client)
            owners = auth.display_names(self._client, {s.owner_id for s in available})
        except Exception as exc:  # dialog boundary: show it, offer to retry
            self._show_error(str(exc))
            return
        self._show_list(available, owners)

    def _show_list(self, available: list[Sound], owners: dict[str, str]) -> None:
        self._list.clear()
        self._rows = [(sound.id, sound.name) for sound in available]
        for sound in available:
            owner_name = owners.get(sound.owner_id, sound.owner_id)
            self._list.addItem(f"{sound.name} — {owner_name}")
        self._list.show()
        self._error.hide()
        self._retry_button.hide()

    def _show_error(self, message: str) -> None:
        self._list.hide()
        self._error.setText(message)
        self._error.show()
        self._retry_button.show()

    def _accept(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self.selected_id, self.selected_name = self._rows[row]
        self.accept()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_library_dialog.py -v`
Expected: 4 passed.

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/ui/library_dialog.py tests/unit/test_library_dialog.py
git commit -m "feat: add LibraryDialog to browse and pick a shared sound"
```

---

### Task 4: `MainWindow` — soltar un archivo lo sube y comparte (Camino 1)

**Files:**
- Modify: `src/soundboard/ui/main_window.py`
- Modify: `tests/unit/test_main_window.py`

**Interfaces:**
- Consumes: `UploadWorker(upload: Callable[[], Sound])` (Task 1),
  `sounds.add_sound(client: RemoteClient, session: Session, path: str, name: str) ->
  Sound` (ya existe).
- Produces:
  - `MainWindow.__init__` gana un parámetro posicional obligatorio `session: Session`
    (nuevo tercer argumento, entre `client` y `cache`).
  - `self._active_uploads: set[UploadWorker]`.
  - `_assign_local_file(index: int, path: str) -> None` — reescrito: valida, pone
    `LOADING`, sube en background.
  - `_on_upload_ready(index: int, worker: UploadWorker, sound: Sound) -> None`.
  - `_on_upload_failed(index: int, worker: UploadWorker, message: str) -> None`.

- [ ] **Step 1: Update the test file**

Reemplaza el contenido completo de `tests/unit/test_main_window.py`:

```python
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import Qt

from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.clip_button import ClipState
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, RemoteSource
from soundboard.ui.main_window import MainWindow


class _RecordingEngine:
    def __init__(self) -> None:
        self.played: list[np.ndarray] = []
        self.stopped_all = 0

    def play(self, pcm: np.ndarray, **kwargs: object) -> None:
        self.played.append(pcm)

    def stop_all(self) -> None:
        self.stopped_all += 1

    def stop(self) -> None:
        pass


def test_clicking_a_local_cell_plays_it(qtbot: Any, tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.5, dtype=np.float32), 48_000)
    engine = _RecordingEngine()
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip", shortcut=None)],
    )
    window = MainWindow(
        engine, client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window._grid.button_at(0), Qt.MouseButton.LeftButton)

    assert len(engine.played) == 1


def test_clicking_a_remote_cell_loads_then_plays(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.5, dtype=np.float32), 48_000)
    sound = sounds.add_sound(client, session, str(clip), name="laugh")
    engine = _RecordingEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id=sound.id), name="laugh", shortcut=None)],
    )
    window = MainWindow(
        engine, client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window._grid.button_at(0), Qt.MouseButton.LeftButton)

    assert window._grid.button_at(0).state is ClipState.LOADING
    qtbot.waitUntil(lambda: len(engine.played) == 1, timeout=2000)
    assert window._grid.button_at(0).state is ClipState.IDLE


def test_a_remote_download_failure_shows_the_error_and_resets_the_button(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    engine = _RecordingEngine()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id="missing-id"), name="ghost", shortcut=None)],
    )
    window = MainWindow(
        engine, client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window._grid.button_at(0), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window._grid.button_at(0).state is ClipState.IDLE, timeout=2000)

    assert engine.played == []
    assert window.statusBar().currentMessage()


def test_dropping_a_file_assigns_the_cell_and_persists_the_layout(
    qtbot: Any, tmp_path: Path
) -> None:
    clip = tmp_path / "airhorn.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    layout_path = tmp_path / "ui_layout.json"
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, layout_path,
    )
    qtbot.addWidget(window)

    window._grid.button_at(0).file_dropped.emit(0, str(clip))

    qtbot.waitUntil(lambda: window._grid.button_at(0).state is ClipState.IDLE, timeout=2000)
    cell = window._cell_at(0)
    assert cell is not None
    assert isinstance(cell.source, RemoteSource)
    assert "airhorn" in window._grid.button_at(0).text()
    assert layout_path.exists()


def test_dropping_a_file_uploads_it_with_the_current_users_owner_id(
    qtbot: Any, tmp_path: Path
) -> None:
    clip = tmp_path / "airhorn.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    window._grid.button_at(0).file_dropped.emit(0, str(clip))
    qtbot.waitUntil(lambda: window._grid.button_at(0).state is ClipState.IDLE, timeout=2000)

    cell = window._cell_at(0)
    assert cell is not None
    assert isinstance(cell.source, RemoteSource)
    rows = client.select("sounds", filters={"id": cell.source.id})
    assert rows and rows[0]["owner_id"] == session.user_id


def test_a_failed_upload_shows_an_error_and_leaves_the_cell_empty(
    qtbot: Any, tmp_path: Path
) -> None:
    clip = tmp_path / "airhorn.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)

    class _FailingUploadClient(FakeRemoteClient):
        def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
            raise RuntimeError("bucket unreachable")

    client = _FailingUploadClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    layout_path = tmp_path / "ui_layout.json"
    errors: list[str] = []
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, layout_path,
        message_box=lambda _parent, _title, message: errors.append(message),
    )
    qtbot.addWidget(window)

    window._grid.button_at(0).file_dropped.emit(0, str(clip))
    qtbot.waitUntil(lambda: window._grid.button_at(0).state is ClipState.EMPTY, timeout=2000)

    assert errors == ["bucket unreachable"]
    assert window._layout.cells == []


def test_dropping_an_undecodable_file_shows_an_error_and_leaves_the_cell_empty(
    qtbot: Any, tmp_path: Path
) -> None:
    bogus = tmp_path / "not_audio.txt"
    bogus.write_text("hello")
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
        message_box=lambda *_args: None,
    )
    qtbot.addWidget(window)

    window._grid.button_at(0).file_dropped.emit(0, str(bogus))

    assert window._grid.button_at(0).state is ClipState.EMPTY


def test_a_registered_hotkey_triggers_playback(qtbot: Any, tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.5, dtype=np.float32), 48_000)
    engine = _RecordingEngine()
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip",
                     shortcut="<ctrl>+<alt>+1")],
    )
    window = MainWindow(
        engine, client, session, SoundCache(tmp_path / "cache"),
        hotkeys, layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    hotkeys.trigger("<ctrl>+<alt>+1")

    assert len(engine.played) == 1


def test_clear_cell_unregisters_its_hotkey_and_empties_the_button(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path="x.wav"), name="clip",
                     shortcut="<ctrl>+<alt>+1")],
    )
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        hotkeys, layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    window._grid.clear_requested.emit(0)

    assert window._grid.button_at(0).state is ClipState.EMPTY
    with pytest.raises(KeyError):
        hotkeys.trigger("<ctrl>+<alt>+1")


def test_stop_all_toolbar_action_calls_the_engine(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    engine = _RecordingEngine()
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        engine, client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)

    window._stop_all_action.trigger()

    assert engine.stopped_all == 1


def test_closing_the_window_hides_it_instead_of_closing(qtbot: Any, tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
    )
    qtbot.addWidget(window)
    window.show()

    window.close()

    assert not window.isVisible()
    assert window.isHidden()


def test_assign_shortcut_registers_it_and_persists_the_layout(qtbot: Any, tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip", shortcut=None)],
    )
    layout_path = tmp_path / "ui_layout.json"
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        hotkeys, layout, layout_path,
        prompt_shortcut=lambda *_args: ("<ctrl>+<alt>+5", True),
    )
    qtbot.addWidget(window)

    window._grid.assign_shortcut_requested.emit(0)

    hotkeys.trigger("<ctrl>+<alt>+5")  # raises KeyError if registration didn't happen
    assert layout_path.exists()
    assert "<ctrl>+<alt>+5" in window._grid.button_at(0).text()


def test_assign_shortcut_with_a_malformed_combo_shows_an_error_and_registers_nothing(
    qtbot: Any, tmp_path: Path
) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    hotkeys = FakeHotkeyManager()
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=LocalSource(path=str(clip)), name="clip", shortcut=None)],
    )
    errors = []
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        hotkeys, layout, tmp_path / "ui_layout.json",
        message_box=lambda _parent, _title, message: errors.append(message),
        prompt_shortcut=lambda *_args: ("not-a-combo!!", True),
    )
    qtbot.addWidget(window)

    window._grid.assign_shortcut_requested.emit(0)

    assert errors
    cell = window._cell_at(0)
    assert cell is not None
    assert cell.shortcut is None


def test_assign_from_library_on_an_empty_cell_sets_a_remote_source(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(rows=1, cols=1, mic="mic", out="cable", blocksize=256)
    layout_path = tmp_path / "ui_layout.json"
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, layout_path,
        pick_library_sound=lambda *_args: ("sound-id", "applause"),
    )
    qtbot.addWidget(window)

    window._grid.assign_from_library_requested.emit(0)

    cell = window._cell_at(0)
    assert cell is not None
    assert cell.source == RemoteSource(id="sound-id")
    assert cell.name == "applause"
    assert layout_path.exists()


def test_assign_from_library_on_an_occupied_cell_does_nothing(
    qtbot: Any, tmp_path: Path
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    layout = GridLayout(
        rows=1, cols=1, mic="mic", out="cable", blocksize=256,
        cells=[Cell(index=0, source=RemoteSource(id="existing"), name="existing", shortcut=None)],
    )
    calls: list[object] = []
    window = MainWindow(
        _RecordingEngine(), client, session, SoundCache(tmp_path / "cache"),
        FakeHotkeyManager(), layout, tmp_path / "ui_layout.json",
        pick_library_sound=lambda *args: calls.append(args) or ("sound-id", "applause"),
    )
    qtbot.addWidget(window)

    window._grid.assign_from_library_requested.emit(0)

    assert calls == []
    cell = window._cell_at(0)
    assert cell is not None
    assert cell.source == RemoteSource(id="existing")
```

Nota: los últimos dos tests (`test_assign_from_library_on_an_empty_cell_sets_a_remote_source`
y `test_assign_from_library_on_an_occupied_cell_does_nothing`) usan
`pick_library_sound`, que todavía no existe en `MainWindow` — fallarán con `TypeError`
hasta el Task 5. Es intencional: quedan escritos aquí porque viven en el mismo fichero,
pero no se espera que pasen hasta terminar el Task 5.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_main_window.py -v`
Expected: FAIL — `TypeError: MainWindow.__init__() takes ... positional arguments` en
casi todos los tests (la firma real todavía no acepta `session`), y `TypeError:
unexpected keyword argument 'pick_library_sound'` en los dos últimos.

- [ ] **Step 3: Write the implementation**

`src/soundboard/ui/main_window.py` (reemplaza el contenido completo):

```python
"""Wires the clip grid, tray icon and hotkeys to the audio engine and remote library."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Protocol

import numpy as np
from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
    QWidget,
)

from soundboard.audioio import load_mono_48k
from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.models import RemoteClient, Session, Sound
from soundboard.ui.clip_button import ClipButton, ClipState
from soundboard.ui.download_worker import DownloadWorker
from soundboard.ui.grid import ClipGrid
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource, RemoteSource, save_layout
from soundboard.ui.upload_worker import UploadWorker


class Engine(Protocol):
    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> None: ...
    def stop_all(self) -> None: ...


def _default_message_box(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


class MainWindow(QMainWindow):
    def __init__(
        self,
        engine: Engine,
        client: RemoteClient,
        session: Session,
        cache: SoundCache,
        hotkeys: HotkeyManager,
        layout: GridLayout,
        layout_path: Path,
        message_box: Callable[[QWidget, str, str], None] = _default_message_box,
        prompt_shortcut: Callable[[QWidget, str, str], tuple[str, bool]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Soundboard")
        self._engine = engine
        self._client = client
        self._session = session
        self._cache = cache
        self._hotkeys = hotkeys
        self._layout = layout
        self._layout_path = layout_path
        self._message_box = message_box
        self._prompt_shortcut = prompt_shortcut or (
            lambda parent, title, label: QInputDialog.getText(parent, title, label)
        )
        self._pool = QThreadPool.globalInstance()
        self._active_downloads: set[DownloadWorker] = set()
        self._active_uploads: set[UploadWorker] = set()

        self._grid = ClipGrid(layout.rows, layout.cols)
        self.setCentralWidget(self._grid)
        self._grid.play_requested.connect(self._play)
        self._grid.file_dropped.connect(self._assign_local_file)
        self._grid.clear_requested.connect(self._clear_cell)
        self._grid.assign_shortcut_requested.connect(self._assign_shortcut)

        toolbar = QToolBar()
        self._stop_all_action = toolbar.addAction("Detener todo")
        self._stop_all_action.triggered.connect(self._engine.stop_all)
        self.addToolBar(toolbar)

        status = QStatusBar()
        self.setStatusBar(status)
        self._metrics_timer = QTimer(self)
        self._metrics_timer.timeout.connect(self._update_metrics)
        self._metrics_timer.start(500)

        for cell in layout.cells:
            self._apply_cell(cell)

    def _apply_cell(self, cell: Cell) -> None:
        self._grid.button_at(cell.index).assign(cell.name, cell.shortcut)
        if cell.shortcut:
            self._hotkeys.register(cell.shortcut, partial(self._play, cell.index))

    def _cell_at(self, index: int) -> Cell | None:
        return next((c for c in self._layout.cells if c.index == index), None)

    def _play(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        button = self._grid.button_at(index)
        if isinstance(cell.source, LocalSource):
            self._engine.play(load_mono_48k(cell.source.path))
            return
        self._play_remote(button, cell.source)

    def _play_remote(self, button: ClipButton, source: RemoteSource) -> None:
        button.set_state(ClipState.LOADING)

        def resolve() -> np.ndarray:
            sound = sounds.get_sound(self._client, source.id)
            return sounds.resolve_pcm(self._client, self._cache, sound)

        worker = DownloadWorker(resolve)
        # QThreadPool doesn't keep Python's refcount alive across the thread hop —
        # without this, the worker (and its bound signals) can be garbage collected
        # before `run()` finishes, silently dropping the finished/failed signal.
        self._active_downloads.add(worker)
        worker.signals.finished.connect(
            lambda pcm, b=button, w=worker: self._on_remote_ready(b, w, pcm)
        )
        worker.signals.failed.connect(
            lambda message, b=button, w=worker: self._on_remote_failed(b, w, message)
        )
        self._pool.start(worker)

    def _on_remote_ready(self, button: ClipButton, worker: DownloadWorker, pcm: np.ndarray) -> None:
        self._active_downloads.discard(worker)
        button.set_state(ClipState.IDLE)
        self._engine.play(pcm)

    def _on_remote_failed(self, button: ClipButton, worker: DownloadWorker, message: str) -> None:
        self._active_downloads.discard(worker)
        button.set_state(ClipState.IDLE)
        self.statusBar().showMessage(f"error: {message}", 5000)

    def _assign_local_file(self, index: int, path: str) -> None:
        try:
            load_mono_48k(path)
        except Exception as exc:
            self._message_box(self, "No se pudo asignar", str(exc))
            return
        name = Path(path).stem
        button = self._grid.button_at(index)
        button.set_state(ClipState.LOADING)

        def upload() -> Sound:
            return sounds.add_sound(self._client, self._session, path, name=name)

        worker = UploadWorker(upload)
        self._active_uploads.add(worker)
        worker.signals.finished.connect(
            lambda sound, i=index, w=worker: self._on_upload_ready(i, w, sound)
        )
        worker.signals.failed.connect(
            lambda message, i=index, w=worker: self._on_upload_failed(i, w, message)
        )
        self._pool.start(worker)

    def _on_upload_ready(self, index: int, worker: UploadWorker, sound: Sound) -> None:
        self._active_uploads.discard(worker)
        self._set_cell(
            Cell(index=index, source=RemoteSource(id=sound.id), name=sound.name, shortcut=None)
        )

    def _on_upload_failed(self, index: int, worker: UploadWorker, message: str) -> None:
        self._active_uploads.discard(worker)
        self._grid.button_at(index).set_state(ClipState.EMPTY)
        self._message_box(self, "No se pudo subir el sonido", message)

    def _set_cell(self, cell: Cell) -> None:
        self._layout.cells = [c for c in self._layout.cells if c.index != cell.index] + [cell]
        self._grid.button_at(cell.index).assign(cell.name, cell.shortcut)
        save_layout(self._layout_path, self._layout)

    def _clear_cell(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is not None and cell.shortcut:
            self._hotkeys.unregister(cell.shortcut)
        self._layout.cells = [c for c in self._layout.cells if c.index != index]
        self._grid.button_at(index).clear()
        save_layout(self._layout_path, self._layout)

    def _assign_shortcut(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        combo, ok = self._prompt_shortcut(
            self, "Asignar atajo", "Combinación (formato pynput, ej. <ctrl>+<alt>+1):"
        )
        if not ok or not combo:
            return
        try:
            self._hotkeys.register(combo, partial(self._play, index))
        except ValueError as exc:
            self._message_box(self, "Atajo inválido", str(exc))
            return
        if cell.shortcut:
            self._hotkeys.unregister(cell.shortcut)
        self._set_cell(Cell(index=cell.index, source=cell.source, name=cell.name, shortcut=combo))

    def _update_metrics(self) -> None:
        metrics = getattr(self._engine, "metrics", None)
        if metrics is not None:
            self.statusBar().showMessage(str(metrics))

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_main_window.py -v`
Expected: 13 passed, 2 failed (los dos tests de `pick_library_sound` — se resuelven en
el Task 5).

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores (los 2 tests que fallan son fallos de *runtime* esperados,
no de lint/tipos).

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/ui/main_window.py tests/unit/test_main_window.py
git commit -m "feat: upload a dropped file and share it instead of assigning it locally"
```

---

### Task 5: `MainWindow` — asignar desde biblioteca (Camino 2)

**Files:**
- Modify: `src/soundboard/ui/main_window.py`

**Interfaces:**
- Consumes: `LibraryDialog(client: RemoteClient, parent: QWidget | None = None)` (Task 3),
  `ClipGrid.assign_from_library_requested: Signal(int)` (Task 2).
- Produces:
  - `MainWindow.__init__` gana el parámetro opcional
    `pick_library_sound: Callable[[QWidget, RemoteClient], tuple[str, str] | None] |
    None = None`.
  - `_open_library_dialog(index: int) -> None`.

- [ ] **Step 1: Run the two pending tests to confirm they still fail as expected**

Run: `.venv\Scripts\pytest.exe tests/unit/test_main_window.py -k assign_from_library -v`
Expected: FAIL — `TypeError: MainWindow.__init__() got an unexpected keyword argument
'pick_library_sound'` (ya escritos en el Task 4, sin implementación todavía).

- [ ] **Step 2: Add the import, the default picker, the constructor parameter and the wiring**

En `src/soundboard/ui/main_window.py`:

Reemplaza el bloque de imports de `PySide6.QtWidgets`:

```python
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
    QWidget,
)
```

Añade el import de `LibraryDialog` junto a los demás imports de `soundboard.ui`:

```python
from soundboard.ui.library_dialog import LibraryDialog
```

Añade, después de `_default_message_box`:

```python
def _default_pick_library_sound(
    parent: QWidget, client: RemoteClient
) -> tuple[str, str] | None:
    dialog = LibraryDialog(client, parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    assert dialog.selected_id is not None and dialog.selected_name is not None
    return dialog.selected_id, dialog.selected_name
```

En la firma de `MainWindow.__init__`, añade el parámetro nuevo justo antes de `parent`:

```python
        prompt_shortcut: Callable[[QWidget, str, str], tuple[str, bool]] | None = None,
        pick_library_sound: Callable[[QWidget, RemoteClient], tuple[str, str] | None]
        | None = None,
        parent: QWidget | None = None,
    ) -> None:
```

En el cuerpo de `__init__`, después de la línea que fija `self._prompt_shortcut`:

```python
        self._pick_library_sound = pick_library_sound or _default_pick_library_sound
```

Justo después de `self._grid.assign_shortcut_requested.connect(self._assign_shortcut)`:

```python
        self._grid.assign_from_library_requested.connect(self._open_library_dialog)
```

Añade un método nuevo, después de `_assign_shortcut`:

```python
    def _open_library_dialog(self, index: int) -> None:
        if self._cell_at(index) is not None:
            return
        picked = self._pick_library_sound(self, self._client)
        if picked is None:
            return
        selected_id, selected_name = picked
        self._set_cell(
            Cell(index=index, source=RemoteSource(id=selected_id), name=selected_name,
                 shortcut=None)
        )
```

- [ ] **Step 3: Run the full test file to verify everything passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_main_window.py -v`
Expected: 15 passed.

- [ ] **Step 4: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/main_window.py
git commit -m "feat: assign an empty cell from a sound another user already shared"
```

---

### Task 6: `ui/app.py` — pasar la `Session` a `MainWindow`

**Files:**
- Modify: `src/soundboard/ui/app.py`
- Modify: `tests/unit/test_app.py`

**Interfaces:**
- Consumes: `LoginDialog.session: Session | None` (ya existe),
  `auth.require_session(client, store) -> Session` (ya existe, su valor de retorno hoy
  se descarta).
- Produces: `run_gui` construye `MainWindow(engine, client, session, cache, hotkeys,
  layout, layout_path)` con una `session: Session` real en ambas ramas (sesión ya
  guardada / login inline).

- [ ] **Step 1: Write the failing tests**

Añadir al final de `tests/unit/test_app.py` (los imports existentes ya alcanzan):

```python
def test_run_gui_passes_the_restored_session_to_the_main_window(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)
    layout_path = tmp_path / "ui_layout.json"
    save_layout(
        layout_path,
        GridLayout(rows=1, cols=1, mic="fake microphone", out="fake cable", blocksize=64),
    )
    monkeypatch.setattr(app_module, "default_layout_path", lambda: layout_path)
    captured: list[object] = []
    real_main_window = app_module.MainWindow

    def _spy_main_window(engine, client_arg, session_arg, *rest, **kwargs):
        captured.append(session_arg)
        return real_main_window(engine, client_arg, session_arg, *rest, **kwargs)

    monkeypatch.setattr(app_module, "MainWindow", _spy_main_window)

    exit_code = run_gui(
        client=client, store=store, backend=FakeBackend(), hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 0
    assert captured == [session]


def test_run_gui_passes_the_freshly_logged_in_session_to_the_main_window(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    store = SessionStore(backend=_DictKeyringBackend())  # empty: store.load() is None
    layout_path = tmp_path / "ui_layout.json"
    save_layout(
        layout_path,
        GridLayout(rows=1, cols=1, mic="fake microphone", out="fake cable", blocksize=64),
    )
    monkeypatch.setattr(app_module, "default_layout_path", lambda: layout_path)

    def _fake_exec(self: LoginDialog) -> int:
        self.session = session
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(LoginDialog, "exec", _fake_exec)

    captured: list[object] = []
    real_main_window = app_module.MainWindow

    def _spy_main_window(engine, client_arg, session_arg, *rest, **kwargs):
        captured.append(session_arg)
        return real_main_window(engine, client_arg, session_arg, *rest, **kwargs)

    monkeypatch.setattr(app_module, "MainWindow", _spy_main_window)

    exit_code = run_gui(
        client=client, store=store, backend=FakeBackend(), hotkeys=FakeHotkeyManager(),
        exec_app=False,
    )

    assert exit_code == 0
    assert captured == [session]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_app.py -k passes_the -v`
Expected: FAIL — `TypeError` (la `MainWindow` real todavía espera `session` en la
posición de `cache`, y `run_gui` todavía no se lo pasa).

- [ ] **Step 3: Write the implementation**

En `src/soundboard/ui/app.py`, reemplaza:

```python
    if store.load() is None:
        login = LoginDialog(client, store)
        if login.exec() != QDialog.DialogCode.Accepted:
            return 1
    else:
        auth.require_session(client, store)
```

por:

```python
    if store.load() is None:
        login = LoginDialog(client, store)
        if login.exec() != QDialog.DialogCode.Accepted:
            return 1
        assert login.session is not None
        session = login.session
    else:
        session = auth.require_session(client, store)
```

y reemplaza:

```python
    cache = SoundCache(_default_cache_dir())
    window = MainWindow(engine, client, cache, hotkeys, layout, layout_path)
    window.show()
```

por:

```python
    cache = SoundCache(_default_cache_dir())
    window = MainWindow(engine, client, session, cache, hotkeys, layout, layout_path)
    window.show()
```

- [ ] **Step 4: Run the full test file to verify everything passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_app.py -v`
Expected: 7 passed (5 existentes + 2 nuevos).

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/ui/app.py tests/unit/test_app.py
git commit -m "feat: pass the resolved Supabase session into the main window"
```

---

## Verificación final

- [ ] `.venv\Scripts\pytest.exe -v` (suite completa por defecto) — todo en verde.
- [ ] `.venv\Scripts\ruff.exe check .` — sin errores.
- [ ] `.venv\Scripts\mypy.exe` — sin errores.
- [ ] `uv run soundboard gui` a mano, con dos usuarios distintos (dos perfiles/máquinas
  o dos cuentas de prueba contra el mismo proyecto Supabase local):
  - Soltar un `.wav` sobre una celda vacía en la sesión del usuario A → el botón pasa
    por `LOADING` y termina en `IDLE` con el nombre del archivo.
  - Iniciar sesión como el usuario B, clic derecho en una celda vacía → "Asignar desde
    biblioteca" → el sonido subido por A aparece listado como "{nombre} — {A}" →
    seleccionarlo y confirmar asigna la celda.
  - Repetir el drop con Supabase apagado (`supabase stop`) → `QMessageBox` con el error,
    la celda queda vacía.
  - Abrir el navegador de biblioteca con Supabase apagado → error inline + "Reintentar";
    reiniciar Supabase y reintentar carga la lista.
- [ ] Confirmar aparte (fuera de este plan, spec §9) que la migración
  `20260729000000_sounds_library.sql` está aplicada al proyecto Supabase real antes de
  considerar esta función lista para usuarios reales.
