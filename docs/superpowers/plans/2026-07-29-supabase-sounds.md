# Biblioteca de sonidos con Supabase — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir la biblioteca de sonidos en multiusuario sobre Supabase — auth por
email/contraseña, CRUD de sonidos y categorías con RLS por dueño, caché local de
reproducción, todo expuesto por la CLI existente.

**Architecture:** Paquete nuevo `remote/` (único punto de I/O de red) detrás de un
protocolo `RemoteClient`, con un `FakeRemoteClient` en memoria para tests unitarios —
mismo patrón que `AudioBackend`/`FakeBackend` de la fase 1. `library/importer.py` decodifica
y mide el sonido antes de tocar la red; `library/cache.py` descarga bajo demanda por
SHA-256. RLS se valida contra un stack local real de Supabase (Supabase CLI + Docker) en
una suite de integración aparte, marcada y excluida por defecto.

**Tech Stack:** Python 3.13, `supabase` 2.31.0 (SDK oficial: Auth + PostgREST + Storage),
`keyring` 25.7.0 (sesión en el almacén de credenciales del SO), pytest, ruff, mypy.
Supabase CLI + Docker solo para los tests de integración de RLS y desarrollo local.

**Spec:** `docs/superpowers/specs/2026-07-29-supabase-sounds-design.md`

## Global Constraints

- Python `>=3.13`. Todas las dependencias binarias publican wheels abi3 o cp313.
- Frecuencia interna fija: **48000 Hz**, mono, `float32` — sin cambios respecto a la fase 1.
- Ningún módulo bajo `src/soundboard/audio/` puede importar `remote/`, `library/`,
  sqlite3 ni hacer I/O de red. `remote/` no importa `audio/`.
- Código, identificadores, docstrings y mensajes de commit en **inglés**. Documentación
  de producto y specs en **español**.
- Ningún fallo se traga en silencio (heredado del diseño original y de la spec de esta
  fase, §10): sesión ausente, permiso denegado por RLS, caché corrupta — todos con
  mensaje explícito, nunca un éxito falso.
- Límite de tamaño: si un fichero supera ~300 líneas, dividirlo.
- Comandos: en esta máquina `uv` está en
  `C:\Users\k\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`
  hasta que se reinicie la terminal. Tras `uv sync` se puede usar `.venv\Scripts\pytest.exe`,
  `.venv\Scripts\ruff.exe` y `.venv\Scripts\mypy.exe` directamente, que es lo que asumen
  los pasos de este plan.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `pyproject.toml` | + dependencias `supabase`, `keyring`; marcador de pytest `supabase` |
| `src/soundboard/library/__init__.py` | Paquete de biblioteca local (decodificación + caché) |
| `src/soundboard/library/importer.py` | Decodifica, mezcla a mono, remuestrea, mide SHA-256 y gain |
| `src/soundboard/library/cache.py` | Caché local de PCM por SHA-256, descarga bajo demanda |
| `src/soundboard/remote/__init__.py` | Paquete de acceso a Supabase |
| `src/soundboard/remote/errors.py` | `NotAuthenticatedError`, `PermissionDeniedError` |
| `src/soundboard/remote/models.py` | `Session`, `Sound`, `Category`, `Profile`, protocolo `RemoteClient` |
| `src/soundboard/remote/fake_client.py` | `FakeRemoteClient` — doble en memoria para tests |
| `src/soundboard/remote/client.py` | `SessionStore` (keyring), config, `SupabaseRemoteClient`, `build_client()` |
| `src/soundboard/remote/auth.py` | signup / login / logout / whoami / display_names |
| `src/soundboard/remote/sounds.py` | CRUD de sonidos + resolución de PCM para reproducir |
| `src/soundboard/remote/categories.py` | CRUD de categorías |
| `src/soundboard/cli.py` | + subcomandos `auth`, `sounds`, `categories`; `run --sound` resuelve id/nombre remoto |
| `supabase/migrations/20260729000000_sounds_library.sql` | Esquema + RLS + bucket de Storage |
| `.github/workflows/ci.yml` | + job `rls` (Supabase CLI/Docker, `pytest -m supabase`) |
| `README.md` | + sección de uso de la biblioteca Supabase |

---

### Task 1: Dependencias y andamiaje de paquetes

**Files:**
- Modify: `pyproject.toml`
- Create: `src/soundboard/library/__init__.py`, `src/soundboard/remote/__init__.py`,
  `src/soundboard/remote/errors.py`
- Test: `tests/unit/test_remote_and_library_packages.py`

**Interfaces:**
- Consumes: nada.
- Produces: paquetes importables `soundboard.library` y `soundboard.remote`;
  `soundboard.remote.errors.NotAuthenticatedError`,
  `soundboard.remote.errors.PermissionDeniedError`; marcador de pytest `supabase`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_remote_and_library_packages.py`:

```python
def test_library_subpackage_is_importable() -> None:
    import soundboard.library  # noqa: F401


def test_remote_subpackage_is_importable() -> None:
    import soundboard.remote  # noqa: F401


def test_remote_errors_are_exceptions() -> None:
    from soundboard.remote.errors import NotAuthenticatedError, PermissionDeniedError

    assert issubclass(NotAuthenticatedError, Exception)
    assert issubclass(PermissionDeniedError, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_remote_and_library_packages.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.library'`.

- [ ] **Step 3: Add dependencies to pyproject.toml**

En `[project] dependencies`, añadir:

```toml
    "supabase>=2.31.0",
    "keyring>=25.7.0",
```

En `[tool.pytest.ini_options]`, cambiar `addopts` y `markers`:

```toml
addopts = "-m 'not hardware and not supabase'"
markers = [
    "hardware: requires a real audio device; deselected by default",
    "supabase: requires a local Supabase stack (Docker); deselected by default",
]
```

En `[[tool.mypy.overrides]]`, añadir un bloque nuevo (mantener el existente de
sounddevice/soxr/soundfile):

```toml
[[tool.mypy.overrides]]
module = ["keyring.*"]
ignore_missing_imports = true
```

- [ ] **Step 4: Create the package files**

`src/soundboard/library/__init__.py`:

```python
"""Local sound library: decoding, hashing and the on-disk playback cache."""
```

`src/soundboard/remote/__init__.py`:

```python
"""Supabase-backed multiuser sound library: the only network I/O in the project."""
```

`src/soundboard/remote/errors.py`:

```python
"""Errors surfaced by the remote sound library.

Kept distinct from stdlib exceptions so the CLI can catch them by type and print a
clear message instead of a stack trace — never a silent no-op.
"""

from __future__ import annotations


class NotAuthenticatedError(Exception):
    """Raised when a remote operation needs a session and none is loaded."""


class PermissionDeniedError(Exception):
    """Raised when RLS reports zero affected rows on an update or delete.

    Zero affected rows means either the row does not exist or it belongs to someone
    else — RLS makes those indistinguishable by design, so the message covers both.
    """
```

- [ ] **Step 5: Sync dependencies and run the tests**

Run:
```
uv sync --all-groups
.venv\Scripts\pytest.exe tests/unit/test_remote_and_library_packages.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/soundboard/library/__init__.py src/soundboard/remote/__init__.py src/soundboard/remote/errors.py tests/unit/test_remote_and_library_packages.py
git commit -m "chore: scaffold library and remote packages, add supabase and keyring deps"
```

---

### Task 2: Importador — decodificación, SHA-256 y gain

**Files:**
- Create: `src/soundboard/library/importer.py`
- Test: `tests/unit/test_importer.py`

**Interfaces:**
- Consumes: nada (usa `soundfile`, `soxr`, `soundboard.audio.mixer.CEILING`).
- Produces:
  - `ImportedSound(pcm: np.ndarray, sha256: str, source_filename: str,
    duration_frames: int, orig_samplerate: int, orig_channels: int, gain_db: float)` —
    dataclass congelada.
  - `import_sound(path: str | Path, samplerate: int = 48_000) -> ImportedSound`

**Nota de diseño:** el SHA-256 se calcula sobre los bytes del **fichero original**, no
sobre el PCM ya procesado — así dos importaciones del mismo fichero deduplican aunque el
remuestreo no sea bit-exacto, igual que en el diseño local original (fase 2 previa,
§5.3, ahora supersedida pero cuyo criterio de dedup se conserva).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_importer.py`:

```python
import hashlib
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundboard.audio.mixer import CEILING
from soundboard.library.importer import import_sound


def _write_wav(path: Path, samples: np.ndarray, samplerate: int) -> None:
    sf.write(str(path), samples, samplerate)


def test_reports_original_samplerate_and_channels(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, np.full((4_410, 2), 0.1, dtype=np.float32), 44_100)

    imported = import_sound(path)

    assert imported.orig_samplerate == 44_100
    assert imported.orig_channels == 2


def test_mixes_to_mono_and_resamples_to_48k(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, np.full((4_410, 2), 0.1, dtype=np.float32), 44_100)

    imported = import_sound(path)

    assert imported.pcm.ndim == 1
    assert imported.duration_frames == imported.pcm.shape[0]
    # 100ms at 44.1kHz resampled to 48kHz is ~4800 frames.
    assert abs(imported.pcm.shape[0] - 4_800) < 10


def test_sha256_matches_the_original_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _write_wav(path, np.full((4_800,), 0.2, dtype=np.float32), 48_000)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    imported = import_sound(path)

    assert imported.sha256 == expected


def test_source_filename_is_the_basename(tmp_path: Path) -> None:
    path = tmp_path / "subdir_marker.wav"
    path.parent.mkdir(exist_ok=True)
    _write_wav(path, np.zeros(480, dtype=np.float32), 48_000)

    imported = import_sound(path)

    assert imported.source_filename == "subdir_marker.wav"


def test_gain_db_brings_the_peak_to_the_limiter_ceiling(tmp_path: Path) -> None:
    path = tmp_path / "half.wav"
    _write_wav(path, np.full((480,), 0.5, dtype=np.float32), 48_000)

    imported = import_sound(path)

    expected_gain_db = 20.0 * math.log10(CEILING / 0.5)
    assert imported.gain_db == pytest.approx(expected_gain_db, abs=1e-2)


def test_silence_gets_zero_gain(tmp_path: Path) -> None:
    path = tmp_path / "silence.wav"
    _write_wav(path, np.zeros(480, dtype=np.float32), 48_000)

    imported = import_sound(path)

    assert imported.gain_db == 0.0
```

`test_gain_db_brings_the_peak_to_the_limiter_ceiling` already doubles as the
non-destructive-normalization check: if `import_sound` baked the gain into the PCM in
place, the measured peak used to compute `gain_db` would already be at `CEILING` and
the assertion against `20*log10(CEILING/0.5)` would fail.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_importer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.library.importer'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/library/importer.py`:

```python
"""Decodes a source file into the engine's internal format and measures it.

Runs once per import, off the real-time path. Produces the same mono float32 48kHz
PCM that ``audio.audioio.load_mono_48k`` produces for the phase-1 CLI, plus the
metadata the remote library needs: a content hash for dedup and a gain that would
bring the clip's peak to the limiter ceiling without ever modifying the samples
themselves.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

from soundboard.audio.mixer import CEILING


@dataclass(frozen=True)
class ImportedSound:
    pcm: np.ndarray
    sha256: str
    source_filename: str
    duration_frames: int
    orig_samplerate: int
    orig_channels: int
    gain_db: float


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure_gain_db(pcm: np.ndarray) -> float:
    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    if peak <= 0.0:
        return 0.0
    return 20.0 * math.log10(CEILING / peak)


def import_sound(path: str | Path, samplerate: int = 48_000) -> ImportedSound:
    """Decode ``path``, mix to mono, resample to ``samplerate`` and measure it."""
    path = Path(path)
    data, orig_samplerate = sf.read(str(path), dtype="float32", always_2d=True)
    orig_channels = data.shape[1]

    mono = data.mean(axis=1)
    if orig_samplerate != samplerate:
        mono = soxr.resample(mono, orig_samplerate, samplerate, quality="HQ")
    pcm = np.ascontiguousarray(mono, dtype=np.float32)

    return ImportedSound(
        pcm=pcm,
        sha256=_sha256_file(path),
        source_filename=path.name,
        duration_frames=pcm.shape[0],
        orig_samplerate=orig_samplerate,
        orig_channels=orig_channels,
        gain_db=_measure_gain_db(pcm),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_importer.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/library/importer.py tests/unit/test_importer.py
git commit -m "feat(library): add importer with sha256 dedup key and ceiling-relative gain"
```

---

### Task 3: Caché local de reproducción

**Files:**
- Create: `src/soundboard/library/cache.py`
- Test: `tests/unit/test_cache.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `SoundCache(cache_dir: str | Path)`
  - `SoundCache.has(sha256: str) -> bool`
  - `SoundCache.read(sha256: str) -> np.ndarray`
  - `SoundCache.write(sha256: str, pcm: np.ndarray) -> None`
  - `SoundCache.get_or_fetch(sha256: str, fetch: Callable[[], bytes],
    expected_frames: int | None = None) -> np.ndarray`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_cache.py`:

```python
from pathlib import Path

import numpy as np
import pytest

from soundboard.library.cache import SoundCache


def test_has_reports_false_for_an_unknown_hash(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)

    assert cache.has("deadbeef") is False


def test_write_then_read_roundtrips_the_pcm(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    pcm = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    cache.write("abc123", pcm)

    assert cache.has("abc123") is True
    assert np.array_equal(cache.read("abc123"), pcm)


def test_get_or_fetch_returns_cached_pcm_without_calling_fetch(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    pcm = np.array([1.0, 2.0], dtype=np.float32)
    cache.write("hit", pcm)

    def fail_if_called() -> bytes:
        raise AssertionError("fetch should not be called on a cache hit")

    result = cache.get_or_fetch("hit", fail_if_called, expected_frames=2)

    assert np.array_equal(result, pcm)


def test_get_or_fetch_downloads_and_caches_on_a_miss(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    pcm = np.array([0.5, -0.5, 0.25, -0.25], dtype=np.float32)
    calls = 0

    def fetch() -> bytes:
        nonlocal calls
        calls += 1
        return pcm.tobytes()

    result = cache.get_or_fetch("miss", fetch, expected_frames=4)

    assert calls == 1
    assert np.array_equal(result, pcm)
    assert cache.has("miss") is True
    # A second call must hit the now-populated cache, not fetch again.
    cache.get_or_fetch("miss", fetch, expected_frames=4)
    assert calls == 1


def test_get_or_fetch_redownloads_when_the_cached_file_is_truncated(tmp_path: Path) -> None:
    cache = SoundCache(tmp_path)
    cache.write("corrupt", np.array([1.0], dtype=np.float32))  # 1 frame, not the real 3
    good_pcm = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    def fetch() -> bytes:
        return good_pcm.tobytes()

    result = cache.get_or_fetch("corrupt", fetch, expected_frames=3)

    assert np.array_equal(result, good_pcm)


def test_creates_the_cache_directory_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "pcm" / "nested"

    SoundCache(nested)

    assert nested.is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_cache.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.library.cache'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/library/cache.py`:

```python
"""On-disk playback cache, keyed by content hash.

Files are named ``<sha256>.f32`` — raw mono float32 frames at the engine sample rate,
the same bytes stored remotely. No header, no format negotiation: the caller always
knows the sample rate (48kHz, fixed) and, when it wants a corruption check, the
expected frame count from the remote row.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np


class SoundCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str) -> Path:
        return self._dir / f"{sha256}.f32"

    def has(self, sha256: str) -> bool:
        return self._path(sha256).exists()

    def read(self, sha256: str) -> np.ndarray:
        return np.fromfile(self._path(sha256), dtype=np.float32)

    def write(self, sha256: str, pcm: np.ndarray) -> None:
        np.ascontiguousarray(pcm, dtype=np.float32).tofile(self._path(sha256))

    def get_or_fetch(
        self,
        sha256: str,
        fetch: Callable[[], bytes],
        expected_frames: int | None = None,
    ) -> np.ndarray:
        """Return the cached PCM for ``sha256``, downloading on a miss.

        A cached file whose frame count does not match ``expected_frames`` is treated
        as corrupt (e.g. a previous run was killed mid-write) and re-downloaded
        transparently, rather than handed to the caller or reported as an error.
        """
        if self.has(sha256):
            pcm = self.read(sha256)
            if expected_frames is None or pcm.shape[0] == expected_frames:
                return pcm
        pcm = np.frombuffer(fetch(), dtype=np.float32).copy()
        self.write(sha256, pcm)
        return pcm
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_cache.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/library/cache.py tests/unit/test_cache.py
git commit -m "feat(library): add sha256-keyed playback cache with corruption recovery"
```

---

### Task 4: Modelos y protocolo RemoteClient

**Files:**
- Create: `src/soundboard/remote/models.py`
- Test: `tests/unit/test_remote_models.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `Session(access_token: str, refresh_token: str, user_id: str, email: str)` —
    dataclass congelada.
  - `Sound(id, owner_id, category_id, name, sha256, storage_path, source_filename,
    duration_frames, orig_samplerate, orig_channels, gain_db, trim_start_frames,
    trim_end_frames, loop, color, tags)` — dataclass congelada.
  - `Category(id, name, color, position, created_by)` — dataclass congelada.
  - `Profile(id, display_name)` — dataclass congelada.
  - Protocolo `RemoteClient` con: `sign_up`, `sign_in`, `sign_out`, `restore_session`,
    `insert`, `select`, `update`, `delete`, `storage_upload`, `storage_download`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_remote_models.py`:

```python
def test_models_and_protocol_are_importable() -> None:
    from soundboard.remote.models import (  # noqa: F401
        Category,
        Profile,
        RemoteClient,
        Session,
        Sound,
    )


def test_session_is_a_frozen_dataclass() -> None:
    from soundboard.remote.models import Session

    session = Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com")

    assert session.user_id == "u"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_remote_models.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.remote.models'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/remote/models.py`:

```python
"""Data shapes shared across the remote sound library and its client protocol.

``RemoteClient`` is the seam between the library logic (auth.py, sounds.py,
categories.py) and whatever talks to Supabase — the same role ``AudioBackend`` plays
for the audio engine. Two implementations exist: ``SupabaseRemoteClient`` (real) and
``FakeRemoteClient`` (in-memory, for tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    user_id: str
    email: str


@dataclass(frozen=True)
class Profile:
    id: str
    display_name: str


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    color: str | None
    position: int
    created_by: str


@dataclass(frozen=True)
class Sound:
    id: str
    owner_id: str
    category_id: str | None
    name: str
    sha256: str
    storage_path: str
    source_filename: str
    duration_frames: int
    orig_samplerate: int
    orig_channels: int
    gain_db: float
    trim_start_frames: int
    trim_end_frames: int | None
    loop: bool
    color: str | None
    tags: list[str] = field(default_factory=list)


class RemoteClient(Protocol):
    def sign_up(self, email: str, password: str) -> None: ...
    def sign_in(self, email: str, password: str) -> Session: ...
    def sign_out(self) -> None: ...
    def restore_session(self, session: Session) -> None: ...

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    def update(self, table: str, id_: str, fields: dict[str, Any]) -> int:
        """Returns the number of rows affected. 0 means not found or not permitted."""
        ...

    def delete(self, table: str, id_: str) -> int:
        """Returns the number of rows affected. 0 means not found or not permitted."""
        ...

    def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
        """Idempotent: uploading the same content-addressed path twice is a no-op."""
        ...

    def storage_download(self, bucket: str, path: str) -> bytes: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_remote_models.py -v`
Expected: 2 passed.

- [ ] **Step 5: Verify types**

Run: `.venv\Scripts\mypy.exe`
Expected: sin errores. (Protocol members with `...` bodies are fine under strict mypy.)

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/remote/models.py tests/unit/test_remote_models.py
git commit -m "feat(remote): add Session/Sound/Category/Profile models and RemoteClient protocol"
```

---

### Task 5: FakeRemoteClient

**Files:**
- Create: `src/soundboard/remote/fake_client.py`
- Test: `tests/unit/test_fake_remote_client.py`

**Interfaces:**
- Consumes: `soundboard.remote.models.Session`.
- Produces: `FakeRemoteClient()` implementando `RemoteClient` — CRUD en memoria con
  reglas de ownership por tabla (simula el resultado observable de RLS: 0 filas
  afectadas si `update`/`delete` no coinciden con el usuario activo), auth en memoria,
  storage en memoria con upload idempotente.

**Nota:** este doble simula el *contrato* que `sounds.py`/`categories.py` dependen de
(conteo de filas afectadas), no las políticas SQL en sí — esas solo las valida de
verdad la suite de integración de la Task 11 contra Postgres real.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_fake_remote_client.py`:

```python
import pytest

from soundboard.remote.fake_client import FakeRemoteClient


def test_sign_up_then_sign_in_returns_a_session_with_a_stable_user_id() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")

    session = client.sign_in("a@x.com", "hunter2")

    assert session.email == "a@x.com"
    assert session.user_id


def test_sign_in_with_wrong_password_raises() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")

    with pytest.raises(ValueError):
        client.sign_in("a@x.com", "wrong")


def test_insert_then_select_roundtrips_a_row() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    client.sign_in("a@x.com", "hunter2")

    row = client.insert("categories", {"name": "memes", "created_by": "u1"})
    found = client.select("categories", filters={"name": "memes"})

    assert found == [row]


def test_select_with_no_filters_returns_every_row() -> None:
    client = FakeRemoteClient()
    client.insert("categories", {"name": "a"})
    client.insert("categories", {"name": "b"})

    rows = client.select("categories", filters=None)

    assert {r["name"] for r in rows} == {"a", "b"}


def test_owner_can_update_their_own_sound_row() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    row = client.insert("sounds", {"owner_id": session.user_id, "name": "old"})

    affected = client.update("sounds", row["id"], {"name": "new"})

    assert affected == 1
    assert client.select("sounds", filters={"id": row["id"]})[0]["name"] == "new"


def test_stranger_cannot_update_someone_elses_sound_row() -> None:
    client = FakeRemoteClient()
    owner_session = client.sign_in_as_new_user("owner@x.com")
    client.sign_in_as_new_user("stranger@x.com")  # switches "current user" to the stranger
    row = client.insert("sounds", {"owner_id": owner_session.user_id, "name": "old"})

    affected = client.update("sounds", row["id"], {"name": "hijacked"})

    assert affected == 0
    assert client.select("sounds", filters={"id": row["id"]})[0]["name"] == "old"


def test_stranger_cannot_delete_someone_elses_category() -> None:
    client = FakeRemoteClient()
    owner_session = client.sign_in_as_new_user("owner@x.com")
    row = client.insert("categories", {"name": "owned", "created_by": owner_session.user_id})
    client.sign_in_as_new_user("stranger@x.com")

    affected = client.delete("categories", row["id"])

    assert affected == 0
    assert client.select("categories", filters={"id": row["id"]})


def test_update_of_a_missing_row_returns_zero() -> None:
    client = FakeRemoteClient()
    client.sign_in_as_new_user("a@x.com")

    assert client.update("sounds", "nonexistent", {"name": "x"}) == 0


def test_storage_upload_then_download_roundtrips_bytes() -> None:
    client = FakeRemoteClient()

    client.storage_upload("sounds", "abc.f32", b"\x01\x02\x03\x04")

    assert client.storage_download("sounds", "abc.f32") == b"\x01\x02\x03\x04"


def test_storage_upload_is_idempotent_on_the_same_path() -> None:
    client = FakeRemoteClient()

    client.storage_upload("sounds", "abc.f32", b"first")
    client.storage_upload("sounds", "abc.f32", b"first")  # same content, re-uploaded

    assert client.storage_download("sounds", "abc.f32") == b"first"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_fake_remote_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.remote.fake_client'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/remote/fake_client.py`:

```python
"""In-memory RemoteClient, for tests. No network, no Supabase."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from soundboard.remote.models import Session

_OWNER_COLUMN = {
    "sounds": "owner_id",
    "categories": "created_by",
    "profiles": "id",
}


class FakeRemoteClient:
    def __init__(self) -> None:
        self._passwords: dict[str, str] = {}
        self._user_ids: dict[str, str] = {}
        self._tables: dict[str, dict[str, dict[str, Any]]] = {}
        self._storage: dict[str, bytes] = {}
        self._current_user_id: str | None = None

    # -- auth ---------------------------------------------------------------

    def sign_up(self, email: str, password: str) -> None:
        if email not in self._user_ids:
            self._user_ids[email] = str(uuid4())
        self._passwords[email] = password

    def sign_in(self, email: str, password: str) -> Session:
        if self._passwords.get(email) != password:
            raise ValueError(f"invalid credentials for {email!r}")
        self._current_user_id = self._user_ids[email]
        return Session(
            access_token=f"fake-access-{email}",
            refresh_token=f"fake-refresh-{email}",
            user_id=self._current_user_id,
            email=email,
        )

    def sign_in_as_new_user(self, email: str) -> Session:
        """Test convenience: sign_up + sign_in in one call, random password."""
        self.sign_up(email, "password")
        return self.sign_in(email, "password")

    def sign_out(self) -> None:
        self._current_user_id = None

    def restore_session(self, session: Session) -> None:
        self._current_user_id = session.user_id

    # -- tables ---------------------------------------------------------------

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        stored = dict(row)
        stored.setdefault("id", str(uuid4()))
        self._tables.setdefault(table, {})[stored["id"]] = stored
        return dict(stored)

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        rows = list(self._tables.get(table, {}).values())
        if filters:
            rows = [r for r in rows if all(r.get(k) == v for k, v in filters.items())]
        return [dict(r) for r in rows]

    def _authorized_row(self, table: str, id_: str) -> dict[str, Any] | None:
        row = self._tables.get(table, {}).get(id_)
        if row is None:
            return None
        owner_column = _OWNER_COLUMN.get(table)
        if owner_column is not None and row.get(owner_column) != self._current_user_id:
            return None
        return row

    def update(self, table: str, id_: str, fields: dict[str, Any]) -> int:
        row = self._authorized_row(table, id_)
        if row is None:
            return 0
        row.update(fields)
        return 1

    def delete(self, table: str, id_: str) -> int:
        row = self._authorized_row(table, id_)
        if row is None:
            return 0
        del self._tables[table][id_]
        return 1

    # -- storage ---------------------------------------------------------------

    def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
        self._storage[f"{bucket}/{path}"] = data

    def storage_download(self, bucket: str, path: str) -> bytes:
        return self._storage[f"{bucket}/{path}"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_fake_remote_client.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/remote/fake_client.py tests/unit/test_fake_remote_client.py
git commit -m "feat(remote): add in-memory FakeRemoteClient for tests"
```

---

### Task 6: SessionStore, configuración y SupabaseRemoteClient real

**Files:**
- Create: `src/soundboard/remote/client.py`
- Test: `tests/unit/test_client.py`

**Interfaces:**
- Consumes: `soundboard.remote.models.Session`, `soundboard.remote.models.RemoteClient`.
- Produces:
  - `SessionStore(backend: KeyringBackend | None = None)` con `save`, `load`, `clear`.
  - `load_supabase_config(env: Mapping[str, str] | None = None, settings_path: Path
    | None = None) -> tuple[str, str]` — resuelve `(url, anon_key)`.
  - `SupabaseRemoteClient(url: str, anon_key: str)` implementando `RemoteClient` sobre
    el SDK `supabase-py`.
  - `build_client() -> SupabaseRemoteClient` — construye con `load_supabase_config()`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_client.py`:

```python
import json
from pathlib import Path
from typing import Any

import pytest

from soundboard.remote.client import (
    SessionStore,
    SupabaseRemoteClient,
    load_supabase_config,
)
from soundboard.remote.models import Session


class _FakeKeyringBackend:
    """Dict-backed stand-in for the ``keyring`` module's module-level functions."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


def test_session_store_round_trips_a_session() -> None:
    store = SessionStore(backend=_FakeKeyringBackend())
    session = Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com")

    store.save(session)

    assert store.load() == session


def test_session_store_load_returns_none_when_empty() -> None:
    store = SessionStore(backend=_FakeKeyringBackend())

    assert store.load() is None


def test_session_store_clear_is_idempotent() -> None:
    store = SessionStore(backend=_FakeKeyringBackend())
    store.save(Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com"))

    store.clear()
    store.clear()  # second clear on an already-empty store must not raise

    assert store.load() is None


def test_load_supabase_config_prefers_environment_variables() -> None:
    env = {
        "SOUNDBOARD_SUPABASE_URL": "https://env.supabase.co",
        "SOUNDBOARD_SUPABASE_ANON_KEY": "env-key",
    }

    url, key = load_supabase_config(env=env, settings_path=Path("/nonexistent"))

    assert (url, key) == ("https://env.supabase.co", "env-key")


def test_load_supabase_config_falls_back_to_settings_file(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"supabase": {"url": "https://file.supabase.co", "anon_key": "file-key"}})
    )

    url, key = load_supabase_config(env={}, settings_path=settings_path)

    assert (url, key) == ("https://file.supabase.co", "file-key")


def test_load_supabase_config_raises_a_clear_error_when_unconfigured(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="SOUNDBOARD_SUPABASE_URL"):
        load_supabase_config(env={}, settings_path=tmp_path / "missing.json")


class _FakeQuery:
    def __init__(self, table: "_FakeTable", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []

    def eq(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append((column, value))
        return self

    def execute(self) -> Any:
        return self._table.run(self._op, self._payload, self._filters)


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, columns: str) -> _FakeQuery:
        return _FakeQuery(self, "select")

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self, "insert", row)

    def update(self, fields: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self, "update", fields)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self, "delete")

    def run(self, op: str, payload: Any, filters: list[tuple[str, Any]]) -> _FakeResponse:
        if op == "insert":
            row = dict(payload)
            row.setdefault("id", "new-id")
            self.rows.append(row)
            return _FakeResponse([row])

        matched = [
            r for r in self.rows if all(r.get(col) == val for col, val in filters)
        ]
        if op == "select":
            return _FakeResponse(matched)
        if op == "update":
            for row in matched:
                row.update(payload)
            return _FakeResponse(matched)
        if op == "delete":
            for row in matched:
                self.rows.remove(row)
            return _FakeResponse(matched)
        raise AssertionError(f"unexpected op {op!r}")


class _FakeStorageBucket:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, bytes, dict[str, Any]]] = []
        self._blobs: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, file_options: dict[str, Any]) -> None:
        self.uploaded.append((path, data, file_options))
        self._blobs[path] = data

    def download(self, path: str) -> bytes:
        return self._blobs[path]


class _FakeStorage:
    def __init__(self) -> None:
        self.bucket = _FakeStorageBucket()

    def from_(self, bucket: str) -> _FakeStorageBucket:
        return self.bucket


class _FakeAuth:
    def sign_up(self, credentials: dict[str, str]) -> None:
        pass

    def sign_out(self) -> None:
        pass


class _FakeSDKClient:
    def __init__(self) -> None:
        self.auth = _FakeAuth()
        self.storage = _FakeStorage()
        self._tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self._tables.setdefault(name, _FakeTable([]))


def test_supabase_remote_client_insert_select_update_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sdk = _FakeSDKClient()
    monkeypatch.setattr(
        "soundboard.remote.client.create_client", lambda url, key: fake_sdk
    )
    client = SupabaseRemoteClient("https://x.supabase.co", "anon-key")

    row = client.insert("categories", {"name": "memes"})
    assert client.select("categories", filters={"name": "memes"}) == [row]

    affected = client.update("categories", row["id"], {"name": "renamed"})
    assert affected == 1
    assert client.select("categories", filters={"id": row["id"]})[0]["name"] == "renamed"

    affected = client.delete("categories", row["id"])
    assert affected == 1
    assert client.select("categories", filters={"id": row["id"]}) == []


def test_supabase_remote_client_uploads_with_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sdk = _FakeSDKClient()
    monkeypatch.setattr(
        "soundboard.remote.client.create_client", lambda url, key: fake_sdk
    )
    client = SupabaseRemoteClient("https://x.supabase.co", "anon-key")

    client.storage_upload("sounds", "abc.f32", b"\x00\x01")

    path, data, options = fake_sdk.storage.bucket.uploaded[0]
    assert path == "abc.f32"
    assert data == b"\x00\x01"
    assert options["upsert"] == "true"
    assert client.storage_download("sounds", "abc.f32") == b"\x00\x01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.remote.client'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/remote/client.py`:

```python
"""Session persistence, config resolution and the real Supabase-backed client."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

import keyring
import platformdirs
from keyring.errors import PasswordDeleteError
from supabase import create_client

from soundboard.remote.models import Session

_SERVICE_NAME = "soundboard"
_KEYRING_USERNAME = "session"


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class SessionStore:
    """Persists the active session in the OS credential store between CLI runs."""

    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend: KeyringBackend = backend if backend is not None else keyring

    def save(self, session: Session) -> None:
        self._backend.set_password(_SERVICE_NAME, _KEYRING_USERNAME, json.dumps(asdict(session)))

    def load(self) -> Session | None:
        raw = self._backend.get_password(_SERVICE_NAME, _KEYRING_USERNAME)
        if raw is None:
            return None
        return Session(**json.loads(raw))

    def clear(self) -> None:
        try:
            self._backend.delete_password(_SERVICE_NAME, _KEYRING_USERNAME)
        except PasswordDeleteError:
            pass  # already empty: clearing an absent session is not an error


def _default_settings_path() -> Path:
    return Path(platformdirs.user_config_dir("soundboard")) / "settings.json"


def load_supabase_config(
    env: dict[str, str] | None = None, settings_path: Path | None = None
) -> tuple[str, str]:
    """Resolve ``(url, anon_key)`` from the environment, falling back to settings.json."""
    env = os.environ if env is None else env  # type: ignore[assignment]
    settings_path = settings_path or _default_settings_path()

    url = env.get("SOUNDBOARD_SUPABASE_URL")
    key = env.get("SOUNDBOARD_SUPABASE_ANON_KEY")
    if not url or not key:
        if settings_path.exists():
            data = json.loads(settings_path.read_text())
            supabase_cfg = data.get("supabase", {})
            url = url or supabase_cfg.get("url")
            key = key or supabase_cfg.get("anon_key")
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured: set SOUNDBOARD_SUPABASE_URL and "
            f"SOUNDBOARD_SUPABASE_ANON_KEY, or add them to {settings_path}"
        )
    return url, key


class SupabaseRemoteClient:
    """Wraps the official ``supabase`` SDK behind the ``RemoteClient`` protocol."""

    def __init__(self, url: str, anon_key: str) -> None:
        self._client = create_client(url, anon_key)

    def sign_up(self, email: str, password: str) -> None:
        self._client.auth.sign_up({"email": email, "password": password})

    def sign_in(self, email: str, password: str) -> Session:
        result = self._client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        return Session(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            user_id=result.user.id,
            email=result.user.email,
        )

    def sign_out(self) -> None:
        self._client.auth.sign_out()

    def restore_session(self, session: Session) -> None:
        self._client.auth.set_session(session.access_token, session.refresh_token)

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        response = self._client.table(table).insert(row).execute()
        return dict(response.data[0])

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        query = self._client.table(table).select("*")
        for column, value in (filters or {}).items():
            query = query.eq(column, value)
        return [dict(row) for row in query.execute().data]

    def update(self, table: str, id_: str, fields: dict[str, Any]) -> int:
        response = self._client.table(table).update(fields).eq("id", id_).execute()
        return len(response.data)

    def delete(self, table: str, id_: str) -> int:
        response = self._client.table(table).delete().eq("id", id_).execute()
        return len(response.data)

    def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
        self._client.storage.from_(bucket).upload(path, data, file_options={"upsert": "true"})

    def storage_download(self, bucket: str, path: str) -> bytes:
        result = self._client.storage.from_(bucket).download(path)
        return bytes(result)


def build_client() -> SupabaseRemoteClient:
    url, anon_key = load_supabase_config()
    return SupabaseRemoteClient(url, anon_key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_client.py -v`
Expected: 8 passed.

- [ ] **Step 5: Verify lint and types**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores. Si `supabase`/`keyring` no traen *stubs* completos y mypy
se queja de tipos de retorno del SDK, añadir `supabase.*` a los `ignore_missing_imports`
del `[[tool.mypy.overrides]]` creado en la Task 1.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/remote/client.py tests/unit/test_client.py pyproject.toml
git commit -m "feat(remote): add SessionStore, config resolution and SupabaseRemoteClient"
```

---

### Task 7: Autenticación

**Files:**
- Create: `src/soundboard/remote/auth.py`
- Test: `tests/unit/test_auth.py`

**Interfaces:**
- Consumes: `RemoteClient`, `SessionStore`, `Session` (Tasks 4–6).
- Produces:
  - `sign_up(client, email, password) -> None`
  - `log_in(client, store, email, password, display_name_prompt: Callable[[], str]) ->
    Session` — crea la fila en `profiles` si es el primer login.
  - `log_out(client, store) -> None`
  - `require_session(client, store) -> Session` — lanza `NotAuthenticatedError` si no
    hay sesión guardada; si la hay, la restaura en `client` y la devuelve.
  - `display_names(client, user_ids: list[str]) -> dict[str, str]`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_auth.py`:

```python
import pytest

from soundboard.remote import auth
from soundboard.remote.client import SessionStore
from soundboard.remote.errors import NotAuthenticatedError
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.remote.models import Session


class _DictKeyringBackend:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


def _store() -> SessionStore:
    return SessionStore(backend=_DictKeyringBackend())


def test_log_in_saves_the_session() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()

    session = auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    assert store.load() == session


def test_log_in_creates_a_profile_on_first_login() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()

    session = auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    profiles = client.select("profiles", filters={"id": session.user_id})
    assert profiles == [{"id": session.user_id, "display_name": "Pablo"}]


def test_log_in_does_not_prompt_or_duplicate_an_existing_profile() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()
    auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    def fail_if_called() -> str:
        raise AssertionError("must not prompt again on a second login")

    auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=fail_if_called)

    assert len(client.select("profiles", filters=None)) == 1


def test_log_out_clears_the_stored_session() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()
    auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    auth.log_out(client, store)

    assert store.load() is None


def test_require_session_raises_when_none_is_stored() -> None:
    client = FakeRemoteClient()
    store = _store()

    with pytest.raises(NotAuthenticatedError):
        auth.require_session(client, store)


def test_require_session_restores_and_returns_the_stored_session() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()
    logged_in = auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    restored = auth.require_session(client, store)

    assert restored == logged_in


def test_display_names_maps_user_ids_to_names() -> None:
    client = FakeRemoteClient()
    client.insert("profiles", {"id": "u1", "display_name": "Pablo"})
    client.insert("profiles", {"id": "u2", "display_name": "Ana"})

    names = auth.display_names(client, ["u1", "u2", "u3"])

    assert names == {"u1": "Pablo", "u2": "Ana"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_auth.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.remote.auth'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/remote/auth.py`:

```python
"""Sign-up, login, logout and the first-login profile bootstrap."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from soundboard.remote.client import SessionStore
from soundboard.remote.errors import NotAuthenticatedError
from soundboard.remote.models import RemoteClient, Session


def sign_up(client: RemoteClient, email: str, password: str) -> None:
    client.sign_up(email, password)


def log_in(
    client: RemoteClient,
    store: SessionStore,
    email: str,
    password: str,
    display_name_prompt: Callable[[], str],
) -> Session:
    session = client.sign_in(email, password)
    store.save(session)
    if not client.select("profiles", filters={"id": session.user_id}):
        client.insert("profiles", {"id": session.user_id, "display_name": display_name_prompt()})
    return session


def log_out(client: RemoteClient, store: SessionStore) -> None:
    client.sign_out()
    store.clear()


def require_session(client: RemoteClient, store: SessionStore) -> Session:
    """Load the stored session, restore it onto ``client``, and return it.

    Raises ``NotAuthenticatedError`` rather than silently proceeding unauthenticated —
    every remote command needs a clear, actionable error instead of a confusing
    downstream RLS rejection.
    """
    session = store.load()
    if session is None:
        raise NotAuthenticatedError("no session found; run `soundboard auth login` first")
    client.restore_session(session)
    return session


def display_names(client: RemoteClient, user_ids: Iterable[str]) -> dict[str, str]:
    wanted = set(user_ids)
    if not wanted:
        return {}
    rows = client.select("profiles", filters=None)
    return {row["id"]: row["display_name"] for row in rows if row["id"] in wanted}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_auth.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/remote/auth.py tests/unit/test_auth.py
git commit -m "feat(remote): add signup/login/logout with first-login profile bootstrap"
```

---

### Task 8: CRUD de sonidos

**Files:**
- Create: `src/soundboard/remote/sounds.py`
- Test: `tests/unit/test_sounds.py`

**Interfaces:**
- Consumes: `RemoteClient`, `Session` (Task 4), `import_sound`/`ImportedSound` (Task 2),
  `SoundCache` (Task 3), `PermissionDeniedError` (Task 1).
- Produces:
  - `add_sound(client, session, path, name, category_id=None) -> Sound` — idempotente
    por `(owner_id, sha256)`.
  - `list_sounds(client, *, owner_id=None, category_id=None) -> list[Sound]`
  - `get_sound(client, sound_id) -> Sound` — lanza `LookupError` si no existe.
  - `find_sound_by_name(client, name) -> Sound | None`
  - `edit_sound(client, sound_id, **fields) -> Sound` — lanza `PermissionDeniedError`
    si RLS afecta 0 filas.
  - `remove_sound(client, sound_id) -> None` — igual.
  - `resolve_pcm(client, cache, sound) -> np.ndarray` — caché primero, descarga si falta.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_sounds.py`:

```python
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.fake_client import FakeRemoteClient


def _clip(tmp_path: Path, name: str = "clip.wav") -> Path:
    path = tmp_path / name
    sf.write(str(path), np.full(480, 0.3, dtype=np.float32), 48_000)
    return path


def test_add_sound_creates_a_row_owned_by_the_caller(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")

    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    assert sound.owner_id == session.user_id
    assert sound.name == "laugh"
    assert sound.duration_frames == 480


def test_add_sound_uploads_the_pcm_to_storage(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")

    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    blob = client.storage_download("sounds", sound.storage_path)
    assert np.frombuffer(blob, dtype=np.float32).shape[0] == sound.duration_frames


def test_add_sound_is_idempotent_for_the_same_owner_and_file(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    clip = _clip(tmp_path)

    first = sounds.add_sound(client, session, str(clip), name="laugh")
    second = sounds.add_sound(client, session, str(clip), name="laugh again")

    assert first.id == second.id
    assert len(client.select("sounds", filters=None)) == 1


def test_list_sounds_filters_by_owner(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    sounds.add_sound(client, owner, str(_clip(tmp_path, "a.wav")), name="a")
    other = client.sign_in_as_new_user("other@x.com")
    sounds.add_sound(client, other, str(_clip(tmp_path, "b.wav")), name="b")

    mine = sounds.list_sounds(client, owner_id=owner.user_id)

    assert [s.name for s in mine] == ["a"]


def test_edit_sound_by_the_owner_succeeds(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    edited = sounds.edit_sound(client, sound.id, name="renamed")

    assert edited.name == "renamed"


def test_edit_sound_by_a_stranger_is_denied(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, owner, str(_clip(tmp_path)), name="laugh")
    client.sign_in_as_new_user("stranger@x.com")

    with pytest.raises(PermissionDeniedError):
        sounds.edit_sound(client, sound.id, name="hijacked")


def test_remove_sound_by_the_owner_succeeds(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    sounds.remove_sound(client, sound.id)

    assert sounds.list_sounds(client) == []


def test_remove_sound_by_a_stranger_is_denied(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, owner, str(_clip(tmp_path)), name="laugh")
    client.sign_in_as_new_user("stranger@x.com")

    with pytest.raises(PermissionDeniedError):
        sounds.remove_sound(client, sound.id)


def test_get_sound_raises_lookup_error_when_missing() -> None:
    client = FakeRemoteClient()

    with pytest.raises(LookupError):
        sounds.get_sound(client, "nonexistent")


def test_resolve_pcm_downloads_on_a_cache_miss(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")
    cache = SoundCache(tmp_path / "cache")

    pcm = sounds.resolve_pcm(client, cache, sound)

    assert pcm.shape[0] == sound.duration_frames
    assert cache.has(sound.sha256)


def test_resolve_pcm_uses_the_cache_on_a_hit(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")
    cache = SoundCache(tmp_path / "cache")
    sounds.resolve_pcm(client, cache, sound)  # populates the cache

    # Corrupt storage after the fact: a cache hit must never touch it again.
    client._storage[f"sounds/{sound.storage_path}"] = b""

    pcm = sounds.resolve_pcm(client, cache, sound)
    assert pcm.shape[0] == sound.duration_frames
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_sounds.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.remote.sounds'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/remote/sounds.py`:

```python
"""CRUD for the shared sound library, plus PCM resolution for playback."""

from __future__ import annotations

from typing import Any

import numpy as np

from soundboard.library.cache import SoundCache
from soundboard.library.importer import import_sound
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.models import RemoteClient, Session, Sound

BUCKET = "sounds"


def _row_to_sound(row: dict[str, Any]) -> Sound:
    return Sound(
        id=row["id"],
        owner_id=row["owner_id"],
        category_id=row.get("category_id"),
        name=row["name"],
        sha256=row["sha256"],
        storage_path=row["storage_path"],
        source_filename=row["source_filename"],
        duration_frames=row["duration_frames"],
        orig_samplerate=row["orig_samplerate"],
        orig_channels=row["orig_channels"],
        gain_db=row["gain_db"],
        trim_start_frames=row.get("trim_start_frames", 0),
        trim_end_frames=row.get("trim_end_frames"),
        loop=row.get("loop", False),
        color=row.get("color"),
        tags=row.get("tags") or [],
    )


def add_sound(
    client: RemoteClient,
    session: Session,
    path: str,
    name: str,
    category_id: str | None = None,
) -> Sound:
    """Import ``path`` and add it to the library. Idempotent per (owner, content)."""
    imported = import_sound(path)

    existing = client.select(
        "sounds", filters={"owner_id": session.user_id, "sha256": imported.sha256}
    )
    if existing:
        return _row_to_sound(existing[0])

    storage_path = f"{imported.sha256}.f32"
    client.storage_upload(BUCKET, storage_path, imported.pcm.tobytes())

    row = client.insert(
        "sounds",
        {
            "owner_id": session.user_id,
            "category_id": category_id,
            "name": name,
            "sha256": imported.sha256,
            "storage_path": storage_path,
            "source_filename": imported.source_filename,
            "duration_frames": imported.duration_frames,
            "orig_samplerate": imported.orig_samplerate,
            "orig_channels": imported.orig_channels,
            "gain_db": imported.gain_db,
            "trim_start_frames": 0,
            "trim_end_frames": None,
            "loop": False,
        },
    )
    return _row_to_sound(row)


def list_sounds(
    client: RemoteClient, *, owner_id: str | None = None, category_id: str | None = None
) -> list[Sound]:
    filters: dict[str, Any] = {}
    if owner_id is not None:
        filters["owner_id"] = owner_id
    if category_id is not None:
        filters["category_id"] = category_id
    rows = client.select("sounds", filters=filters or None)
    return [_row_to_sound(row) for row in rows]


def get_sound(client: RemoteClient, sound_id: str) -> Sound:
    rows = client.select("sounds", filters={"id": sound_id})
    if not rows:
        raise LookupError(f"no sound with id {sound_id!r}")
    return _row_to_sound(rows[0])


def find_sound_by_name(client: RemoteClient, name: str) -> Sound | None:
    rows = client.select("sounds", filters={"name": name})
    return _row_to_sound(rows[0]) if rows else None


def edit_sound(client: RemoteClient, sound_id: str, **fields: Any) -> Sound:
    affected = client.update("sounds", sound_id, fields)
    if affected == 0:
        raise PermissionDeniedError(f"cannot edit sound {sound_id!r}: not found or not yours")
    return get_sound(client, sound_id)


def remove_sound(client: RemoteClient, sound_id: str) -> None:
    affected = client.delete("sounds", sound_id)
    if affected == 0:
        raise PermissionDeniedError(f"cannot delete sound {sound_id!r}: not found or not yours")


def resolve_pcm(client: RemoteClient, cache: SoundCache, sound: Sound) -> np.ndarray:
    def fetch() -> bytes:
        return client.storage_download(BUCKET, sound.storage_path)

    return cache.get_or_fetch(sound.sha256, fetch, expected_frames=sound.duration_frames)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_sounds.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/remote/sounds.py tests/unit/test_sounds.py
git commit -m "feat(remote): add sound CRUD with owner-checked edit/delete and cache resolution"
```

---

### Task 9: CRUD de categorías

**Files:**
- Create: `src/soundboard/remote/categories.py`
- Test: `tests/unit/test_categories.py`

**Interfaces:**
- Consumes: `RemoteClient`, `Session` (Task 4), `PermissionDeniedError` (Task 1).
- Produces:
  - `add_category(client, session, name, color=None) -> Category` — idempotente por
    `name`.
  - `list_categories(client) -> list[Category]`
  - `remove_category(client, name) -> None` — `LookupError` si no existe,
    `PermissionDeniedError` si no es del creador.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_categories.py`:

```python
import pytest

from soundboard.remote import categories
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.fake_client import FakeRemoteClient


def test_add_category_is_owned_by_the_creator() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")

    category = categories.add_category(client, session, "memes")

    assert category.name == "memes"
    assert category.created_by == session.user_id


def test_add_category_is_idempotent_by_name() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")

    first = categories.add_category(client, session, "memes")
    second = categories.add_category(client, session, "memes")

    assert first.id == second.id
    assert len(client.select("categories", filters=None)) == 1


def test_list_categories_returns_every_category() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    categories.add_category(client, session, "memes")
    categories.add_category(client, session, "reactions")

    names = {c.name for c in categories.list_categories(client)}

    assert names == {"memes", "reactions"}


def test_remove_category_by_the_creator_succeeds() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    categories.add_category(client, session, "memes")

    categories.remove_category(client, "memes")

    assert categories.list_categories(client) == []


def test_remove_category_by_a_stranger_is_denied() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    categories.add_category(client, session, "memes")
    client.sign_in_as_new_user("stranger@x.com")

    with pytest.raises(PermissionDeniedError):
        categories.remove_category(client, "memes")


def test_remove_category_raises_lookup_error_when_missing() -> None:
    client = FakeRemoteClient()
    client.sign_in_as_new_user("a@x.com")

    with pytest.raises(LookupError):
        categories.remove_category(client, "nonexistent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_categories.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.remote.categories'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/remote/categories.py`:

```python
"""CRUD for the shared category taxonomy."""

from __future__ import annotations

from typing import Any

from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.models import Category, RemoteClient, Session


def _row_to_category(row: dict[str, Any]) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        color=row.get("color"),
        position=row.get("position", 0),
        created_by=row["created_by"],
    )


def add_category(
    client: RemoteClient, session: Session, name: str, color: str | None = None
) -> Category:
    existing = client.select("categories", filters={"name": name})
    if existing:
        return _row_to_category(existing[0])
    row = client.insert(
        "categories", {"name": name, "color": color, "position": 0, "created_by": session.user_id}
    )
    return _row_to_category(row)


def list_categories(client: RemoteClient) -> list[Category]:
    return [_row_to_category(row) for row in client.select("categories", filters=None)]


def remove_category(client: RemoteClient, name: str) -> None:
    rows = client.select("categories", filters={"name": name})
    if not rows:
        raise LookupError(f"no category named {name!r}")
    affected = client.delete("categories", rows[0]["id"])
    if affected == 0:
        raise PermissionDeniedError(f"cannot delete category {name!r}: not yours")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_categories.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/remote/categories.py tests/unit/test_categories.py
git commit -m "feat(remote): add category CRUD with creator-checked delete"
```

---

### Task 10: Wiring de la CLI

**Files:**
- Modify: `src/soundboard/cli.py`
- Test: `tests/unit/test_cli.py` (extiende el existente)

**Interfaces:**
- Consumes: todo lo de las Tasks 4–9 (`RemoteClient`, `Session`, `SessionStore`,
  `build_client`, `auth.*`, `sounds.*`, `categories.*`, `SoundCache`).
- Produces: subcomandos `auth signup|login|logout|whoami`, `sounds
  add|list|edit|rm`, `categories add|list|rm`; `run --sound` acepta además de una ruta
  local un id o nombre remoto.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_cli.py` (mantener los tests existentes tal cual):

```python
from soundboard.library.cache import SoundCache
from soundboard.remote import auth, categories, sounds
from soundboard.remote.client import SessionStore
from soundboard.remote.fake_client import FakeRemoteClient


class _DictKeyringBackend:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


def test_auth_signup_and_login_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    from soundboard.cli import _auth, build_parser

    client = FakeRemoteClient()
    store = SessionStore(backend=_DictKeyringBackend())

    signup_args = build_parser().parse_args(["auth", "signup", "--email", "a@x.com"])
    exit_code = _auth(signup_args, client=client, store=store, password_prompt=lambda: "hunter2")
    assert exit_code == 0

    login_args = build_parser().parse_args(["auth", "login", "--email", "a@x.com"])
    exit_code = _auth(
        login_args,
        client=client,
        store=store,
        password_prompt=lambda: "hunter2",
        display_name_prompt=lambda: "Pablo",
    )
    assert exit_code == 0
    assert store.load() is not None

    whoami_args = build_parser().parse_args(["auth", "whoami"])
    exit_code = _auth(whoami_args, client=client, store=store)
    assert exit_code == 0
    assert "a@x.com" in capsys.readouterr().out


def test_auth_whoami_without_a_session_reports_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from soundboard.cli import _auth, build_parser

    args = build_parser().parse_args(["auth", "whoami"])
    exit_code = _auth(args, client=FakeRemoteClient(), store=SessionStore(backend=_DictKeyringBackend()))

    assert exit_code == 1
    assert "auth login" in capsys.readouterr().err


def test_sounds_add_list_edit_rm_subcommands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from soundboard.cli import _sounds, build_parser

    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(480, 0.3, dtype=np.float32), 48_000)

    add_args = build_parser().parse_args(["sounds", "add", str(clip), "--name", "laugh"])
    assert _sounds(add_args, client=client, store=store) == 0

    added = sounds.list_sounds(client)[0]

    list_args = build_parser().parse_args(["sounds", "list"])
    assert _sounds(list_args, client=client, store=store) == 0
    assert "laugh" in capsys.readouterr().out

    edit_args = build_parser().parse_args(
        ["sounds", "edit", added.id, "--name", "renamed"]
    )
    assert _sounds(edit_args, client=client, store=store) == 0
    assert sounds.get_sound(client, added.id).name == "renamed"

    rm_args = build_parser().parse_args(["sounds", "rm", added.id])
    assert _sounds(rm_args, client=client, store=store) == 0
    assert sounds.list_sounds(client) == []


def test_sounds_edit_by_a_stranger_reports_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from soundboard.cli import _sounds, build_parser

    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)
    added = sounds.add_sound(client, owner, str(clip), name="laugh")

    stranger = client.sign_in_as_new_user("stranger@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(stranger)

    edit_args = build_parser().parse_args(["sounds", "edit", added.id, "--name", "hijacked"])
    exit_code = _sounds(edit_args, client=client, store=store)

    assert exit_code == 1
    assert "not" in capsys.readouterr().err.lower()


def test_categories_add_list_rm_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    from soundboard.cli import _categories, build_parser

    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    store = SessionStore(backend=_DictKeyringBackend())
    store.save(session)

    add_args = build_parser().parse_args(["categories", "add", "memes"])
    assert _categories(add_args, client=client, store=store) == 0

    list_args = build_parser().parse_args(["categories", "list"])
    assert _categories(list_args, client=client, store=store) == 0
    assert "memes" in capsys.readouterr().out

    rm_args = build_parser().parse_args(["categories", "rm", "memes"])
    assert _categories(rm_args, client=client, store=store) == 0
    assert categories.list_categories(client) == []


def test_run_sound_resolves_a_remote_id_when_no_local_file_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from soundboard.cli import _run, build_parser

    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.full(64 * 50, 0.5, dtype=np.float32), 48_000)
    added = sounds.add_sound(client, session, str(clip), name="laugh")

    backend = FakeBackend()
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)
    args = build_parser().parse_args(
        [
            "run",
            "--mic",
            "microphone",
            "--out",
            "cable",
            "--sound",
            f"a={added.id}",
            "--blocksize",
            "64",
        ]
    )
    monkeypatch.setattr("sys.stdin", _AdvancingStdin(["a", "stop", "quit"], backend, 5))

    exit_code = _run(args, backend, remote_client=client, cache=SoundCache(tmp_path / "cache"))

    assert exit_code == 0
    assert np.max(backend.captured[9]) > 0.4
```

Añadir los imports que falten al principio del fichero (`from pathlib import Path` ya
está; agregar los de arriba junto a los existentes).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_cli.py -v`
Expected: FAIL — `_auth`, `_sounds`, `_categories` no existen todavía, y `_run` no
acepta `remote_client`/`cache`.

- [ ] **Step 3: Extend the CLI**

Reemplazar el contenido de `src/soundboard/cli.py` por:

```python
"""Command line: device listing, engine control, and the Supabase sound library."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import platformdirs
import sounddevice as sd
import soundfile as sf

from soundboard.audio.backend import AudioBackend
from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.portaudio import PortAudioBackend, find_device
from soundboard.audioio import load_mono_48k
from soundboard.library.cache import SoundCache
from soundboard.remote import auth, categories, sounds
from soundboard.remote.client import SessionStore, build_client
from soundboard.remote.models import RemoteClient


def parse_sound_argument(value: str) -> tuple[str, str]:
    """Split a ``KEY=PATH`` assignment."""
    key, separator, path = value.partition("=")
    if not separator or not key or not path:
        raise ValueError(f"expected KEY=PATH, got {value!r}")
    return key, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="soundboard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="list the audio devices PortAudio can see")

    run = subparsers.add_parser("run", help="run the engine and trigger clips from stdin")
    run.add_argument("--mic", required=True, help="substring of the physical microphone name")
    run.add_argument("--out", required=True, help="substring of the virtual cable input name")
    run.add_argument(
        "--sound", action="append", default=[], metavar="KEY=PATH-OR-ID-OR-NAME"
    )
    run.add_argument("--blocksize", type=int, default=256)

    auth_parser = subparsers.add_parser("auth", help="manage your Supabase session")
    auth_sub = auth_parser.add_subparsers(dest="auth_command", required=True)
    signup = auth_sub.add_parser("signup")
    signup.add_argument("--email", required=True)
    login = auth_sub.add_parser("login")
    login.add_argument("--email", required=True)
    auth_sub.add_parser("logout")
    auth_sub.add_parser("whoami")

    sounds_parser = subparsers.add_parser("sounds", help="manage the shared sound library")
    sounds_sub = sounds_parser.add_subparsers(dest="sounds_command", required=True)
    add = sounds_sub.add_parser("add")
    add.add_argument("path")
    add.add_argument("--name", required=True)
    add.add_argument("--category")
    listing = sounds_sub.add_parser("list")
    listing.add_argument("--mine", action="store_true")
    listing.add_argument("--category")
    edit = sounds_sub.add_parser("edit")
    edit.add_argument("id")
    edit.add_argument("--name")
    edit.add_argument("--category")
    edit.add_argument("--gain-db", type=float)
    edit.add_argument("--trim-start", type=int)
    edit.add_argument("--trim-end", type=int)
    edit.add_argument("--loop", dest="loop", action="store_true")
    edit.add_argument("--no-loop", dest="loop", action="store_false")
    edit.set_defaults(loop=None)
    rm = sounds_sub.add_parser("rm")
    rm.add_argument("id")

    categories_parser = subparsers.add_parser("categories", help="manage shared categories")
    categories_sub = categories_parser.add_subparsers(dest="categories_command", required=True)
    cat_add = categories_sub.add_parser("add")
    cat_add.add_argument("name")
    cat_add.add_argument("--color")
    categories_sub.add_parser("list")
    cat_rm = categories_sub.add_parser("rm")
    cat_rm.add_argument("name")

    return parser


def _print_devices(backend: PortAudioBackend) -> int:
    for device in backend.list_devices():
        direction = []
        if device.max_input_channels:
            direction.append("in")
        if device.max_output_channels:
            direction.append("out")
        print(
            f"{device.index:3d}  {'/'.join(direction):7s}  [{device.hostapi}]  "
            f"{device.default_samplerate:.0f}Hz  {device.name}"
        )
    return 0


def _resolve_sound_pcm(
    value: str, remote_client: RemoteClient | None, cache: SoundCache | None
) -> np.ndarray:
    if Path(value).exists():
        return load_mono_48k(value)

    client = remote_client if remote_client is not None else build_client()
    active_cache = cache if cache is not None else SoundCache(_default_cache_dir())
    sound = sounds.find_sound_by_name(client, value)
    if sound is None:
        sound = sounds.get_sound(client, value)
    return sounds.resolve_pcm(client, active_cache, sound)


def _default_cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("soundboard")) / "pcm"


def _run(
    args: argparse.Namespace,
    backend: AudioBackend | None = None,
    remote_client: RemoteClient | None = None,
    cache: SoundCache | None = None,
) -> int:
    if backend is None:
        backend = PortAudioBackend()

    try:
        devices = backend.list_devices()
        microphone = find_device(devices, args.mic, want_input=True)
        cable = find_device(devices, args.out, want_input=False)

        clips = {}
        for assignment in args.sound:
            key, value = parse_sound_argument(assignment)
            clips[key] = _resolve_sound_pcm(value, remote_client, cache)

        engine = AudioEngine(
            backend,
            EngineConfig(
                blocksize=args.blocksize,
                input_device=microphone.index,
                output_device=cable.index,
                output_channels=min(2, cable.max_output_channels) or 1,
            ),
        )
        engine.start()
    except Exception as exc:  # CLI boundary: report cleanly, see _auth
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"microphone: {microphone.name}")
    print(f"output:     {cable.name}")
    print(f"keys:       {', '.join(sorted(clips)) or '(none)'}")
    print("type a key and press enter to play it; 'stop' to stop all; 'quit' to exit")

    try:
        for line in sys.stdin:
            command = line.strip()
            if command == "quit":
                break
            if command == "stop":
                engine.stop_all()
            elif command in clips:
                engine.play(clips[command])
            elif command:
                metrics = engine.metrics
                print(f"unknown key {command!r} | {metrics} | xruns={backend.xruns}")
    finally:
        engine.stop()
    return 0


def _auth(
    args: argparse.Namespace,
    client: RemoteClient | None = None,
    store: SessionStore | None = None,
    password_prompt: Callable[[], str] | None = None,
    display_name_prompt: Callable[[], str] | None = None,
) -> int:
    client = client if client is not None else build_client()
    store = store if store is not None else SessionStore()
    password_prompt = password_prompt or (lambda: getpass.getpass("password: "))
    display_name_prompt = display_name_prompt or (lambda: input("display name: "))

    try:
        if args.auth_command == "signup":
            auth.sign_up(client, args.email, password_prompt())
            print(f"signed up as {args.email}; check your email to confirm before logging in")
        elif args.auth_command == "login":
            session = auth.log_in(
                client, store, args.email, password_prompt(), display_name_prompt
            )
            print(f"logged in as {session.email}")
        elif args.auth_command == "logout":
            auth.log_out(client, store)
            print("logged out")
        elif args.auth_command == "whoami":
            session = store.load()
            if session is None:
                print("error: no session; run `soundboard auth login`", file=sys.stderr)
                return 1
            print(session.email)
        return 0
    except Exception as exc:  # CLI boundary: always report, never crash silently
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _sounds(
    args: argparse.Namespace, client: RemoteClient | None = None, store: SessionStore | None = None
) -> int:
    client = client if client is not None else build_client()
    store = store if store is not None else SessionStore()
    cache = SoundCache(_default_cache_dir())

    try:
        if args.sounds_command == "add":
            session = auth.require_session(client, store)
            category_id = None
            if args.category:
                category_id = categories.add_category(client, session, args.category).id
            sound = sounds.add_sound(client, session, args.path, name=args.name, category_id=category_id)
            print(f"added {sound.name!r} ({sound.id})")
        elif args.sounds_command == "list":
            session = auth.require_session(client, store)
            owner_id = session.user_id if args.mine else None
            category_id = None
            if args.category:
                matches = [c for c in categories.list_categories(client) if c.name == args.category]
                category_id = matches[0].id if matches else "__none__"
            names = auth.display_names(client, [s.owner_id for s in sounds.list_sounds(client)])
            for sound in sounds.list_sounds(client, owner_id=owner_id, category_id=category_id):
                owner_name = names.get(sound.owner_id, sound.owner_id)
                print(f"{sound.id}  {sound.name!r}  by {owner_name}")
        elif args.sounds_command == "edit":
            session = auth.require_session(client, store)
            fields: dict[str, object] = {}
            if args.name is not None:
                fields["name"] = args.name
            if args.gain_db is not None:
                fields["gain_db"] = args.gain_db
            if args.trim_start is not None:
                fields["trim_start_frames"] = args.trim_start
            if args.trim_end is not None:
                fields["trim_end_frames"] = args.trim_end
            if args.loop is not None:
                fields["loop"] = args.loop
            if args.category is not None:
                fields["category_id"] = categories.add_category(client, session, args.category).id
            sound = sounds.edit_sound(client, args.id, **fields)
            print(f"updated {sound.name!r}")
        elif args.sounds_command == "rm":
            auth.require_session(client, store)
            sounds.remove_sound(client, args.id)
            print("removed")
        return 0
    except Exception as exc:  # CLI boundary: report cleanly, see _auth
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _categories(
    args: argparse.Namespace, client: RemoteClient | None = None, store: SessionStore | None = None
) -> int:
    client = client if client is not None else build_client()
    store = store if store is not None else SessionStore()

    try:
        if args.categories_command == "add":
            session = auth.require_session(client, store)
            category = categories.add_category(client, session, args.name, color=args.color)
            print(f"added {category.name!r} ({category.id})")
        elif args.categories_command == "list":
            auth.require_session(client, store)
            for category in categories.list_categories(client):
                print(f"{category.id}  {category.name}")
        elif args.categories_command == "rm":
            auth.require_session(client, store)
            categories.remove_category(client, args.name)
            print("removed")
        return 0
    except Exception as exc:  # CLI boundary: report cleanly, see _auth
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "devices":
        return _print_devices(PortAudioBackend())
    if args.command == "run":
        return _run(args)
    if args.command == "auth":
        return _auth(args)
    if args.command == "sounds":
        return _sounds(args)
    if args.command == "categories":
        return _categories(args)
    raise AssertionError(f"unhandled command {args.command!r}")  # argparse guarantees a match
```

**Notas de implementación:**
- `_resolve_sound_pcm` importa `numpy` de forma perezosa solo para el *type hint* en el
  cuerpo (evita un import de módulo a nivel de fichero que ningún otro símbolo usa
  fuera de esa función); es la única función nueva que lo necesita.
- `_sounds` con `list --category` cuando la categoría no existe usa el sentinel
  `"__none__"` para que el filtro no devuelva nada en vez de lanzar — listar con un
  filtro que no matchea ningún sonido es un resultado válido (lista vacía), no un
  error.
- El bloque `except Exception` en `_auth`, `_run`, `_sounds` y `_categories` es
  intencional y va contra la regla general de no silenciar fallos porque **no** los
  silencia: los imprime y devuelve código de salida 1, que es exactamente el
  comportamiento requerido por el manejo de errores de la spec (§10) para "sin red",
  "email sin confirmar", "RLS deniega", etc. — excepciones variadas del SDK de
  Supabase (o de `RemoteClient`/`sounds`/`categories`) que en el límite de la CLI deben
  convertirse en un mensaje de una línea, nunca en un traceback ni en un fallo que se
  cuela sin avisar. Por eso `NotAuthenticatedError` y `PermissionDeniedError` ya no
  necesitan un `except` propio en `_sounds`/`_categories`: el genérico las cubre igual
  que a cualquier otro error del cliente remoto.

- [ ] **Step 4: Run the tests and fix any import ordering (ruff) issues**

Run:
```
.venv\Scripts\pytest.exe tests/unit/test_cli.py -v
.venv\Scripts\ruff.exe check . --fix
```
Expected: todos los tests (existentes + nuevos) en verde tras el `--fix` de imports.

- [ ] **Step 5: Verify the full unit suite and types**

Run:
```
.venv\Scripts\pytest.exe tests/unit -v
.venv\Scripts\mypy.exe
```
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add auth/sounds/categories subcommands and remote --sound resolution"
```

---

### Task 11: Esquema SQL, RLS y tests de integración

**Files:**
- Create: `supabase/migrations/20260729000000_sounds_library.sql`,
  `tests/integration/conftest.py`, `tests/integration/test_rls.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `SupabaseRemoteClient` (Task 6), `auth.*`/`sounds.*`/`categories.*`
  (Tasks 7–9), un stack local de Supabase CLI corriendo en `localhost:54321`.
- Produces: esquema aplicado + políticas RLS reales; suite marcada `supabase` que
  prueba la denegación cruzada de owner con Postgres de verdad, no un mock.

- [ ] **Step 1: Write the SQL migration**

`supabase/migrations/20260729000000_sounds_library.sql`:

```sql
-- profiles: display name shown in shared listings instead of raw emails.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;

create policy "profiles are visible to authenticated users"
  on public.profiles for select to authenticated using (true);
create policy "users insert their own profile"
  on public.profiles for insert to authenticated with check (id = auth.uid());
create policy "users update their own profile"
  on public.profiles for update to authenticated using (id = auth.uid());

-- categories: global shared taxonomy, editable only by whoever created each one.
create table public.categories (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  color text,
  position int not null default 0,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);
alter table public.categories enable row level security;

create policy "categories are visible to authenticated users"
  on public.categories for select to authenticated using (true);
create policy "authenticated users create categories"
  on public.categories for insert to authenticated with check (created_by = auth.uid());
create policy "creators update their categories"
  on public.categories for update to authenticated using (created_by = auth.uid());
create policy "creators delete their categories"
  on public.categories for delete to authenticated using (created_by = auth.uid());

-- sounds: shared global library, editable only by the owner.
create table public.sounds (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  category_id uuid references public.categories(id) on delete set null,
  name text not null,
  sha256 text not null,
  storage_path text not null,
  source_filename text not null,
  duration_frames int not null,
  orig_samplerate int not null,
  orig_channels int not null,
  gain_db real not null default 0,
  trim_start_frames int not null default 0,
  trim_end_frames int,
  loop boolean not null default false,
  color text,
  tags text[],
  created_at timestamptz not null default now(),
  unique (owner_id, sha256)
);
alter table public.sounds enable row level security;

create policy "sounds are visible to authenticated users"
  on public.sounds for select to authenticated using (true);
create policy "owners insert their sounds"
  on public.sounds for insert to authenticated with check (owner_id = auth.uid());
create policy "owners update their sounds"
  on public.sounds for update to authenticated using (owner_id = auth.uid());
create policy "owners delete their sounds"
  on public.sounds for delete to authenticated using (owner_id = auth.uid());

-- storage: content-addressed PCM blobs, immutable once written.
insert into storage.buckets (id, name, public)
  values ('sounds', 'sounds', false)
  on conflict (id) do nothing;

create policy "authenticated read sound blobs"
  on storage.objects for select to authenticated
  using (bucket_id = 'sounds');
create policy "authenticated upload sound blobs"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'sounds');
```

- [ ] **Step 2: Initialize the local Supabase project (one-time, if not already done)**

Run:
```
supabase init
```
Si el proyecto ya tiene `supabase/config.toml`, saltar este paso — la migración del
Step 1 ya vive en la carpeta correcta (`supabase/migrations/`), que `supabase init`
crea si no existe.

- [ ] **Step 3: Write the integration fixture**

`tests/integration/conftest.py`:

```python
"""Fixtures for tests that need a real local Supabase stack (Docker)."""

import json
import subprocess
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def supabase_env() -> Iterator[dict[str, str]]:
    """Reads the running local stack's API URL and anon key.

    Skips (does not fail) when the Supabase CLI or Docker aren't available, so the
    normal test run — which never selects the ``supabase`` marker — is unaffected,
    and a manual ``pytest -m supabase`` run degrades to a clear skip instead of a
    confusing connection error.
    """
    try:
        result = subprocess.run(
            ["supabase", "status", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"local Supabase stack is not running: {exc}")

    status = json.loads(result.stdout)
    yield {"url": status["API_URL"], "anon_key": status["ANON_KEY"]}
```

- [ ] **Step 4: Write the RLS integration test**

`tests/integration/test_rls.py`:

```python
"""Proves RLS against a real local Postgres — FakeRemoteClient only simulates the
row-count contract these policies are supposed to produce; this is what checks the
SQL in the migration actually enforces it.
"""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import soundfile as sf

from soundboard.remote import categories, sounds
from soundboard.remote.client import SupabaseRemoteClient
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.models import Session

pytestmark = pytest.mark.supabase


def _fresh_user(env: dict[str, str]) -> tuple[SupabaseRemoteClient, Session]:
    email = f"{uuid4()}@example.com"
    client = SupabaseRemoteClient(env["url"], env["anon_key"])
    client.sign_up(email, "correct horse battery staple")
    session = client.sign_in(email, "correct horse battery staple")
    client.restore_session(session)
    return client, session


def test_owner_can_edit_but_a_stranger_cannot(
    supabase_env: dict[str, str], tmp_path: Path
) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)

    owner, owner_session = _fresh_user(supabase_env)
    stranger, _ = _fresh_user(supabase_env)

    sound = sounds.add_sound(owner, owner_session, str(clip), name="integration clip")

    edited = sounds.edit_sound(owner, sound.id, name="renamed by owner")
    assert edited.name == "renamed by owner"

    with pytest.raises(PermissionDeniedError):
        sounds.edit_sound(stranger, sound.id, name="hijacked")


def test_owner_can_delete_but_a_stranger_cannot(
    supabase_env: dict[str, str], tmp_path: Path
) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)

    owner, owner_session = _fresh_user(supabase_env)
    stranger, _ = _fresh_user(supabase_env)
    sound = sounds.add_sound(owner, owner_session, str(clip), name="integration clip")

    with pytest.raises(PermissionDeniedError):
        sounds.remove_sound(stranger, sound.id)

    sounds.remove_sound(owner, sound.id)  # the actual owner can still remove it


def test_category_deletion_is_restricted_to_its_creator(supabase_env: dict[str, str]) -> None:
    creator, creator_session = _fresh_user(supabase_env)
    stranger, _ = _fresh_user(supabase_env)
    category = categories.add_category(creator, creator_session, f"cat-{uuid4()}")

    with pytest.raises(PermissionDeniedError):
        categories.remove_category(stranger, category.name)

    categories.remove_category(creator, category.name)
```

- [ ] **Step 5: Run the RLS suite against a local stack**

Run:
```
supabase start
supabase db reset
.venv\Scripts\pytest.exe tests/integration/test_rls.py -m supabase -v
```
Expected: 3 passed contra el stack local. (Si `supabase` no está instalado, la
fixture hace `skip`, no `fail` — verificar ese comportamiento corriendo el mismo
comando con el stack detenido: debe reportar 3 skipped, no errores.)

- [ ] **Step 6: Add a dedicated CI job for the RLS suite**

En `.github/workflows/ci.yml`, añadir un job nuevo junto al `test` existente:

```yaml
  rls:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: supabase/setup-cli@v1
        with:
          version: latest
      - run: supabase start
      - run: uv sync --all-groups
      - run: uv run pytest tests/integration/test_rls.py -m supabase -v
      - run: supabase stop
```

- [ ] **Step 7: Commit**

`supabase init` (Step 2) generates `supabase/config.toml` (and, depending on CLI
version, `supabase/.gitignore` / `supabase/seed.sql`) — these must be committed too, or
`supabase start` has no project to read in a fresh clone (CI included).

```bash
git add supabase/ tests/integration/conftest.py tests/integration/test_rls.py .github/workflows/ci.yml
git status
```

Revisar la salida de `git status`: `supabase/.branches/` y `supabase/.temp/` (estado
local del CLI, no del proyecto) no deben quedar *staged* — si `supabase init` no trae
ya un `.gitignore` que los excluya, añadirlos a mano al `.gitignore` del repo antes de
commitear.

```bash
git commit -m "feat(db): add sounds/categories/profiles schema with RLS and integration tests"
```

---

### Task 12: Documentación en el README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nada (solo documentación).
- Produces: sección nueva describiendo configuración de Supabase y los comandos de
  `auth`/`sounds`/`categories`.

- [ ] **Step 1: Insert a new section after "## Uso" and before "## Arquitectura"**

Localizar en `README.md` el final de la sección `## Uso` (justo antes de la línea
`## Arquitectura`) e insertar:

```markdown
## Biblioteca de sonidos (Supabase)

La biblioteca es compartida entre usuarios: cualquiera autenticado puede añadir
sonidos y verlos todos, pero solo puede editar o borrar los suyos.

### Configuración

Definí estas variables de entorno (o agregalas a `<config>/soundboard/settings.json`
bajo la clave `"supabase": {"url": ..., "anon_key": ...}`):

```bash
export SOUNDBOARD_SUPABASE_URL="https://tu-proyecto.supabase.co"
export SOUNDBOARD_SUPABASE_ANON_KEY="tu-anon-key"
```

El anon key es público por diseño de Supabase — la protección la da RLS (Row Level
Security), no el secreto del key.

### Cuenta

```bash
uv run soundboard auth signup --email vos@ejemplo.com
uv run soundboard auth login --email vos@ejemplo.com
uv run soundboard auth whoami
uv run soundboard auth logout
```

La sesión se guarda en el almacén de credenciales del sistema operativo — no hace
falta volver a loguearse en cada ejecución.

### Sonidos y categorías

```bash
uv run soundboard categories add memes
uv run soundboard sounds add clips/airhorn.wav --name airhorn --category memes
uv run soundboard sounds list
uv run soundboard sounds list --mine
uv run soundboard sounds edit <id> --gain-db -3 --loop
uv run soundboard sounds rm <id>
```

### Reproducir sonidos de la biblioteca

`--sound` acepta, además de una ruta local (como en la fase 1), un id o nombre de la
biblioteca compartida:

```bash
uv run soundboard run --mic "..." --out "CABLE Input" --sound applause=<id-o-nombre>
```

Al reproducir por primera vez se descarga y cachea en disco; las siguientes veces se
usa la copia local.
```

- [ ] **Step 2: Update the "## Desarrollo" section to mention the RLS suite**

Después del bloque de comandos existente en `## Desarrollo` (`uv run pytest` / `ruff
check` / `mypy`), añadir:

```markdown
Los tests de RLS (`tests/integration/test_rls.py`) necesitan un stack local de
Supabase y están excluidos por defecto (marcador `supabase`, igual que `hardware`):

```bash
supabase start
uv run pytest -m supabase
```

Requiere [Supabase CLI](https://supabase.com/docs/guides/cli) y Docker.
```

- [ ] **Step 3: Update the roadmap line for the sound library**

Reemplazar la línea del roadmap que ya apunta al spec (añadida durante el
brainstorming) para que en vez de solo enlazar al diseño, resuma también el estado:

```markdown
- **Biblioteca de sonidos**: ✅ diseñada e implementada — multiusuario sobre Supabase
  (Postgres + Storage + Auth), caché local de reproducción, CRUD con RLS por dueño.
  Ver [`docs/superpowers/specs/2026-07-29-supabase-sounds-design.md`](docs/superpowers/specs/2026-07-29-supabase-sounds-design.md).
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the Supabase sound library setup and CLI commands"
```

---

## Verificación final

- [ ] `.venv\Scripts\pytest.exe -v` (suite completa por defecto: excluye `hardware` y
  `supabase`) — todo en verde.
- [ ] `.venv\Scripts\ruff.exe check .` — sin errores.
- [ ] `.venv\Scripts\mypy.exe` — sin errores.
- [ ] `supabase start && .venv\Scripts\pytest.exe -m supabase -v` — 3 passed (Task 11).
- [ ] Prueba manual con dos cuentas reales: signup, confirmación de email, login en dos
  máquinas (o dos perfiles de `keyring`), `sounds add` desde una cuenta, `sounds edit`
  desde la otra cuenta debe fallar con "no tenés permiso, no es tuyo", `run --sound
  <id>` reproduce el sonido de la primera cuenta desde la segunda.
