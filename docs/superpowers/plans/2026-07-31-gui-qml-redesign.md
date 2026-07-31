# Rediseño de la GUI en Qt Quick — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la UI de QWidgets por una interfaz Qt Quick «dark studio» con feedback de reproducción por celda, VU meter, header de estado y color por celda, según [`../specs/2026-07-31-gui-qml-redesign-design.md`](../specs/2026-07-31-gui-qml-redesign-design.md).

**Architecture:** QML como vista tonta sobre modelos Python testeables sin renderizar (`GridModel`, `AppController`, `EngineBridge`, `LibraryModel`). El motor de audio gana identidad de voz (`voice_id`), progreso por voz y pico por bloque, expuestos sin violar la restricción del callback RT (solo asignaciones de atributo y reducciones numpy). Una sola ventana; las «pantallas» (login/setup/board) son un `Loader` conmutado por `App.view` (equivale al StackView del spec con menos estado).

**Tech Stack:** PySide6 (QtQml/QtQuick, ya incluido — sin dependencias nuevas), pytest + pytest-qt con `QT_QPA_PLATFORM=offscreen` (ya configurado en `tests/unit/conftest.py`).

## Global Constraints

- Rama de trabajo: `feature/gui-qml-redesign`. Nunca commitear en `master`. Sin worktrees.
- Código, identificadores, docstrings y mensajes de commit: **inglés**. Textos visibles de la UI: **español neutro** (nunca voseo: «confirma», no «confirmá»).
- Sin atribución a IA en commits/PRs (nada de Co-Authored-By: Claude ni «Generated with»).
- Cada archivo ≤ ~300 líneas (convención del proyecto).
- Después de cada tarea: `uv run pytest`, `uv run ruff check .`, `uv run mypy` — los tres verdes antes de commitear.
- Dirección de dependencias: nada bajo `audio/` importa `ui/`, `hotkeys.py`, `remote/`, PySide6 ni pynput. `ui/` es el único paquete que importa PySide6.
- Ruta RT (callbacks de audio): sin I/O, sin logging, sin `queue.Queue`, sin allocations no triviales — solo ops numpy y asignaciones de atributo.
- Convención de nombres en la frontera Python↔QML: **propiedades** expuestas a QML en camelCase (`userEmail`, `metricsText`); **slots** en snake_case (QML los llama tal cual: `App.log_in(...)`). Los componentes QML usan `property` con valores por defecto, **nunca** `required property`, para que el smoke test pueda instanciarlos sin contexto.
- El rol de estado de celda se llama `cellState` (no `state` — colisiona con `Item.state` de QML) y el de color `cellColor` (no `color` — colisiona con `Rectangle.color`).

---

### Task 1: `Voice` — identidad y progreso

**Files:**
- Modify: `src/soundboard/audio/voice.py`
- Test: `tests/unit/test_voice.py`

**Interfaces:**
- Produces: `Voice(pcm, gain=1.0, loop=False, start=0, end=None, voice_id=0)`; atributo `voice_id: int`; propiedad `progress: float` (0..1 dentro del rango `start..end`; `1.0` si `finished`).

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_voice.py`:

```python
def test_voice_id_defaults_to_zero_and_is_stored() -> None:
    pcm = np.zeros(10, dtype=np.float32)
    assert Voice(pcm).voice_id == 0
    assert Voice(pcm, voice_id=7).voice_id == 7


def test_progress_advances_from_zero_to_one() -> None:
    pcm = np.ones(100, dtype=np.float32)
    voice = Voice(pcm)
    assert voice.progress == 0.0
    out = np.zeros(50, dtype=np.float32)
    voice.mix_into(out)
    assert voice.progress == pytest.approx(0.5)
    voice.mix_into(out)
    assert voice.progress == pytest.approx(1.0)
    assert voice.finished


def test_progress_respects_trim_range() -> None:
    pcm = np.ones(100, dtype=np.float32)
    voice = Voice(pcm, start=20, end=60)
    out = np.zeros(20, dtype=np.float32)
    voice.mix_into(out)
    assert voice.progress == pytest.approx(0.5)  # 20 frames dentro de un rango de 40


def test_progress_is_one_for_empty_range() -> None:
    pcm = np.ones(10, dtype=np.float32)
    voice = Voice(pcm, start=5, end=5)
    assert voice.finished
    assert voice.progress == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_voice.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'voice_id'` / `AttributeError: 'Voice' object has no attribute 'progress'`

- [ ] **Step 3: Implement**

En `Voice.__init__`, añadir el parámetro y atributo `voice_id: int = 0` (después de `end`), y la propiedad:

```python
    @property
    def progress(self) -> float:
        """Fraction of the start..end range already played, 0..1."""
        span = self._end - self._start
        if span <= 0:
            return 1.0
        return min(1.0, (self._position - self._start) / span)
```

Nota: con `loop=True` la posición vuelve a `start` al terminar el ciclo, así que `progress` cicla 0→1 — comportamiento deseado para la barra de la celda.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_voice.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/voice.py tests/unit/test_voice.py
git commit -m "feat(audio): add voice_id and progress to Voice"
```

---

### Task 2: `Mixer` — `voice_states()` y `last_peak`

**Files:**
- Modify: `src/soundboard/audio/mixer.py`
- Test: `tests/unit/test_mixer.py`

**Interfaces:**
- Consumes: `Voice.voice_id`, `Voice.progress` (Task 1).
- Produces: `Mixer.voice_states() -> list[tuple[int, float]]` (pares `(voice_id, progress)` de voces no terminadas); atributo `Mixer.last_peak: float` (pico absoluto del último bloque de salida, tras el limiter).

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_mixer.py`:

```python
def test_voice_states_reports_id_and_progress() -> None:
    mixer = Mixer(blocksize=50)
    pcm = np.ones(100, dtype=np.float32) * 0.1
    mixer.add_voice(Voice(pcm, voice_id=3))
    mic = np.zeros(50, dtype=np.float32)
    out = np.zeros(50, dtype=np.float32)
    mixer.process(mic, out)
    states = mixer.voice_states()
    assert states == [(3, pytest.approx(0.5))]


def test_voice_states_drops_finished_voices() -> None:
    mixer = Mixer(blocksize=50)
    mixer.add_voice(Voice(np.ones(50, dtype=np.float32) * 0.1, voice_id=1))
    mic = np.zeros(50, dtype=np.float32)
    out = np.zeros(50, dtype=np.float32)
    mixer.process(mic, out)
    assert mixer.voice_states() == []


def test_last_peak_tracks_output_block() -> None:
    mixer = Mixer(blocksize=50)
    mic = np.zeros(50, dtype=np.float32)
    out = np.zeros(50, dtype=np.float32)
    mixer.process(mic, out)
    assert mixer.last_peak == 0.0
    mixer.add_voice(Voice(np.ones(100, dtype=np.float32) * 0.5, voice_id=1))
    mixer.process(mic, out)
    assert mixer.last_peak == pytest.approx(float(np.max(np.abs(out))))
    assert mixer.last_peak > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mixer.py -v`
Expected: FAIL — `AttributeError: 'Mixer' object has no attribute 'voice_states'`

- [ ] **Step 3: Implement**

En `Mixer.__init__` añadir `self.last_peak: float = 0.0`. Al final de `process()` (tras el último `np.multiply`):

```python
        self.last_peak = float(np.max(np.abs(out)))
```

Y el método (fuera de la ruta RT — lo llama el hilo de UI):

```python
    def voice_states(self) -> list[tuple[int, float]]:
        """Snapshot of (voice_id, progress) for the active voices.

        Called from the UI thread while the audio callback mutates the voice
        list; iterating a shallow copy under the GIL is safe, and a state one
        block stale is fine for painting a progress bar.
        """
        return [(v.voice_id, v.progress) for v in list(self._voices) if not v.finished]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mixer.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/mixer.py tests/unit/test_mixer.py
git commit -m "feat(audio): expose per-voice progress and output peak from Mixer"
```

---

### Task 3: `AudioEngine` — `play()` devuelve `voice_id`; delegados

**Files:**
- Modify: `src/soundboard/audio/engine.py`
- Test: `tests/unit/test_fake_backend.py` o nuevo `tests/unit/test_engine_voices.py` (crear nuevo)

**Interfaces:**
- Consumes: `Voice(..., voice_id=...)` (Task 1), `Mixer.voice_states()` / `Mixer.last_peak` (Task 2).
- Produces: `AudioEngine.play(pcm, *, gain=1.0, loop=False, start=0, end=None) -> int`; `AudioEngine.voice_states() -> list[tuple[int, float]]`; propiedad `AudioEngine.last_peak: float`.

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_engine_voices.py`:

```python
"""AudioEngine voice identity and level reporting, over FakeBackend."""

from __future__ import annotations

import numpy as np

from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.fake_backend import FakeBackend


def _running_engine() -> tuple[AudioEngine, FakeBackend]:
    backend = FakeBackend()
    engine = AudioEngine(backend, EngineConfig(blocksize=64))
    engine.start()
    return engine, backend


def test_play_returns_increasing_voice_ids() -> None:
    engine, _ = _running_engine()
    pcm = np.ones(256, dtype=np.float32) * 0.1
    first = engine.play(pcm)
    second = engine.play(pcm)
    assert first == 1
    assert second == 2
    engine.stop()


def test_voice_states_and_peak_after_processing() -> None:
    engine, backend = _running_engine()
    pcm = np.ones(1024, dtype=np.float32) * 0.5
    voice_id = engine.play(pcm)
    backend.advance_blocks(2)  # ver nota del Step 2
    states = dict(engine.voice_states())
    assert voice_id in states
    assert 0.0 < states[voice_id] < 1.0
    assert engine.last_peak > 0.0
    engine.stop()
```

**Nota:** revisar `src/soundboard/audio/fake_backend.py` para el método real que dispara callbacks (`advance_blocks`, `step`, o similar — usar el que ya usan `tests/unit/test_fake_backend.py`). Ajustar el nombre en el test; el resto no cambia.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_engine_voices.py -v`
Expected: FAIL — `play()` devuelve `None`, `AudioEngine` no tiene `voice_states`

- [ ] **Step 3: Implement**

En `engine.py`: `import itertools`; en `__init__` añadir `self._voice_ids = itertools.count(1)`. Cambiar `play`:

```python
    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> int:
        """Queue a clip for playback; returns its voice id. Safe from any thread.

        The id comes from itertools.count, whose next() is a single C call and
        therefore safe under concurrent callers (Qt thread + pynput hotkey thread).
        """
        voice_id = next(self._voice_ids)
        voice = Voice(pcm, gain=gain, loop=loop, start=start, end=end, voice_id=voice_id)
        self._commands.append(("play", voice))
        return voice_id
```

Y los delegados:

```python
    def voice_states(self) -> list[tuple[int, float]]:
        """(voice_id, progress) snapshot; safe to call from the UI thread."""
        return self._mixer.voice_states()

    @property
    def last_peak(self) -> float:
        return self._mixer.last_peak
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_engine_voices.py tests/unit/ -v && uv run ruff check . && uv run mypy`
Expected: PASS (toda la suite — `cli.py` y `main_window.py` ignoran el nuevo return, compatible)

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/engine.py tests/unit/test_engine_voices.py
git commit -m "feat(audio): return voice ids from play and expose voice states"
```

---

### Task 4: `layout_store` — campo `color` por celda

**Files:**
- Modify: `src/soundboard/ui/layout_store.py`
- Test: `tests/unit/test_layout_store.py`

**Interfaces:**
- Produces: `Cell(index, source, name, shortcut=None, color: str | None = None)`; round-trip JSON con `color`; JSON antiguo sin el campo carga con `color=None`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_layout_store.py`:

```python
def test_cell_color_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    layout = GridLayout(rows=1, cols=2, mic="m", out="o", blocksize=256)
    layout.cells = [
        Cell(index=0, source=LocalSource(path="a.wav"), name="a", color="#e8590c"),
        Cell(index=1, source=LocalSource(path="b.wav"), name="b"),
    ]
    save_layout(path, layout)
    loaded = load_layout(path)
    assert loaded is not None
    assert loaded.cells[0].color == "#e8590c"
    assert loaded.cells[1].color is None


def test_legacy_layout_without_color_loads(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps({
        "rows": 1, "cols": 1, "mic": "m", "out": "o", "blocksize": 256,
        "cells": [{"index": 0, "source": {"type": "local", "path": "a.wav"},
                   "name": "a", "shortcut": None}],
    }))
    loaded = load_layout(path)
    assert loaded is not None
    assert loaded.cells[0].color is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_layout_store.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'color'`

- [ ] **Step 3: Implement**

En `Cell` añadir `color: str | None = None`. En `_cell_to_dict` añadir `"color": cell.color`. En `_cell_from_dict` añadir `color=data.get("color")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_layout_store.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/layout_store.py tests/unit/test_layout_store.py
git commit -m "feat(ui): add optional per-cell color to the grid layout"
```

---

### Task 5: `GridModel` — modelo de lectura + atajos

**Files:**
- Create: `src/soundboard/ui/grid_model.py`
- Test: `tests/unit/test_grid_model.py`

**Interfaces:**
- Consumes: `Cell`/`GridLayout` con `color` (Task 4), `HotkeyManager`, `Engine.play() -> int` (Task 3).
- Produces (para QML y tareas 6-7, 10):
  - Constantes de módulo `STATE_EMPTY = "empty"`, `STATE_IDLE = "idle"`, `STATE_LOADING = "loading"`, `STATE_PLAYING = "playing"`.
  - `class Engine(Protocol)` con `play(pcm, *, gain=1.0, loop=False, start=0, end=None) -> int`, `stop_all() -> None`, `stop() -> None`.
  - `GridModel(engine, client, session, cache, hotkeys, layout, layout_path, parent=None)` — `QAbstractListModel`.
  - Roles: `NAME_ROLE`→`b"name"`, `SHORTCUT_ROLE`→`b"shortcut"`, `COLOR_ROLE`→`b"cellColor"`, `STATE_ROLE`→`b"cellState"`, `PROGRESS_ROLE`→`b"progress"`.
  - Señal `toast = Signal(str)`. Señal interna `_hotkey_pressed = Signal(int)` conectada a `play` (rebota el hilo de pynput al hilo Qt — la conexión auto se vuelve queued en emisión cross-thread).

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_grid_model.py`:

```python
"""GridModel: headless list model over GridLayout, no QML rendering needed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.grid_model import (
    STATE_EMPTY,
    STATE_IDLE,
    GridModel,
)
from soundboard.ui.layout_store import Cell, GridLayout, LocalSource


class FakeEngine:
    def __init__(self) -> None:
        self.played: list[np.ndarray] = []
        self.states: list[tuple[int, float]] = []
        self.stopped = False
        self._next = 0

    def play(self, pcm: np.ndarray, **kwargs: object) -> int:
        self.played.append(pcm)
        self._next += 1
        return self._next

    def stop_all(self) -> None:
        self.stopped = True

    def stop(self) -> None:
        pass


@pytest.fixture
def hotkeys() -> FakeHotkeyManager:
    return FakeHotkeyManager()


def make_model(
    tmp_path: Path, hotkeys: FakeHotkeyManager, cells: list[Cell] | None = None
) -> tuple[GridModel, FakeEngine, GridLayout]:
    engine = FakeEngine()
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("user@example.com")
    layout = GridLayout(rows=2, cols=3, mic="m", out="o", blocksize=256,
                        cells=cells or [])
    model = GridModel(engine, client, session, SoundCache(tmp_path / "cache"),
                      hotkeys, layout, tmp_path / "layout.json")
    return model, engine, layout


def test_row_count_is_rows_times_cols(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    model, _, _ = make_model(tmp_path, hotkeys)
    assert model.rowCount() == 6


def test_data_for_empty_and_assigned_cells(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    cell = Cell(index=1, source=LocalSource(path="a.wav"), name="airhorn",
                shortcut="<ctrl>+1", color="#e8590c")
    model, _, _ = make_model(tmp_path, hotkeys, cells=[cell])
    empty = model.index(0)
    assigned = model.index(1)
    assert model.data(empty, GridModel.STATE_ROLE) == STATE_EMPTY
    assert model.data(empty, GridModel.NAME_ROLE) == ""
    assert model.data(assigned, GridModel.STATE_ROLE) == STATE_IDLE
    assert model.data(assigned, GridModel.NAME_ROLE) == "airhorn"
    assert model.data(assigned, GridModel.SHORTCUT_ROLE) == "<ctrl>+1"
    assert model.data(assigned, GridModel.COLOR_ROLE) == "#e8590c"
    assert model.data(assigned, GridModel.PROGRESS_ROLE) == 0.0


def test_role_names_are_qml_safe(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    model, _, _ = make_model(tmp_path, hotkeys)
    names = set(model.roleNames().values())
    assert names == {b"name", b"shortcut", b"cellColor", b"cellState", b"progress"}


def test_saved_shortcuts_are_registered_at_init(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a", shortcut="<ctrl>+1")
    make_model(tmp_path, hotkeys, cells=[cell])
    hotkeys.trigger("<ctrl>+1")  # no debe lanzar KeyError
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_grid_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'soundboard.ui.grid_model'`

- [ ] **Step 3: Implement**

Crear `src/soundboard/ui/grid_model.py`:

```python
"""List model behind the QML clip grid: cell contents, runtime state, hotkeys."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)

from soundboard.hotkeys import HotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.models import RemoteClient, Session
from soundboard.ui.layout_store import Cell, GridLayout

STATE_EMPTY = "empty"
STATE_IDLE = "idle"
STATE_LOADING = "loading"
STATE_PLAYING = "playing"


class Engine(Protocol):
    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> int: ...
    def stop_all(self) -> None: ...
    def stop(self) -> None: ...


class GridModel(QAbstractListModel):
    NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    SHORTCUT_ROLE = NAME_ROLE + 1
    COLOR_ROLE = NAME_ROLE + 2
    STATE_ROLE = NAME_ROLE + 3
    PROGRESS_ROLE = NAME_ROLE + 4

    toast = Signal(str)
    # pynput delivers hotkeys on its own thread; emitting a signal bounces the
    # call onto the Qt thread (auto connection turns queued cross-thread), so
    # play() and its dataChanged emissions always run where Qt requires them.
    _hotkey_pressed = Signal(int)

    def __init__(
        self,
        engine: Engine,
        client: RemoteClient,
        session: Session,
        cache: SoundCache,
        hotkeys: HotkeyManager,
        layout: GridLayout,
        layout_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._client = client
        self._session = session
        self._cache = cache
        self._hotkeys = hotkeys
        self._layout = layout
        self._layout_path = layout_path
        self._states: dict[int, str] = {}
        self._progress: dict[int, float] = {}
        self._voice_by_cell: dict[int, int] = {}
        self._active_workers: set[QObject] = set()
        self._hotkey_pressed.connect(self.play)
        for cell in layout.cells:
            if cell.shortcut:
                self._hotkeys.register(
                    cell.shortcut, partial(self._hotkey_pressed.emit, cell.index)
                )

    def play(self, index: int) -> None:  # noqa: D102 — filled in by the playback task
        raise NotImplementedError

    def rowCount(  # noqa: N802 — Qt override
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return self._layout.rows * self._layout.cols

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        i = index.row()
        cell = self._cell_at(i)
        if role == self.NAME_ROLE:
            return cell.name if cell else ""
        if role == self.SHORTCUT_ROLE:
            return (cell.shortcut or "") if cell else ""
        if role == self.COLOR_ROLE:
            return (cell.color or "") if cell else ""
        if role == self.STATE_ROLE:
            return self._states.get(i, STATE_IDLE if cell else STATE_EMPTY)
        if role == self.PROGRESS_ROLE:
            return self._progress.get(i, 0.0)
        return None

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802 — Qt override
        return {
            self.NAME_ROLE: b"name",
            self.SHORTCUT_ROLE: b"shortcut",
            self.COLOR_ROLE: b"cellColor",
            self.STATE_ROLE: b"cellState",
            self.PROGRESS_ROLE: b"progress",
        }

    def _cell_at(self, index: int) -> Cell | None:
        return next((c for c in self._layout.cells if c.index == index), None)

    def _emit_row_changed(self, index: int, roles: list[int]) -> None:
        model_index = self.index(index)
        self.dataChanged.emit(model_index, model_index, roles)
```

(`play` como `NotImplementedError` dura solo hasta la Task 6; el test de atajos de esta task no lo dispara — `trigger` emite la señal y la entrega queda encolada, no ejecutada, sin loop de eventos corriendo.)

**Nota:** si ese encolado sí se ejecuta bajo pytest-qt (depende de si hay `QApplication` activa — el fixture `qtbot`/`qapp` la crea), cambiar el cuerpo de `play` a `return None` temporalmente en vez de `raise`. Decidirlo según lo que haga la suite, no dejar el test rojo.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_grid_model.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/grid_model.py tests/unit/test_grid_model.py
git commit -m "feat(ui): add GridModel list model over the grid layout"
```

---

### Task 6: `GridModel` — reproducción y tracking de voces

**Files:**
- Modify: `src/soundboard/ui/grid_model.py`
- Test: `tests/unit/test_grid_model.py`

**Interfaces:**
- Consumes: `DownloadWorker` (existente), `sounds.get_sound` / `sounds.resolve_pcm`, `load_mono_48k`.
- Produces: slot `play(index: int)`; método `apply_voice_states(states: list[tuple[int, float]]) -> None` (lo llama `EngineBridge`, Task 8).

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_grid_model.py` (el helper `make_wav` puede copiarse de cómo `tests/unit/test_main_window.py` genera WAVs — revisar ese archivo antes de escribirlo y reutilizar su patrón exacto):

```python
def test_play_local_cell_plays_and_tracks_voice(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: object
) -> None:
    wav = make_wav(tmp_path / "a.wav")
    cell = Cell(index=0, source=LocalSource(path=str(wav)), name="a")
    model, engine, _ = make_model(tmp_path, hotkeys, cells=[cell])
    model.play(0)
    assert len(engine.played) == 1
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_PLAYING


def test_play_empty_cell_is_noop(tmp_path: Path, hotkeys: FakeHotkeyManager) -> None:
    model, engine, _ = make_model(tmp_path, hotkeys)
    model.play(0)
    assert engine.played == []


def test_play_unreadable_local_file_toasts(
    tmp_path: Path, hotkeys: FakeHotkeyManager, qtbot: object
) -> None:
    cell = Cell(index=0, source=LocalSource(path=str(tmp_path / "missing.wav")), name="x")
    model, engine, _ = make_model(tmp_path, hotkeys, cells=[cell])
    messages: list[str] = []
    model.toast.connect(messages.append)
    model.play(0)
    assert engine.played == []
    assert messages


def test_apply_voice_states_updates_progress_and_clears_on_end(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    wav = make_wav(tmp_path / "a.wav")
    cell = Cell(index=0, source=LocalSource(path=str(wav)), name="a")
    model, engine, _ = make_model(tmp_path, hotkeys, cells=[cell])
    model.play(0)  # FakeEngine devuelve voice_id 1
    model.apply_voice_states([(1, 0.4)])
    assert model.data(model.index(0), GridModel.PROGRESS_ROLE) == pytest.approx(0.4)
    model.apply_voice_states([])
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_IDLE
    assert model.data(model.index(0), GridModel.PROGRESS_ROLE) == 0.0
```

Para el caso remoto, replicar el patrón de `test_main_window.py` para descargas (fake client con sonido subido + `qtbot.waitSignal` sobre el worker o inyección síncrona). Mínimo un test: celda remota pasa a LOADING y, al resolver, llama `engine.play` y queda PLAYING; y otro: fallo de descarga → IDLE + toast.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_grid_model.py -v`
Expected: FAIL — `NotImplementedError` / atributos faltantes

- [ ] **Step 3: Implement**

Reemplazar el stub de `play` y añadir:

```python
    def play(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        if isinstance(cell.source, LocalSource):
            try:
                pcm = load_mono_48k(cell.source.path)
            except Exception as exc:
                self.toast.emit(f"No se pudo reproducir: {exc}")
                return
            self._track_voice(index, self._engine.play(pcm))
            return
        self._play_remote(index, cell.source)

    def _track_voice(self, index: int, voice_id: int) -> None:
        self._voice_by_cell[index] = voice_id
        self._states[index] = STATE_PLAYING
        self._progress[index] = 0.0
        self._emit_row_changed(index, [self.STATE_ROLE, self.PROGRESS_ROLE])

    def _play_remote(self, index: int, source: RemoteSource) -> None:
        self._states[index] = STATE_LOADING
        self._emit_row_changed(index, [self.STATE_ROLE])

        def resolve() -> np.ndarray:
            sound = sounds.get_sound(self._client, source.id)
            return sounds.resolve_pcm(self._client, self._cache, sound)

        worker = DownloadWorker(resolve)
        # QThreadPool does not keep the Python refcount alive across the thread
        # hop; without this set the worker can be collected before run() ends.
        self._active_workers.add(worker)
        worker.signals.finished.connect(
            lambda pcm, i=index, w=worker: self._on_pcm_ready(i, w, pcm)
        )
        worker.signals.failed.connect(
            lambda message, i=index, w=worker: self._on_pcm_failed(i, w, message)
        )
        QThreadPool.globalInstance().start(worker)

    def _on_pcm_ready(self, index: int, worker: QObject, pcm: np.ndarray) -> None:
        self._active_workers.discard(worker)
        self._track_voice(index, self._engine.play(pcm))

    def _on_pcm_failed(self, index: int, worker: QObject, message: str) -> None:
        self._active_workers.discard(worker)
        self._states[index] = STATE_IDLE
        self._emit_row_changed(index, [self.STATE_ROLE])
        self.toast.emit(f"error: {message}")

    def apply_voice_states(self, states: list[tuple[int, float]]) -> None:
        """Called by EngineBridge with the engine's (voice_id, progress) snapshot."""
        progress_by_id = dict(states)
        for cell_index, voice_id in list(self._voice_by_cell.items()):
            if voice_id in progress_by_id:
                self._progress[cell_index] = progress_by_id[voice_id]
                self._emit_row_changed(cell_index, [self.PROGRESS_ROLE])
            else:
                del self._voice_by_cell[cell_index]
                self._states[cell_index] = STATE_IDLE
                self._progress[cell_index] = 0.0
                self._emit_row_changed(cell_index, [self.STATE_ROLE, self.PROGRESS_ROLE])
```

Imports nuevos: `QThreadPool` (QtCore), `from soundboard.audioio import load_mono_48k`, `from soundboard.remote import sounds`, `from soundboard.ui.download_worker import DownloadWorker`, `LocalSource`/`RemoteSource` de layout_store. Decorar `play` con `@Slot(int)` (import `Slot`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_grid_model.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/grid_model.py tests/unit/test_grid_model.py
git commit -m "feat(ui): play cells and track voice progress in GridModel"
```

---

### Task 7: `GridModel` — asignar, vaciar, atajo, color

**Files:**
- Modify: `src/soundboard/ui/grid_model.py`
- Test: `tests/unit/test_grid_model.py`

**Interfaces:**
- Consumes: `UploadWorker` (existente), `sounds.add_sound`.
- Produces: slots `assign_local(index: int, path: str)` (acepta ruta o URL `file:`), `assign_remote(index: int, sound_id: str, name: str)`, `clear_cell(index: int)`, `set_shortcut(index: int, combo: str)` (`""` quita el atajo), `set_color(index: int, color: str)` (`""` quita el color).

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_grid_model.py` (para `assign_local`, replicar el patrón de subida de `test_main_window.py` con `qtbot.waitSignal`):

```python
def test_assign_remote_sets_cell_and_saves(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    model, _, layout = make_model(tmp_path, hotkeys)
    model.assign_remote(2, "sound-id-1", "applause")
    assert model.data(model.index(2), GridModel.NAME_ROLE) == "applause"
    assert (tmp_path / "layout.json").exists()
    assert any(c.index == 2 for c in layout.cells)


def test_assign_remote_refuses_occupied_cell(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, _ = make_model(tmp_path, hotkeys, cells=[cell])
    model.assign_remote(0, "sound-id-1", "applause")
    assert model.data(model.index(0), GridModel.NAME_ROLE) == "a"


def test_clear_cell_unregisters_shortcut_and_empties(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a", shortcut="<ctrl>+1")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    model.clear_cell(0)
    assert model.data(model.index(0), GridModel.STATE_ROLE) == STATE_EMPTY
    assert layout.cells == []
    with pytest.raises(KeyError):
        hotkeys.trigger("<ctrl>+1")


def test_set_shortcut_registers_and_persists(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    model.set_shortcut(0, "<ctrl>+2")
    assert layout.cells[0].shortcut == "<ctrl>+2"
    hotkeys.trigger("<ctrl>+2")  # no lanza


def test_set_shortcut_invalid_combo_toasts_and_keeps_cell(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    messages: list[str] = []
    model.toast.connect(messages.append)
    model.set_shortcut(0, "not-a-combo")
    assert messages
    assert layout.cells[0].shortcut is None


def test_set_color_persists_and_clears(
    tmp_path: Path, hotkeys: FakeHotkeyManager
) -> None:
    cell = Cell(index=0, source=LocalSource(path="a.wav"), name="a")
    model, _, layout = make_model(tmp_path, hotkeys, cells=[cell])
    model.set_color(0, "#e8590c")
    assert model.data(model.index(0), GridModel.COLOR_ROLE) == "#e8590c"
    model.set_color(0, "")
    assert layout.cells[0].color is None
```

Más los de `assign_local`: archivo válido → LOADING → (worker sube) → celda remota IDLE con nombre; archivo inválido → toast y sigue vacía; celda ocupada → no-op.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_grid_model.py -v`
Expected: FAIL — atributos faltantes

- [ ] **Step 3: Implement**

Añadir a `GridModel` (todos `@Slot` con las firmas de Interfaces):

```python
    @Slot(int, str)
    def assign_local(self, index: int, path: str) -> None:
        if path.startswith("file:"):
            path = QUrl(path).toLocalFile()
        if self._cell_at(index) is not None:
            return
        try:
            load_mono_48k(path)
        except Exception as exc:
            self.toast.emit(f"No se pudo asignar: {exc}")
            return
        name = Path(path).stem
        self._states[index] = STATE_LOADING
        self._emit_row_changed(index, [self.STATE_ROLE])

        def upload() -> Sound:
            return sounds.add_sound(self._client, self._session, path, name=name)

        worker = UploadWorker(upload)
        self._active_workers.add(worker)
        worker.signals.finished.connect(
            lambda sound, i=index, w=worker: self._on_upload_ready(i, w, sound)
        )
        worker.signals.failed.connect(
            lambda message, i=index, w=worker: self._on_upload_failed(i, w, message)
        )
        QThreadPool.globalInstance().start(worker)

    def _on_upload_ready(self, index: int, worker: QObject, sound: Sound) -> None:
        self._active_workers.discard(worker)
        self._set_cell(
            Cell(index=index, source=RemoteSource(id=sound.id), name=sound.name)
        )

    def _on_upload_failed(self, index: int, worker: QObject, message: str) -> None:
        self._active_workers.discard(worker)
        self._states.pop(index, None)
        self._emit_row_changed(index, [self.STATE_ROLE])
        self.toast.emit(f"No se pudo subir el sonido: {message}")

    @Slot(int, str, str)
    def assign_remote(self, index: int, sound_id: str, name: str) -> None:
        if self._cell_at(index) is not None:
            return
        self._set_cell(Cell(index=index, source=RemoteSource(id=sound_id), name=name))

    @Slot(int)
    def clear_cell(self, index: int) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        if cell.shortcut:
            self._hotkeys.unregister(cell.shortcut)
        self._layout.cells = [c for c in self._layout.cells if c.index != index]
        self._states.pop(index, None)
        self._progress.pop(index, None)
        self._voice_by_cell.pop(index, None)
        save_layout(self._layout_path, self._layout)
        self._emit_row_changed(index, [])

    @Slot(int, str)
    def set_shortcut(self, index: int, combo: str) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        if combo:
            try:
                self._hotkeys.register(combo, partial(self._hotkey_pressed.emit, index))
            except ValueError as exc:
                self.toast.emit(f"Atajo inválido: {exc}")
                return
        if cell.shortcut:
            self._hotkeys.unregister(cell.shortcut)
        self._set_cell(Cell(index=cell.index, source=cell.source, name=cell.name,
                            shortcut=combo or None, color=cell.color))

    @Slot(int, str)
    def set_color(self, index: int, color: str) -> None:
        cell = self._cell_at(index)
        if cell is None:
            return
        self._set_cell(Cell(index=cell.index, source=cell.source, name=cell.name,
                            shortcut=cell.shortcut, color=color or None))

    def _set_cell(self, cell: Cell) -> None:
        self._layout.cells = [c for c in self._layout.cells if c.index != cell.index] + [cell]
        self._states[cell.index] = STATE_IDLE
        save_layout(self._layout_path, self._layout)
        self._emit_row_changed(cell.index, [])
```

Imports nuevos: `QUrl`, `UploadWorker`, `Sound`, `save_layout`. Ojo: `set_shortcut` con combo nuevo sobre celda que ya tenía uno registra el nuevo antes de quitar el viejo (mismo orden que el código actual — si el nuevo es inválido, el viejo sobrevive).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_grid_model.py -v && uv run ruff check . && uv run mypy`
Expected: PASS. Si `grid_model.py` supera ~300 líneas, extraer los workers de subida/descarga a un helper privado — pero primero medir; debería quedar ~280.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/grid_model.py tests/unit/test_grid_model.py
git commit -m "feat(ui): cell assignment, shortcuts and colors in GridModel"
```

---

### Task 8: `EngineBridge` — pico, métricas y estados de voz a ~30 Hz

**Files:**
- Create: `src/soundboard/ui/engine_bridge.py`
- Test: `tests/unit/test_engine_bridge.py`

**Interfaces:**
- Consumes: `engine.last_peak`, `engine.voice_states()`, `engine.metrics` (Task 3).
- Produces: `EngineBridge(engine, parent=None, interval_ms=33)` con propiedades QML `peak: float` (notify `peakChanged`) y `metricsText: str` (notify `metricsChanged`); señal `voice_states_updated = Signal(object)` (lista de `(voice_id, progress)`); métodos `start()`, `stop()`, slot `poll()` (un tick, invocable directo en tests).

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_engine_bridge.py`:

```python
"""EngineBridge polls the engine and republishes UI-friendly state."""

from __future__ import annotations

from soundboard.audio.engine import EngineMetrics
from soundboard.ui.engine_bridge import EngineBridge


class FakeEngine:
    def __init__(self) -> None:
        self.last_peak = 0.0
        self.states: list[tuple[int, float]] = []

    def voice_states(self) -> list[tuple[int, float]]:
        return self.states

    @property
    def metrics(self) -> EngineMetrics:
        return EngineMetrics(underruns=1, overruns=0, fill=512, ratio=1.0,
                             active_voices=len(self.states))


def test_poll_publishes_peak_and_metrics(qtbot: object) -> None:
    engine = FakeEngine()
    bridge = EngineBridge(engine)
    engine.last_peak = 0.5
    engine.states = [(1, 0.25)]
    received: list[object] = []
    bridge.voice_states_updated.connect(received.append)
    bridge.poll()
    assert bridge.peak == 0.5
    assert "underruns 1" in bridge.metricsText
    assert received == [[(1, 0.25)]]


def test_peak_changed_only_fires_on_change(qtbot: object) -> None:
    engine = FakeEngine()
    bridge = EngineBridge(engine)
    fired: list[bool] = []
    bridge.peakChanged.connect(lambda: fired.append(True))
    bridge.poll()
    bridge.poll()
    assert fired == []  # 0.0 → 0.0: sin cambio, sin señal
    engine.last_peak = 0.3
    bridge.poll()
    assert len(fired) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_engine_bridge.py -v`
Expected: FAIL — módulo inexistente

- [ ] **Step 3: Implement**

Crear `src/soundboard/ui/engine_bridge.py`:

```python
"""Polls the audio engine and republishes peak/metrics/voice progress for the UI."""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from soundboard.audio.engine import EngineMetrics


class MeteredEngine(Protocol):
    @property
    def last_peak(self) -> float: ...
    @property
    def metrics(self) -> EngineMetrics: ...
    def voice_states(self) -> list[tuple[int, float]]: ...


class EngineBridge(QObject):
    peakChanged = Signal()
    metricsChanged = Signal()
    voice_states_updated = Signal(object)

    def __init__(
        self, engine: MeteredEngine, parent: QObject | None = None, interval_ms: int = 33
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._peak = 0.0
        self._metrics_text = ""
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @Slot()
    def poll(self) -> None:
        peak = float(self._engine.last_peak)
        if peak != self._peak:
            self._peak = peak
            self.peakChanged.emit()
        self.voice_states_updated.emit(self._engine.voice_states())
        m = self._engine.metrics
        text = f"underruns {m.underruns} · fill {m.fill} · voces {m.active_voices}"
        if text != self._metrics_text:
            self._metrics_text = text
            self.metricsChanged.emit()

    def _get_peak(self) -> float:
        return self._peak

    def _get_metrics_text(self) -> str:
        return self._metrics_text

    peak = Property(float, _get_peak, notify=peakChanged)
    metricsText = Property(str, _get_metrics_text, notify=metricsChanged)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_engine_bridge.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/engine_bridge.py tests/unit/test_engine_bridge.py
git commit -m "feat(ui): add EngineBridge polling peak, metrics and voice states"
```

---

### Task 9: `LibraryModel` — biblioteca remota con filtro

**Files:**
- Create: `src/soundboard/ui/library_model.py`
- Test: `tests/unit/test_library_model.py`

**Interfaces:**
- Consumes: `sounds.list_sounds`, `auth.display_names`, `DownloadWorker` (payload genérico `object`).
- Produces: `LibraryModel(client, parent=None)` — `QAbstractListModel` con roles `NAME_ROLE`→`b"name"`, `OWNER_ROLE`→`b"owner"`, `SOUND_ID_ROLE`→`b"soundId"`; propiedades QML `loading: bool` (notify `loadingChanged`), `errorText: str` (notify `errorChanged`), `filterText: str` lectura/escritura (notify `filterChanged`; el setter re-filtra); slot `reload()`.

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_library_model.py`. Preparar el fake: revisar cómo `tests/unit/test_library_dialog.py` siembra sonidos en `FakeRemoteClient` (vía `sounds.add_sound` con una sesión fake) y reutilizar ese patrón exacto. Tests:

```python
def test_reload_populates_rows(qtbot, seeded_client) -> None:
    model = LibraryModel(seeded_client)
    with qtbot.waitSignal(model.loadingChanged, timeout=2000):
        model.reload()
    qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    assert model.rowCount() > 0
    first = model.index(0)
    assert model.data(first, LibraryModel.NAME_ROLE)
    assert model.data(first, LibraryModel.SOUND_ID_ROLE)


def test_filter_narrows_by_name_case_insensitive(qtbot, seeded_client) -> None:
    # seeded con "airhorn" y "applause"
    model = LibraryModel(seeded_client)
    model.reload(); qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    model.filterText = "AIR"
    assert model.rowCount() == 1
    model.filterText = ""
    assert model.rowCount() == 2


def test_reload_failure_sets_error(qtbot) -> None:
    class ExplodingClient:
        def select(self, *a: object, **k: object) -> object:
            raise RuntimeError("boom")
    model = LibraryModel(ExplodingClient())
    model.reload()
    qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    assert "boom" in model.errorText
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_library_model.py -v`
Expected: FAIL — módulo inexistente

- [ ] **Step 3: Implement**

Crear `src/soundboard/ui/library_model.py`: guarda `self._all: list[tuple[str, str, str]]` (`(sound_id, name, owner_display)`) y `self._rows` (filtrada). `reload()`: pone `loading=True` (+señal), limpia `errorText`, lanza `DownloadWorker` con:

```python
        def fetch() -> list[tuple[str, str, str]]:
            available = sounds.list_sounds(self._client)
            owners = auth.display_names(self._client, {s.owner_id for s in available})
            return [(s.id, s.name, owners.get(s.owner_id, s.owner_id))
                    for s in available]
```

`finished` → `self._all = rows`, `_apply_filter()`, `loading=False`; `failed` → `errorText=message`, `loading=False`. `_apply_filter()` hace `beginResetModel()` / filtra por `self._filter.lower() in name.lower()` / `endResetModel()`. Mantener el set `self._active_workers` (mismo motivo de refcount que GridModel). El worker devuelve `object` — `DownloadWorker` ya emite `finished(object)`, sirve para cualquier payload, no solo PCM; actualizar su docstring de módulo para reflejarlo («Runs a callable off the Qt thread; finished carries its return value»).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_library_model.py -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/library_model.py tests/unit/test_library_model.py src/soundboard/ui/download_worker.py
git commit -m "feat(ui): add LibraryModel with name filter over the remote library"
```

---

### Task 10: `AppController` — sesión, ciclo de vida del engine, navegación

**Files:**
- Create: `src/soundboard/ui/controller.py`
- Test: `tests/unit/test_controller.py`

**Interfaces:**
- Consumes: `auth.require_session/log_in/sign_up`, `SessionStore`, `find_device`/`AudioEngine`/`EngineConfig`, `GridModel` (Tasks 5-7), `EngineBridge` (Task 8), `LibraryModel` (Task 9), `load_layout`/`save_layout`.
- Produces — `AppController(*, client, store, backend, hotkeys, cache, layout_path, engine_factory=None, parent=None)`:
  - Propiedades QML: `view: str` («login»/«setup»/«board», notify `viewChanged`), `userEmail: str` (notify `sessionChanged`), `loginError: str` (notify `loginErrorChanged`), `setupError: str` (notify `setupErrorChanged`), `micName/outName: str` y `gridRows/gridCols: int` y `inputDevices/outputDevices: "QVariantList"` (todas notify `devicesChanged`), `gridModel: QObject` (nullable, notify `gridModelChanged`), `bridge: QObject` (nullable, notify `bridgeChanged`), `libraryModel: QObject` (constant).
  - Señal `toast = Signal(str)` (re-emite la de GridModel).
  - Slots: `log_in(email, password)`, `sign_up(email, password)`, `apply_devices(mic, out, rows, cols)`, `open_settings()`, `cancel_settings()`, `stop_all()`.
  - Métodos Python: `bootstrap()` (decide vista inicial), `shutdown()` (teardown de bridge/engine/hotkeys).
  - `engine_factory: Callable[[GridLayout], Engine]` inyectable; el default resuelve dispositivos con `find_device` y hace `engine.start()` (lógica movida desde `app.py::_start_engine_with_retry`, pero sin loop de diálogo: un intento; el fallo se publica en `setupError` y la vista queda en «setup»).

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_controller.py`:

```python
"""AppController: session bootstrap, engine lifecycle, view navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    tmp_path: Path, *, engine_factory=None, store: FakeStore | None = None
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


def test_bootstrap_without_session_lands_on_login(tmp_path: Path, qtbot) -> None:
    controller, _, _ = make_controller(tmp_path)
    controller.bootstrap()
    assert controller.view == "login"


def test_login_without_layout_lands_on_setup(tmp_path: Path, qtbot) -> None:
    controller, _, _ = make_controller(tmp_path)
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    assert controller.view == "setup"
    assert controller.userEmail == "user@example.com"


def test_bad_login_sets_login_error(tmp_path: Path, qtbot) -> None:
    controller, _, _ = make_controller(tmp_path)
    controller.bootstrap()
    controller.log_in("nobody@example.com", "wrong")
    assert controller.view == "login"
    assert controller.loginError != ""


def test_apply_devices_starts_engine_and_lands_on_board(tmp_path: Path, qtbot) -> None:
    controller, _, _ = make_controller(tmp_path)
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    assert controller.view == "board"
    assert controller.gridModel is not None
    assert controller.bridge is not None
    assert (tmp_path / "layout.json").exists()


def test_engine_failure_shows_setup_error(tmp_path: Path, qtbot) -> None:
    def exploding_factory(layout):  # type: ignore[no-untyped-def]
        raise RuntimeError("no such device")
    controller, _, _ = make_controller(tmp_path, engine_factory=exploding_factory)
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    assert controller.view == "setup"
    assert "no such device" in controller.setupError


def test_saved_session_and_layout_boot_straight_to_board(tmp_path: Path, qtbot) -> None:
    controller, client, store = make_controller(tmp_path)
    save_layout(tmp_path / "layout.json",
                GridLayout(rows=2, cols=2, mic="m", out="o", blocksize=256))
    store.save(client.sign_in_as_new_user("user@example.com"))
    controller.bootstrap()
    assert controller.view == "board"


def test_settings_round_trip_and_stop_all(tmp_path: Path, qtbot) -> None:
    engines: list[FakeEngine] = []
    def factory(layout):  # type: ignore[no-untyped-def]
        engines.append(FakeEngine())
        return engines[-1]
    controller, _, _ = make_controller(tmp_path, engine_factory=factory)
    controller.bootstrap()
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    controller.open_settings()
    assert controller.view == "setup"
    controller.cancel_settings()
    assert controller.view == "board"
    controller.apply_devices("mic2", "out2", 3, 3)
    assert engines[0].stopped  # el engine anterior se apagó
    assert controller.view == "board"
    controller.stop_all()
    assert engines[-1].stop_all_called
```

**Nota:** `FakeRemoteClient.sign_in` — comprobar en `src/soundboard/remote/fake_client.py` qué credenciales acepta (`sign_in_as_new_user` primero, o si `sign_in` de un email desconocido lanza — mirar cómo lo usan `tests/unit/test_auth.py`). Ajustar los tests de login para crear el usuario antes si hace falta.

`bootstrap` con sesión que falla al restaurar: cubierto por paridad con `app.py` actual — añadir un test si `FakeRemoteClient` permite simular `require_session` fallando; si no, dejarlo documentado en el test module docstring como cubierto por el código heredado.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_controller.py -v`
Expected: FAIL — módulo inexistente

- [ ] **Step 3: Implement**

Crear `src/soundboard/ui/controller.py`. Esqueleto de la lógica central (las propiedades siguen el patrón `_get_x` + `Property(..., notify=...)` de EngineBridge):

```python
    def bootstrap(self) -> None:
        if self._store.load() is not None:
            try:
                self._session = auth.require_session(self._client, self._store)
            except Exception:
                # Supabase rota el refresh token; un token ya consumido debe
                # tratarse como "sin sesión", no como crash (mismo motivo que
                # documentaba app.py).
                self._store.clear()
        if self._session is None:
            self._set_view("login")
            return
        self._after_login()

    def _after_login(self) -> None:
        self.sessionChanged.emit()
        self._layout = load_layout(self._layout_path)
        self.devicesChanged.emit()
        if self._layout is None:
            self._set_view("setup")
            return
        self._start_engine()

    @Slot(str, str)
    def log_in(self, email: str, password: str) -> None:
        try:
            self._session = auth.log_in(self._client, self._store, email, password,
                                        lambda: email.split("@")[0])
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
            self._layout = GridLayout(rows=rows, cols=cols, mic=mic, out=out,
                                      blocksize=256)
        else:
            self._layout.mic, self._layout.out = mic, out
            self._layout.rows, self._layout.cols = rows, cols
        save_layout(self._layout_path, self._layout)
        self.devicesChanged.emit()
        self._teardown_engine()
        self._start_engine()

    def _start_engine(self) -> None:
        assert self._layout is not None and self._session is not None
        try:
            self._engine = self._engine_factory(self._layout)
        except Exception as exc:
            self._setup_error = str(exc)
            self.setupErrorChanged.emit()
            self._set_view("setup")
            return
        self._setup_error = ""
        self.setupErrorChanged.emit()
        self._grid = GridModel(self._engine, self._client, self._session, self._cache,
                               self._hotkeys, self._layout, self._layout_path,
                               parent=self)
        self._grid.toast.connect(self.toast)
        self._bridge = EngineBridge(self._engine, parent=self)
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
        self._hotkeys.stop()  # GridModel nuevo re-registra los atajos de sus celdas
        if self._engine is not None:
            self._engine.stop()
            self._engine = None

    def shutdown(self) -> None:
        self._teardown_engine()

    def _build_engine(self, layout: GridLayout) -> AudioEngine:
        devices = self._backend.list_devices()
        microphone = find_device(devices, layout.mic, want_input=True)
        cable = find_device(devices, layout.out, want_input=False)
        engine = AudioEngine(self._backend, EngineConfig(
            blocksize=layout.blocksize, input_device=microphone.index,
            output_device=cable.index,
            output_channels=min(2, cable.max_output_channels) or 1))
        engine.start()
        return engine
```

`inputDevices`/`outputDevices` (getters): `[d.name for d in self._backend.list_devices() if d.max_input_channels > 0]` (resp. output). `micName`/`outName`/`gridRows`/`gridCols` leen `self._layout` con defaults (`""`, 4, 6). `open_settings` → `_set_view("setup")`; `cancel_settings` → si `self._engine is not None`, `_set_view("board")`; `stop_all` → `self._engine.stop_all()` si existe. `libraryModel` se crea en `__init__` con `parent=self` y se expone `Property(QObject, _get_library, constant=True)`. `gridModel`/`bridge` son `Property(QObject, ..., notify=...)` que devuelven el objeto o `None` (QML lo ve como `null`).

Si el archivo supera ~300 líneas, mover `_build_engine` + `FakeStore`-style protocolo de store a un `ui/engine_factory.py` — medir primero.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_controller.py tests/unit/ -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/controller.py tests/unit/test_controller.py
git commit -m "feat(ui): add AppController owning session, engine and navigation"
```

---

### Task 11: QML — Theme y componentes

**Files:**
- Create: `src/soundboard/ui/qml/qmldir`, `src/soundboard/ui/qml/Theme.qml`
- Create: `src/soundboard/ui/qml/components/ClipPad.qml`, `HeaderBar.qml`, `VUMeter.qml`, `Toast.qml`
- Test: `tests/unit/test_qml_components.py`

**Interfaces:**
- Produces: singleton `Theme` (import desde `components/` como `import ".."`); componentes instanciables sin contexto (sin `required property`, sin referencias a `App`).
  - `ClipPad`: properties `name: string`, `shortcut: string`, `cellColor: string`, `cellState: string` («empty»/«idle»/«loading»/«playing»), `progress: real`; signals `clicked()`, `rightClicked()`, `fileDropped(string url)`.
  - `HeaderBar`: properties `userEmail`, `micName`, `outName` (string); signals `settingsClicked()`, `stopAllClicked()`.
  - `VUMeter`: property `level: real` (0..1).
  - `Toast`: function `show(text)` — se autooculta a los 4 s.

- [ ] **Step 1: Write the failing test**

Crear `tests/unit/test_qml_components.py`:

```python
"""Every QML component must instantiate standalone under the offscreen platform."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtQml import QQmlComponent, QQmlEngine

QML_DIR = Path(__file__).parents[2] / "src" / "soundboard" / "ui" / "qml"

COMPONENTS = sorted(p for p in (QML_DIR / "components").glob("*.qml"))


def test_components_exist() -> None:
    names = {p.name for p in COMPONENTS}
    assert {"ClipPad.qml", "HeaderBar.qml", "VUMeter.qml", "Toast.qml"} <= names


@pytest.mark.parametrize("qml_file", COMPONENTS, ids=lambda p: p.name)
def test_component_instantiates(qapp: object, qml_file: Path) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine, str(qml_file))
    obj = component.create()
    errors = [e.toString() for e in component.errors()]
    assert obj is not None, errors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_qml_components.py -v`
Expected: FAIL — directorio/archivos inexistentes

- [ ] **Step 3: Implement**

`qml/qmldir`:

```
singleton Theme 1.0 Theme.qml
```

`qml/Theme.qml`:

```qml
pragma Singleton
import QtQuick

QtObject {
    readonly property color windowBg: "#141518"
    readonly property color surface: "#1d1f24"
    readonly property color padBg: "#22252b"
    readonly property color accent: "#7c5cff"
    readonly property color textPrimary: "#e8eaed"
    readonly property color textSecondary: "#9aa0a6"
    readonly property color danger: "#e5484d"
    readonly property color meterGreen: "#3dd68c"
    readonly property color meterAmber: "#f5a524"
    readonly property color meterRed: "#e5484d"
    readonly property int radiusPad: 8
    readonly property int radiusControl: 6
    readonly property int pad: 8
}
```

`components/ClipPad.qml` (los demás componentes siguen el mismo estilo — `import QtQuick`, `import QtQuick.Controls`, `import ".."` para `Theme`):

```qml
import QtQuick
import QtQuick.Controls
import ".."

Rectangle {
    id: root
    property string name: ""
    property string shortcut: ""
    property string cellColor: ""
    property string cellState: "empty"
    property real progress: 0.0
    signal clicked()
    signal rightClicked()
    signal fileDropped(string url)

    radius: Theme.radiusPad
    color: cellState === "empty" ? Theme.padBg
         : cellColor !== "" ? Qt.darker(cellColor, 2.8) : Theme.surface
    border.width: 2
    border.color: cellState === "playing" ? Theme.accent : "transparent"
    Behavior on border.color { ColorAnimation { duration: 150 } }

    Rectangle {
        visible: root.cellColor !== ""
        color: root.cellColor
        height: 4
        radius: 2
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 6 }
    }

    Column {
        anchors.centerIn: parent
        spacing: 4
        width: parent.width - 16
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.name
            color: Theme.textPrimary
            elide: Text.ElideRight
            font.pixelSize: 13
            font.bold: true
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            visible: root.shortcut !== ""
            text: root.shortcut
            color: Theme.textSecondary
            elide: Text.ElideMiddle
            font.pixelSize: 10
        }
    }

    BusyIndicator {
        visible: root.cellState === "loading"
        running: visible
        anchors.centerIn: parent
        width: 28; height: 28
    }

    Rectangle {
        visible: root.cellState === "playing"
        anchors { bottom: parent.bottom; left: parent.left; margins: 6 }
        width: (parent.width - 12) * Math.min(1, root.progress)
        height: 3
        radius: 1.5
        color: Theme.accent
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: (mouse) => {
            if (mouse.button === Qt.RightButton)
                root.rightClicked()
            else
                root.clicked()
        }
    }

    DropArea {
        anchors.fill: parent
        enabled: root.cellState === "empty"
        onDropped: (drop) => {
            if (drop.hasUrls)
                root.fileDropped(drop.urls[0])
        }
    }
}
```

`components/VUMeter.qml`: `Item` con `property real level`, fondo `Rectangle` redondeado `Theme.padBg`, e `Item { clip: true; width: parent.width * Math.min(1, level) }` conteniendo un `Rectangle` de ancho completo con `gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: Theme.meterGreen } GradientStop { position: 0.75; color: Theme.meterAmber } GradientStop { position: 1; color: Theme.meterRed } }`.

`components/Toast.qml`: `Rectangle` con `radius: Theme.radiusControl`, `color: Theme.surface`, `border.color: Theme.accent`, `opacity: 0`, `Text` interior, `function show(text) { label.text = text; opacity = 1; hideTimer.restart() }`, `Timer { id: hideTimer; interval: 4000; onTriggered: parent.opacity = 0 }`, `Behavior on opacity { NumberAnimation { duration: 200 } }`.

`components/HeaderBar.qml`: `Rectangle` altura 48, `color: Theme.surface`; `RowLayout` con `Text "Soundboard"` (bold, `Theme.textPrimary`), spacer, `Text userEmail` + `Text micName + " → " + outName` (`Theme.textSecondary`, pixelSize 11), `Button "Ajustes"` → `settingsClicked()`, `Button "Detener todo"` → `stopAllClicked()` (fondo `Theme.danger`, texto blanco, vía `background: Rectangle {...}`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_qml_components.py -v && uv run ruff check . && uv run mypy`
Expected: PASS (si `BusyIndicator`/`Button` fallan por falta de estilo QtQuick Controls en offscreen, el mensaje de error del test lo dirá — en ese caso añadir `import QtQuick.Controls.Basic` en lugar de `QtQuick.Controls` en los componentes que los usan)

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/qml tests/unit/test_qml_components.py
git commit -m "feat(ui): add QML theme singleton and board components"
```

---

### Task 12: QML — vistas, popups y `Main.qml`

**Files:**
- Create: `src/soundboard/ui/qml/Main.qml`, `LoginView.qml`, `DeviceSetupView.qml`, `BoardView.qml`
- Create: `src/soundboard/ui/qml/components/LibraryPopup.qml`, `ShortcutPopup.qml`, `ColorPopup.qml`
- Test: `tests/unit/test_qml_components.py` (los popups entran solos a la parametrización por el glob)

**Interfaces:**
- Consumes: contexto global `App` (AppController, Task 10) — **solo** en las vistas y `Main.qml`, nunca en `components/` (los popups reciben todo por properties/signals).
- Produces: `Main.qml` — `ApplicationWindow` cargable por `QQmlApplicationEngine` con `App` como context property (el smoke completo llega en Task 13).
  - `LibraryPopup`: properties `model` (LibraryModel), `cellIndex: int`; signal `picked(int cellIndex, string soundId, string name)`.
  - `ShortcutPopup`: properties `cellIndex: int`, `currentShortcut: string`; signal `accepted(int cellIndex, string combo)`.
  - `ColorPopup`: property `cellIndex: int`; signal `picked(int cellIndex, string color)`; presets `["#e5484d", "#f5a524", "#3dd68c", "#29a383", "#0091ff", "#7c5cff", "#d6409f", "#f76b15"]` + botón «Sin color» (emite `""`).

- [ ] **Step 1: Write the failing test**

Ampliar `test_components_exist` en `tests/unit/test_qml_components.py`:

```python
    assert {"ClipPad.qml", "HeaderBar.qml", "VUMeter.qml", "Toast.qml",
            "LibraryPopup.qml", "ShortcutPopup.qml", "ColorPopup.qml"} <= names


def test_views_exist() -> None:
    names = {p.name for p in QML_DIR.glob("*.qml")}
    assert {"Main.qml", "LoginView.qml", "DeviceSetupView.qml",
            "BoardView.qml", "Theme.qml"} <= names
```

(Las vistas usan `App` y no se instancian standalone — su carga real se verifica en el smoke de Task 13.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_qml_components.py -v`
Expected: FAIL — archivos inexistentes

- [ ] **Step 3: Implement**

`Main.qml`:

```qml
import QtQuick
import QtQuick.Controls
import "."
import "components"

ApplicationWindow {
    id: root
    visible: true
    width: 960
    height: 640
    minimumWidth: 640
    minimumHeight: 420
    title: "Soundboard"
    color: Theme.windowBg

    onClosing: (close) => {
        if (App.view === "login") {
            Qt.quit()          // sin sesión no hay nada que conservar en la bandeja
        } else {
            close.accepted = false
            root.hide()        // la bandeja mantiene vivo el motor de audio
        }
    }

    Loader {
        anchors.fill: parent
        source: App.view === "login" ? "LoginView.qml"
              : App.view === "setup" ? "DeviceSetupView.qml"
              : "BoardView.qml"
    }

    Toast {
        id: toast
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom;
                  bottomMargin: 24 }
        width: Math.min(parent.width - 48, 480)
        height: 40
    }

    Connections {
        target: App
        function onToast(message) { toast.show(message) }
    }
}
```

`LoginView.qml`: columna centrada dentro de un `Rectangle` tipo tarjeta (`Theme.surface`, radius, ancho 320): `TextField` email (`placeholderText: "Email"`), `TextField` password (`echoMode: TextInput.Password`), `Text { text: App.loginError; color: Theme.danger; visible: text !== ""; wrapMode: Text.Wrap }`, `Button "Ingresar"` → `App.log_in(emailField.text, passwordField.text)`, `Button "Crear cuenta"` → `App.sign_up(emailField.text, passwordField.text)`.

`DeviceSetupView.qml`: tarjeta centrada con `ComboBox` mic (`model: App.inputDevices; currentIndex: App.inputDevices.indexOf(App.micName)`), `ComboBox` salida (ídem con `outputDevices`/`outName`), `SpinBox` filas y columnas (`from: 1; to: 12; value: App.gridRows` / `App.gridCols`), `Text` de error (`App.setupError`, `Theme.danger`), `Button "Aplicar"` → `App.apply_devices(micCombo.currentText, outCombo.currentText, rowsSpin.value, colsSpin.value)`, `Button "Cancelar"` (`visible: App.gridModel !== null`) → `App.cancel_settings()`.

`BoardView.qml`:

```qml
import QtQuick
import QtQuick.Controls
import "."
import "components"

Item {
    HeaderBar {
        id: header
        anchors { top: parent.top; left: parent.left; right: parent.right }
        userEmail: App.userEmail
        micName: App.micName
        outName: App.outName
        onSettingsClicked: App.open_settings()
        onStopAllClicked: App.stop_all()
    }

    GridView {
        id: grid
        anchors { top: header.bottom; left: parent.left; right: parent.right;
                  bottom: footer.top; margins: Theme.pad }
        model: App.gridModel
        interactive: false
        cellWidth: Math.floor(width / App.gridCols)
        cellHeight: Math.floor(height / App.gridRows)
        delegate: Item {
            width: grid.cellWidth
            height: grid.cellHeight
            ClipPad {
                anchors { fill: parent; margins: Theme.pad / 2 }
                name: model.name
                shortcut: model.shortcut
                cellColor: model.cellColor
                cellState: model.cellState
                progress: model.progress
                onClicked: App.gridModel.play(index)
                onRightClicked: contextMenu.openFor(index, model.cellState)
                onFileDropped: (url) => App.gridModel.assign_local(index, url)
            }
        }
    }

    Rectangle {
        id: footer
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: 36
        color: Theme.surface
        Row {
            anchors { fill: parent; margins: Theme.pad }
            spacing: Theme.pad * 2
            VUMeter {
                width: 180; height: parent.height
                level: App.bridge !== null ? App.bridge.peak : 0
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: App.bridge !== null ? App.bridge.metricsText : ""
                color: Theme.textSecondary
                font.pixelSize: 11
            }
        }
    }

    Menu {
        id: contextMenu
        property int cellIndex: -1
        property string cellState: "empty"
        function openFor(index, state) { cellIndex = index; cellState = state; popup() }
        MenuItem {
            text: "Asignar desde biblioteca"
            enabled: contextMenu.cellState === "empty"
            onTriggered: libraryPopup.openFor(contextMenu.cellIndex)
        }
        MenuItem {
            text: "Asignar atajo"
            enabled: contextMenu.cellState !== "empty"
            onTriggered: shortcutPopup.openFor(contextMenu.cellIndex)
        }
        MenuItem {
            text: "Color"
            enabled: contextMenu.cellState !== "empty"
            onTriggered: colorPopup.openFor(contextMenu.cellIndex)
        }
        MenuItem {
            text: "Vaciar celda"
            enabled: contextMenu.cellState !== "empty"
            onTriggered: App.gridModel.clear_cell(contextMenu.cellIndex)
        }
    }

    LibraryPopup {
        id: libraryPopup
        model: App.libraryModel
        onPicked: (cellIndex, soundId, name) =>
            App.gridModel.assign_remote(cellIndex, soundId, name)
    }
    ShortcutPopup {
        id: shortcutPopup
        onAccepted: (cellIndex, combo) => App.gridModel.set_shortcut(cellIndex, combo)
    }
    ColorPopup {
        id: colorPopup
        onPicked: (cellIndex, color) => App.gridModel.set_color(cellIndex, color)
    }
}
```

Los tres popups son `Popup` de QtQuick.Controls centrados (`anchors.centerIn: Overlay.overlay`), fondo `Theme.surface` con radius, y un `function openFor(index)` que fija `cellIndex` + estado inicial y llama `open()`:
- `LibraryPopup`: `TextField` de filtro con `onTextChanged: model.filterText = text`, `ListView` (`model: root.model`) con delegates `name — owner` clicables (fila resaltada `Theme.accent` al hover), `Text` de error (`model.errorText`) + `Button "Reintentar"` → `model.reload()`, `BusyIndicator` (`running: model.loading`), texto vacío «No hay sonidos compartidos todavía» cuando `count === 0 && !model.loading && model.errorText === ""`. `openFor` llama `model.reload()`. Doble click o botón «Asignar» emite `picked(cellIndex, soundId, name)` y cierra. **Nota:** `model` como nombre de property es válido aquí (Popup no es delegate); los roles del delegate interno se leen como `model.name`/`model.owner`/`model.soundId`.
- `ShortcutPopup`: `TextField` (`text: currentShortcut; placeholderText: "<ctrl>+<alt>+1"`), `Text` ayuda («Formato pynput. Vacío = quitar atajo», `Theme.textSecondary`), botones «Guardar» (emite `accepted(cellIndex, field.text)` y cierra) y «Cancelar».
- `ColorPopup`: `Grid` 4×2 de `Rectangle` 32×32 con radius, cada uno un preset, `MouseArea` → `picked(cellIndex, modelData)` + close; debajo `Button "Sin color"` → `picked(cellIndex, "")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_qml_components.py -v && uv run ruff check . && uv run mypy`
Expected: PASS — los popups nuevos entran a la parametrización y deben instanciarse standalone (por eso reciben `model` por property y no tocan `App`)

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/ui/qml tests/unit/test_qml_components.py
git commit -m "feat(ui): add QML views, popups and main window"
```

---

### Task 13: `app.py` — arranque QML + tray + smoke test completo

**Files:**
- Modify: `src/soundboard/ui/app.py` (rewrite)
- Modify: `tests/unit/test_app.py` (rewrite)
- Create: `tests/unit/test_qml_main.py`

**Interfaces:**
- Consumes: `AppController` (Task 10), `Main.qml` (Task 12), `TrayIcon` (existente, sin cambios).
- Produces: `run_gui(argv=None, *, backend=None, client=None, store=None, hotkeys=None, exec_app=True) -> int` (misma firma que hoy); `qml_root() -> Path` (resuelve `qml/` tanto en desarrollo como bajo PyInstaller vía `sys._MEIPASS`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_qml_main.py`:

```python
"""Full Main.qml smoke: loads with a real AppController wired to fakes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtQml import QQmlApplicationEngine

from soundboard.audio.fake_backend import FakeBackend
from soundboard.hotkeys import FakeHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.app import qml_root
from soundboard.ui.controller import AppController
from tests.unit.test_controller import FakeEngine, FakeStore


def _load(controller: AppController) -> tuple[QQmlApplicationEngine, list[str]]:
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(
        lambda ws: warnings.extend(w.toString() for w in ws)
    )
    engine.rootContext().setContextProperty("App", controller)
    engine.load(str(qml_root() / "Main.qml"))
    return engine, warnings


def make_controller(tmp_path: Path) -> AppController:
    return AppController(
        client=FakeRemoteClient(), store=FakeStore(), backend=FakeBackend(),
        hotkeys=FakeHotkeyManager(), cache=SoundCache(tmp_path / "cache"),
        layout_path=tmp_path / "layout.json",
        engine_factory=lambda layout: FakeEngine(),
    )


def test_main_qml_loads_on_login_view(qapp, tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    assert engine.rootObjects(), warnings
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []


def test_main_qml_reaches_board_view(qapp, tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller.bootstrap()
    engine, warnings = _load(controller)
    controller.log_in("user@example.com", "password")
    controller.apply_devices("mic", "out", 2, 3)
    qapp.processEvents()
    assert controller.view == "board"
    qml_warnings = [w for w in warnings if ".qml" in w]
    assert qml_warnings == []
```

(Si `log_in` con usuario inexistente falla en `FakeRemoteClient`, sembrar con `sign_in_as_new_user` + store como en `test_controller.py`.)

`tests/unit/test_app.py` (rewrite — conservar solo lo que siga aplicando del actual; revisar qué fakes/monkeypatches usa hoy y mantener el estilo):

```python
def test_run_gui_smoke_without_exec(qapp, tmp_path, monkeypatch) -> None:
    from soundboard.ui import app as app_module
    monkeypatch.setattr(app_module, "default_layout_path",
                        lambda: tmp_path / "layout.json")
    monkeypatch.setattr(app_module, "_default_cache_dir", lambda: tmp_path / "cache")
    code = app_module.run_gui(
        [], backend=FakeBackend(), client=FakeRemoteClient(), store=FakeStore(),
        hotkeys=FakeHotkeyManager(), exec_app=False,
    )
    assert code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_qml_main.py tests/unit/test_app.py -v`
Expected: FAIL — `qml_root` no existe; `run_gui` sigue construyendo `MainWindow`

- [ ] **Step 3: Implement**

Rewrite de `src/soundboard/ui/app.py`:

```python
"""GUI entry point: builds the AppController, loads Main.qml, wires the tray."""

from __future__ import annotations

import sys
from pathlib import Path

import platformdirs
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMessageBox

from soundboard.audio.backend import AudioBackend
from soundboard.audio.portaudio import PortAudioBackend
from soundboard.hotkeys import HotkeyManager, PynputHotkeyManager
from soundboard.library.cache import SoundCache
from soundboard.remote.client import SessionStore, build_client
from soundboard.remote.models import RemoteClient
from soundboard.ui.controller import AppController
from soundboard.ui.layout_store import default_layout_path
from soundboard.ui.tray import TrayIcon


def _default_cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("soundboard")) / "pcm"


def qml_root() -> Path:
    """Locate qml/ both in a checkout and inside a PyInstaller bundle."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        return Path(bundled) / "soundboard" / "ui" / "qml"
    return Path(__file__).parent / "qml"


def run_gui(
    argv: list[str] | None = None,
    *,
    backend: AudioBackend | None = None,
    client: RemoteClient | None = None,
    store: SessionStore | None = None,
    hotkeys: HotkeyManager | None = None,
    exec_app: bool = True,
) -> int:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)

    if client is None:
        try:
            client = build_client()
        except Exception as exc:
            # Double-clicked by a non-technical user: a corrupt settings.json
            # must be a dialog, not a traceback (or silence under a file manager).
            QMessageBox.critical(None, "Configuración inválida", str(exc))
            return 1

    controller = AppController(
        client=client,
        store=store if store is not None else SessionStore(),
        backend=backend if backend is not None else PortAudioBackend(),
        hotkeys=hotkeys if hotkeys is not None else PynputHotkeyManager(),
        cache=SoundCache(_default_cache_dir()),
        layout_path=default_layout_path(),
    )
    controller.bootstrap()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("App", controller)
    engine.load(str(qml_root() / "Main.qml"))
    if not engine.rootObjects():
        QMessageBox.critical(None, "Error de interfaz", "No se pudo cargar la interfaz")
        return 1
    window = engine.rootObjects()[0]

    def quit_app() -> None:
        app.quit()

    tray = TrayIcon(on_show=window.show, on_quit=quit_app)
    tray.show()
    app.aboutToQuit.connect(controller.shutdown)

    if not exec_app:
        controller.shutdown()
        return 0
    return app.exec()
```

(La variable `tray` debe mantenerse referenciada hasta el final de `run_gui` — no borrarla «porque no se usa»; sin la referencia el ícono se recolecta.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_qml_main.py tests/unit/test_app.py -v && uv run ruff check . && uv run mypy`
Expected: PASS (la suite completa aún no — `test_main_window.py` y compañía siguen apuntando a los módulos viejos; caen en la Task 14)

- [ ] **Step 5: Manual verification (primera vez que la app entera es visible)**

Run: `uv run soundboard gui`
Checklist: login (o sesión guardada) → board se ve con tema oscuro; click reproduce; celda se ilumina con progreso; VU se mueve con el mic; drop de un WAV asigna; menú contextual completo; ajustes cambia dispositivos sin reiniciar; cerrar ventana minimiza a bandeja; «Salir» de la bandeja termina el proceso.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/ui/app.py tests/unit/test_app.py tests/unit/test_qml_main.py
git commit -m "feat(ui): boot the QML window from AppController"
```

---

### Task 14: Retirar la capa QWidgets

**Files:**
- Delete: `src/soundboard/ui/main_window.py`, `grid.py`, `clip_button.py`, `login_dialog.py`, `device_dialog.py`, `library_dialog.py`
- Delete: `tests/unit/test_main_window.py`, `test_grid.py`, `test_clip_button.py`, `test_login_dialog.py`, `test_device_dialog.py`, `test_library_dialog.py`
- Modify: `tests/unit/test_ui_and_hotkeys_packages.py` (si nombra módulos borrados)

**Interfaces:**
- Consumes: nada nuevo. Produces: árbol sin QWidgets muertos; suite verde.

- [ ] **Step 1: Verificar que nada vivo importa los módulos a borrar**

Run: `grep -rn "main_window\|clip_button\|login_dialog\|device_dialog\|library_dialog\|ui.grid\b\|from soundboard.ui.grid import" src/ tests/ --include="*.py"`
Expected: solo los archivos listados para borrar (y quizá `test_ui_and_hotkeys_packages.py`). Si aparece algo más, arreglarlo primero.

- [ ] **Step 2: Borrar**

```bash
git rm src/soundboard/ui/main_window.py src/soundboard/ui/grid.py \
       src/soundboard/ui/clip_button.py src/soundboard/ui/login_dialog.py \
       src/soundboard/ui/device_dialog.py src/soundboard/ui/library_dialog.py \
       tests/unit/test_main_window.py tests/unit/test_grid.py \
       tests/unit/test_clip_button.py tests/unit/test_login_dialog.py \
       tests/unit/test_device_dialog.py tests/unit/test_library_dialog.py
```

Actualizar `tests/unit/test_ui_and_hotkeys_packages.py` si enumera módulos de `ui/` (añadir los nuevos: `controller`, `grid_model`, `engine_bridge`, `library_model`; quitar los borrados).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: PASS, todo verde

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(ui): drop the QWidgets layer replaced by QML"
```

---

### Task 15: Packaging — QML en el bundle

**Files:**
- Modify: `packaging/windows/soundboard.spec`
- Modify: `packaging/linux/soundboard.spec`
- Modify: `tests/unit/test_packaging_windows_spec.py`, `tests/unit/test_packaging_linux_spec.py`

**Interfaces:**
- Consumes: `qml_root()` (Task 13) — resuelve `sys._MEIPASS/soundboard/ui/qml`, así que el destino de los datas DEBE ser `soundboard/ui/qml`.
- Produces: specs que empaquetan `src/soundboard/ui/qml/**` como datos y fuerzan los módulos QtQuick de PySide6.

- [ ] **Step 1: Write the failing tests**

Leer primero `tests/unit/test_packaging_windows_spec.py` para copiar su forma de inspeccionar el spec (lectura de texto o exec). Añadir en el estilo del archivo, para ambos specs:

```python
def test_spec_bundles_qml_data() -> None:
    text = SPEC_PATH.read_text()
    assert "ui" in text and "qml" in text          # datas: src/soundboard/ui/qml
    assert "PySide6.QtQuick" in text               # hiddenimports fuerzan los plugins


def test_spec_keeps_quick_controls() -> None:
    text = SPEC_PATH.read_text()
    assert "PySide6.QtQuickControls2" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_packaging_windows_spec.py tests/unit/test_packaging_linux_spec.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

En ambos specs, dentro de `Analysis(...)`:

```python
    datas=[
        (
            os.path.join(SPECPATH, "..", "..", "src", "soundboard", "ui", "qml"),
            os.path.join("soundboard", "ui", "qml"),
        ),
    ],
    hiddenimports=[
        *collect_submodules("keyring.backends"),
        *collect_submodules("pynput"),
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
    ],
```

(El spec de Linux puede tener una lista de hiddenimports distinta — añadir los tres módulos PySide6 a la que exista, no reemplazarla. Los hooks estándar de PyInstaller para PySide6 recogen los plugins/QML de Qt al ver estos imports.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/ -k packaging -v && uv run ruff check . && uv run mypy`
Expected: PASS

- [ ] **Step 5: Build de humo en Windows (opcional pero recomendado antes del PR)**

Run: `uv sync --group packaging && uv run pyinstaller packaging/windows/soundboard.spec --noconfirm --distpath dist-smoke`
Expected: `dist-smoke/soundboard.exe` arranca y muestra la ventana QML (probar a mano; borrar `dist-smoke/` después).

- [ ] **Step 6: Commit**

```bash
git add packaging tests/unit/test_packaging_windows_spec.py tests/unit/test_packaging_linux_spec.py
git commit -m "build: bundle QML assets and QtQuick modules in PyInstaller specs"
```

---

## Self-review del plan

1. **Cobertura del spec:** header (T11-12) ✓, feedback por celda (T1-3, T6, T8, T11) ✓, VU (T2-3, T8, T11) ✓, color por celda (T4, T7, T12) ✓, vistas login/setup/board (T10, T12) ✓, ajustes en caliente (T10, T12) ✓, toasts (T5-7, T10, T12) ✓, biblioteca con filtro (T9, T12) ✓, borrado QWidgets (T14) ✓, packaging (T15) ✓, tray/cierre a bandeja (T13, Main.qml `onClosing`) ✓.
2. **Placeholders:** los puntos «revisar el patrón de X» apuntan siempre a un archivo concreto existente con el patrón a copiar — decisión deliberada, no un TBD.
3. **Consistencia de tipos:** `voice_states() -> list[tuple[int, float]]` uniforme en Mixer/Engine/Bridge/GridModel; roles `cellState`/`cellColor` uniformes entre GridModel y ClipPad/BoardView; slots snake_case en QML (`App.log_in`, `gridModel.clear_cell`) uniforme en vistas.
