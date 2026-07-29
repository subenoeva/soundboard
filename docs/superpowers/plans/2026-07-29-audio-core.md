# Núcleo de audio — Plan de implementación (fases 0–1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el motor de audio completo — captura del micrófono, mezcla de clips,
compensación de deriva de reloj y salida a un dispositivo virtual — con una CLI de prueba,
de modo que en Discord se oiga la voz del usuario **y** los sonidos disparados, sin interfaz
gráfica todavía.

**Architecture:** Dos streams PortAudio independientes unidos por un ring buffer SPSC. El
callback de entrada escribe el micrófono; el de salida lee con posición fraccionaria
(compensando la deriva entre los relojes de ambos dispositivos), mezcla las voces activas,
aplica *ducking* y limitador, y escribe al cable virtual. `sounddevice` queda tras el
protocolo `AudioBackend`, con un `FakeBackend` de reloj simulado que permite ejecutar el
motor entero en CI sin tarjeta de sonido.

**Tech Stack:** Python 3.13, numpy 2.5, sounddevice 0.5.5 (PortAudio), soundfile 0.14,
soxr 1.1, pytest, ruff, mypy. Gestión de entorno con `uv`.

**Spec:** `docs/superpowers/specs/2026-07-29-soundboard-design.md`

**Planes posteriores:** fase 2 (biblioteca SQLite + importador multiformato), fases 3–4
(UI PySide6 + enrutado y asistente), fases 5–6 (atajos globales, categorías, editor,
perfiles), fase 7 (efectos), fase 8 (empaquetado). Cada uno se escribe cuando el anterior
esté cerrado.

## Global Constraints

- Python `>=3.13`. Todas las dependencias binarias publican wheels abi3 o cp313.
- Frecuencia de muestreo interna fija: **48000 Hz**. Nunca se parametriza fuera de `EngineConfig`.
- Formato interno: **mono**, `numpy.float32`, arrays unidimensionales de forma `(frames,)`.
  Los buffers de salida hacia el backend son `(frames, channels)`.
- Tamaño de bloque por defecto: **256 frames**. Configurable vía `EngineConfig.blocksize`.
- Techo del limitador: **−1 dBFS**, es decir `10 ** (-1/20) == 0.8912509…`.
- Ningún módulo bajo `src/soundboard/audio/` puede importar PySide6, sqlite3 ni hacer E/S.
- Dentro de un callback de audio: prohibido E/S, `logging`, `queue.Queue` y decodificación.
  Las reservas de memoria se minimizan usando arrays preasignados; las pocas que quedan
  (`np.interp`, filtrado de la lista de voces) se documentan con comentario en el código.
- Límite de tamaño: si un fichero supera ~300 líneas, dividirlo.
- Código, identificadores, docstrings y mensajes de commit en **inglés**. Documentación de
  producto y specs en **español**.
- Comandos: en esta máquina `uv` está en
  `C:\Users\k\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`
  hasta que se reinicie la terminal. Tras `uv sync` se puede usar `.venv\Scripts\pytest.exe`
  directamente, que es lo que asumen los pasos de este plan.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `pyproject.toml` | Metadatos, dependencias, configuración de ruff/mypy/pytest |
| `src/soundboard/__init__.py` | Versión del paquete |
| `src/soundboard/audio/ringbuffer.py` | Cola SPSC de frames `float32` |
| `src/soundboard/audio/drift.py` | `DriftController` (lazo de control) y `DriftResampler` (lectura fraccionaria) |
| `src/soundboard/audio/backend.py` | `DeviceInfo`, protocolos `Stream` y `AudioBackend` |
| `src/soundboard/audio/fake_backend.py` | Backend en memoria con reloj simulado, para pruebas |
| `src/soundboard/audio/voice.py` | Una reproducción en curso: posición, ganancia, bucle, recorte |
| `src/soundboard/audio/mixer.py` | Suma de voces, *ducking*, limitador |
| `src/soundboard/audio/engine.py` | Orquestación de streams, cola de comandos, métricas |
| `src/soundboard/audio/portaudio.py` | Backend real sobre `sounddevice` |
| `src/soundboard/cli.py` | CLI de prueba: listar dispositivos y ejecutar el motor |
| `src/soundboard/__main__.py` | Punto de entrada |
| `.github/workflows/ci.yml` | CI en Windows y Linux |

---

### Task 1: Andamiaje del proyecto

**Files:**
- Create: `pyproject.toml`, `.python-version`, `src/soundboard/__init__.py`,
  `src/soundboard/audio/__init__.py`, `.github/workflows/ci.yml`
- Test: `tests/unit/test_package.py`

**Interfaces:**
- Consumes: nada.
- Produces: paquete importable `soundboard` con `__version__: str`. Entorno virtual en
  `.venv/` con todas las dependencias del stack.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_package.py`:

```python
def test_package_exposes_version() -> None:
    import soundboard

    assert soundboard.__version__ == "0.1.0"


def test_audio_subpackage_is_importable() -> None:
    import soundboard.audio  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_package.py -v`
Expected: FAIL — no existe `.venv` todavía, ni el paquete.

- [ ] **Step 3: Write the project files**

`pyproject.toml`:

```toml
[project]
name = "soundboard"
version = "0.1.0"
description = "Cross-platform soundboard that feeds clips and your microphone into a virtual input device"
requires-python = ">=3.13"
dependencies = [
    "numpy>=2.5.1",
    "sounddevice>=0.5.5",
    "soundfile>=0.14.0",
    "soxr>=1.1.0",
    "platformdirs>=4.11.0",
]

[project.scripts]
soundboard = "soundboard.__main__:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "mypy>=1.11",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/soundboard"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not hardware'"
markers = [
    "hardware: requires a real audio device; deselected by default",
]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.13"
strict = true
files = ["src", "tests"]

[[tool.mypy.overrides]]
module = ["sounddevice.*", "soxr.*", "soundfile.*"]
ignore_missing_imports = true
```

`.python-version`:

```
3.13
```

`src/soundboard/__init__.py`:

```python
"""Cross-platform soundboard."""

__version__ = "0.1.0"
```

`src/soundboard/audio/__init__.py`:

```python
"""Real-time audio engine."""
```

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
      - name: Install PortAudio (Linux)
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libportaudio2
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-groups
      - run: uv run ruff check .
      - run: uv run mypy
      - run: uv run pytest -v
```

- [ ] **Step 4: Create the environment and run the tests**

Run:
```
"C:\Users\k\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe" sync --all-groups
.venv\Scripts\pytest.exe tests/unit/test_package.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .python-version src tests .github
git commit -m "chore: scaffold project with uv, ruff, mypy and pytest"
```

---

### Task 2: RingBuffer

**Files:**
- Create: `src/soundboard/audio/ringbuffer.py`
- Test: `tests/unit/test_ringbuffer.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `RingBuffer(capacity: int)` — `capacity` en frames, uno se reserva para distinguir
    lleno de vacío.
  - `RingBuffer.capacity -> int` (frames utilizables)
  - `RingBuffer.fill -> int` (frames pendientes de leer)
  - `RingBuffer.write(data: np.ndarray) -> None` — solo hilo productor. En desbordamiento
    descarta los frames **más antiguos** e incrementa `overruns`.
  - `RingBuffer.read(out: np.ndarray) -> int` — solo hilo consumidor. Rellena `out` con
    ceros si faltan datos e incrementa `underruns`. Devuelve frames reales leídos.
  - `RingBuffer.overruns: int`, `RingBuffer.underruns: int`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ringbuffer.py`:

```python
import numpy as np
import pytest

from soundboard.audio.ringbuffer import RingBuffer


def test_roundtrip_returns_written_frames() -> None:
    rb = RingBuffer(16)
    rb.write(np.arange(4, dtype=np.float32))
    out = np.zeros(4, dtype=np.float32)

    assert rb.read(out) == 4
    assert np.array_equal(out, np.arange(4, dtype=np.float32))
    assert rb.fill == 0


def test_fill_reports_pending_frames() -> None:
    rb = RingBuffer(16)
    rb.write(np.ones(5, dtype=np.float32))

    assert rb.fill == 5


def test_wraparound_preserves_order() -> None:
    rb = RingBuffer(8)  # 7 usable frames
    scratch = np.zeros(5, dtype=np.float32)
    rb.write(np.arange(5, dtype=np.float32))
    rb.read(scratch)
    rb.write(np.arange(5, 10, dtype=np.float32))

    assert rb.read(scratch) == 5
    assert np.array_equal(scratch, np.arange(5, 10, dtype=np.float32))


def test_underflow_zero_pads_and_counts() -> None:
    rb = RingBuffer(16)
    rb.write(np.ones(2, dtype=np.float32))
    out = np.full(5, 9.0, dtype=np.float32)

    assert rb.read(out) == 2
    assert np.array_equal(out, np.array([1, 1, 0, 0, 0], dtype=np.float32))
    assert rb.underruns == 1


def test_overflow_drops_oldest_and_counts() -> None:
    rb = RingBuffer(6)  # 5 usable frames
    rb.write(np.arange(5, dtype=np.float32))
    rb.write(np.array([100.0, 200.0], dtype=np.float32))
    out = np.zeros(5, dtype=np.float32)
    rb.read(out)

    assert np.array_equal(out, np.array([2, 3, 4, 100, 200], dtype=np.float32))
    assert rb.overruns == 1


def test_write_longer_than_capacity_keeps_the_tail() -> None:
    rb = RingBuffer(6)
    rb.write(np.arange(20, dtype=np.float32))
    out = np.zeros(5, dtype=np.float32)
    rb.read(out)

    assert np.array_equal(out, np.arange(15, 20, dtype=np.float32))


def test_rejects_tiny_capacity() -> None:
    with pytest.raises(ValueError):
        RingBuffer(1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_ringbuffer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.ringbuffer'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/audio/ringbuffer.py`:

```python
"""Single-producer / single-consumer ring buffer for mono float32 frames."""

from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Fixed-capacity FIFO of mono ``float32`` frames.

    One thread writes and one thread reads. Only the index updates run inside the
    lock; the sample copies happen outside it, so a slow ``memcpy`` never blocks
    the other side. A single slot is kept free so that a full buffer is
    distinguishable from an empty one.
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 2:
            raise ValueError("capacity must be at least 2 frames")
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._size = capacity
        self._read = 0
        self._write = 0
        self._lock = threading.Lock()
        self.overruns = 0
        self.underruns = 0

    @property
    def capacity(self) -> int:
        """Usable capacity in frames."""
        return self._size - 1

    @property
    def fill(self) -> int:
        """Frames written but not yet read."""
        with self._lock:
            return (self._write - self._read) % self._size

    def write(self, data: np.ndarray) -> None:
        """Append frames. Producer thread only.

        On overflow the oldest frames are dropped: keeping latency bounded matters
        more than preserving samples the consumer has already fallen behind on.
        """
        if data.shape[0] > self.capacity:
            data = data[-self.capacity :]
        n = data.shape[0]
        if n == 0:
            return

        with self._lock:
            free = self.capacity - (self._write - self._read) % self._size
            if n > free:
                self._read = (self._read + (n - free)) % self._size
                self.overruns += 1
            start = self._write

        end = start + n
        if end <= self._size:
            self._buf[start:end] = data
        else:
            split = self._size - start
            self._buf[start:] = data[:split]
            self._buf[: end - self._size] = data[split:]

        with self._lock:
            self._write = end % self._size

    def read(self, out: np.ndarray) -> int:
        """Fill ``out`` with the oldest frames. Consumer thread only.

        Returns the number of real frames read. Any shortfall is zero-filled and
        counted as an underrun.
        """
        n = out.shape[0]
        with self._lock:
            available = (self._write - self._read) % self._size
            start = self._read

        take = min(n, available)
        end = start + take
        if end <= self._size:
            out[:take] = self._buf[start:end]
        else:
            split = self._size - start
            out[:split] = self._buf[start:]
            out[split:take] = self._buf[: end - self._size]

        if take < n:
            out[take:] = 0.0
            self.underruns += 1

        with self._lock:
            self._read = end % self._size
        return take
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_ringbuffer.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/ringbuffer.py tests/unit/test_ringbuffer.py
git commit -m "feat(audio): add SPSC ring buffer with overrun and underrun accounting"
```

---

### Task 3: DriftController y DriftResampler

**Files:**
- Create: `src/soundboard/audio/drift.py`
- Test: `tests/unit/test_drift.py`

**Interfaces:**
- Consumes: `RingBuffer` de la Task 2.
- Produces:
  - `DriftController(target_fill: int, alpha: float = 0.005, gain: float = 0.05,
    max_deviation: float = 0.005)`
  - `DriftController.update(fill: int) -> float` — devuelve el ratio de lectura, definido
    como frames de entrada consumidos por frame de salida producido. `>1` cuando el buffer
    se acumula. Saturado a `1 ± max_deviation`.
  - `DriftController.ema_fill -> float`
  - `DriftResampler(source: RingBuffer, max_block: int)`
  - `DriftResampler.read(out: np.ndarray, ratio: float) -> None` — rellena `out` leyendo de
    `source` con posición fraccionaria e interpolación lineal, conservando la fase entre
    bloques.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_drift.py`:

```python
import numpy as np

from soundboard.audio.drift import DriftController, DriftResampler
from soundboard.audio.ringbuffer import RingBuffer


def test_ratio_is_one_at_target_fill() -> None:
    controller = DriftController(target_fill=512)

    assert controller.update(512) == 1.0


def test_ratio_rises_when_buffer_accumulates() -> None:
    controller = DriftController(target_fill=512)
    ratio = 1.0
    for _ in range(2000):
        ratio = controller.update(1024)

    assert ratio > 1.0
    assert ratio <= 1.005


def test_ratio_falls_when_buffer_drains() -> None:
    controller = DriftController(target_fill=512)
    ratio = 1.0
    for _ in range(2000):
        ratio = controller.update(0)

    assert ratio < 1.0
    assert ratio >= 0.995


def test_ema_converges_towards_observed_fill() -> None:
    controller = DriftController(target_fill=512)
    for _ in range(5000):
        controller.update(700)

    assert abs(controller.ema_fill - 700) < 1.0


def test_resampler_at_ratio_one_is_passthrough() -> None:
    rb = RingBuffer(1024)
    source = np.arange(64, dtype=np.float32)
    rb.write(source)
    resampler = DriftResampler(rb, max_block=32)
    out = np.zeros(32, dtype=np.float32)

    resampler.read(out, 1.0)

    assert np.allclose(out, source[:32], atol=1e-5)


def test_resampler_above_one_consumes_more_input_than_it_emits() -> None:
    rb = RingBuffer(8192)
    rb.write(np.zeros(4096, dtype=np.float32))
    resampler = DriftResampler(rb, max_block=256)
    out = np.zeros(256, dtype=np.float32)
    before = rb.fill

    for _ in range(8):
        resampler.read(out, 1.004)

    consumed = before - rb.fill
    assert consumed > 8 * 256


def test_resampler_keeps_a_sine_continuous_across_blocks() -> None:
    samplerate = 48_000
    frames = 48_000
    t = np.arange(frames, dtype=np.float64) / samplerate
    sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    rb = RingBuffer(frames + 16)
    rb.write(sine)
    resampler = DriftResampler(rb, max_block=256)

    blocks = []
    out = np.zeros(256, dtype=np.float32)
    for _ in range(160):
        resampler.read(out, 1.001)
        blocks.append(out.copy())
    signal = np.concatenate(blocks)

    # A 1 kHz sine at 48 kHz moves at most ~0.131 per sample. Any block-boundary
    # discontinuity would show up as a much larger jump.
    assert np.max(np.abs(np.diff(signal))) < 0.15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_drift.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.drift'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/audio/drift.py`:

```python
"""Clock-drift compensation between two independent audio devices.

The microphone and the virtual cable are driven by different oscillators. A
typical 10-100 ppm deviation means one frame gained or lost every few seconds,
which is audible as a click. ``DriftController`` watches how full the bridging
ring buffer is and asks for a slightly different read rate; ``DriftResampler``
applies that rate with a fractional read position.
"""

from __future__ import annotations

import numpy as np

from soundboard.audio.ringbuffer import RingBuffer


class DriftController:
    """Proportional controller over the ring buffer fill level."""

    def __init__(
        self,
        target_fill: int,
        alpha: float = 0.005,
        gain: float = 0.05,
        max_deviation: float = 0.005,
    ) -> None:
        if target_fill <= 0:
            raise ValueError("target_fill must be positive")
        self._target = float(target_fill)
        self._alpha = alpha
        self._gain = gain
        self._max_deviation = max_deviation
        self._ema = float(target_fill)

    @property
    def ema_fill(self) -> float:
        """Smoothed estimate of the ring buffer fill level, in frames."""
        return self._ema

    def update(self, fill: int) -> float:
        """Feed the current fill level and get the read ratio to apply."""
        self._ema += self._alpha * (fill - self._ema)
        error = (self._ema - self._target) / self._target
        ratio = 1.0 + self._gain * error
        low = 1.0 - self._max_deviation
        high = 1.0 + self._max_deviation
        return min(max(ratio, low), high)


class DriftResampler:
    """Pulls frames from a ring buffer at a fractionally variable rate.

    ``ratio`` is input frames consumed per output frame produced. Neighbouring
    input samples are linearly interpolated; at the +-0.5% deviations this is used
    for, that is a sub-sample fractional delay whose distortion sits far below the
    noise floor of any microphone.
    """

    _MAX_RATIO = 1.02

    def __init__(self, source: RingBuffer, max_block: int) -> None:
        self._source = source
        self._phase = 0.0
        self._history = np.zeros(2, dtype=np.float32)
        self._history_len = 0
        span = int(max_block * self._MAX_RATIO) + 4
        self._buffer = np.zeros(span, dtype=np.float32)
        self._grid = np.arange(span, dtype=np.float64)
        self._ramp = np.arange(max_block, dtype=np.float64)
        self._positions = np.zeros(max_block, dtype=np.float64)

    def read(self, out: np.ndarray, ratio: float) -> None:
        """Fill ``out`` with ``len(out)`` frames read at the given ratio."""
        n = out.shape[0]
        positions = self._positions[:n]
        np.multiply(self._ramp[:n], ratio, out=positions)
        positions += self._phase

        # Highest input index the interpolation will touch, plus its partner.
        span = int(positions[n - 1]) + 2
        window = self._buffer[:span]
        kept = self._history_len
        window[:kept] = self._history[:kept]
        self._source.read(window[kept:])

        # np.interp allocates its result; there is no out= parameter. One small
        # array per block is the single unavoidable allocation in this path.
        out[:] = np.interp(positions, self._grid[:span], window)

        advance = self._phase + n * ratio
        consumed = int(advance)
        self._phase = advance - consumed
        kept = max(span - consumed, 0)
        self._history_len = kept
        self._history[:kept] = window[consumed : consumed + kept]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_drift.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/drift.py tests/unit/test_drift.py
git commit -m "feat(audio): add clock-drift controller and fractional-rate resampler"
```

---

### Task 4: Protocolo AudioBackend y FakeBackend

**Files:**
- Create: `src/soundboard/audio/backend.py`, `src/soundboard/audio/fake_backend.py`
- Test: `tests/unit/test_fake_backend.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `DeviceInfo(index: int, name: str, hostapi: str, max_input_channels: int,
    max_output_channels: int, default_samplerate: float)` — dataclass congelada.
  - `InputCallback = Callable[[np.ndarray], None]` — recibe `(frames,)` mono float32.
  - `OutputCallback = Callable[[np.ndarray], None]` — recibe `(frames, channels)` float32
    a rellenar en el sitio.
  - `Stream` protocolo: `start()`, `stop()`, `close()`.
  - `AudioBackend` protocolo: `list_devices()`, `open_input(*, device, samplerate,
    blocksize, callback)`, `open_output(*, device, samplerate, blocksize, channels, callback)`.
  - `FakeBackend()` con `input_source: Callable[[int], np.ndarray] | None`,
    `captured: list[np.ndarray]` y `advance(blocks: int = 1) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_fake_backend.py`:

```python
import numpy as np

from soundboard.audio.fake_backend import FakeBackend


def test_lists_default_devices() -> None:
    backend = FakeBackend()
    names = [d.name for d in backend.list_devices()]

    assert "Fake Microphone" in names
    assert "Fake Cable" in names


def test_advance_drives_the_input_callback() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: np.full(frames, 0.25, dtype=np.float32)
    received: list[np.ndarray] = []
    stream = backend.open_input(
        device=0, samplerate=48_000, blocksize=64, callback=lambda block: received.append(block.copy())
    )
    stream.start()

    backend.advance(3)

    assert len(received) == 3
    assert np.allclose(received[0], 0.25)


def test_advance_captures_output_blocks() -> None:
    backend = FakeBackend()

    def fill(out: np.ndarray) -> None:
        out[:] = 0.5

    stream = backend.open_output(
        device=1, samplerate=48_000, blocksize=64, channels=2, callback=fill
    )
    stream.start()

    backend.advance(2)

    assert len(backend.captured) == 2
    assert backend.captured[0].shape == (64, 2)
    assert np.allclose(backend.captured[0], 0.5)


def test_stopped_streams_do_not_run() -> None:
    backend = FakeBackend()
    calls = 0

    def count(block: np.ndarray) -> None:
        nonlocal calls
        calls += 1

    stream = backend.open_input(device=0, samplerate=48_000, blocksize=64, callback=count)
    backend.advance(5)

    assert calls == 0
    stream.start()
    backend.advance(2)
    assert calls == 2


def test_input_runs_before_output_within_a_block() -> None:
    backend = FakeBackend()
    order: list[str] = []
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)
    out_stream = backend.open_output(
        device=1, samplerate=48_000, blocksize=8, channels=1, callback=lambda o: order.append("out")
    )
    in_stream = backend.open_input(
        device=0, samplerate=48_000, blocksize=8, callback=lambda b: order.append("in")
    )
    out_stream.start()
    in_stream.start()

    backend.advance(2)

    assert order == ["in", "out", "in", "out"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_fake_backend.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.fake_backend'`.

- [ ] **Step 3: Write the protocol module**

`src/soundboard/audio/backend.py`:

```python
"""Audio backend abstraction.

Keeping PortAudio behind a protocol is what makes the engine testable: the whole
mixing path can run against an in-memory backend with a simulated clock, in CI,
with no sound card present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

InputCallback = Callable[[np.ndarray], None]
"""Receives a ``(frames,)`` mono float32 block of captured audio."""

OutputCallback = Callable[[np.ndarray], None]
"""Receives a ``(frames, channels)`` float32 block to fill in place."""


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


class Stream(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class AudioBackend(Protocol):
    def list_devices(self) -> list[DeviceInfo]: ...

    def open_input(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        callback: InputCallback,
    ) -> Stream: ...

    def open_output(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        channels: int,
        callback: OutputCallback,
    ) -> Stream: ...
```

- [ ] **Step 4: Write the fake backend**

`src/soundboard/audio/fake_backend.py`:

```python
"""In-memory audio backend with a simulated clock, for tests."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from soundboard.audio.backend import DeviceInfo, InputCallback, OutputCallback

_DEFAULT_DEVICES = [
    DeviceInfo(0, "Fake Microphone", "fake", 1, 0, 48_000.0),
    DeviceInfo(1, "Fake Cable", "fake", 0, 2, 48_000.0),
]


class FakeStream:
    def __init__(self, backend: FakeBackend, is_input: bool, blocksize: int, channels: int,
                 callback: Callable[[np.ndarray], None]) -> None:
        self.backend = backend
        self.is_input = is_input
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.started = False
        self.closed = True
        if self in self.backend.streams:
            self.backend.streams.remove(self)


class FakeBackend:
    """Drives audio callbacks deterministically from the calling thread.

    ``advance(n)`` simulates ``n`` block periods. Input streams always run before
    output streams within a block, matching the real ordering closely enough for
    the engine's ring buffer accounting to behave the same way.
    """

    def __init__(self, devices: list[DeviceInfo] | None = None) -> None:
        self._devices = list(devices) if devices is not None else list(_DEFAULT_DEVICES)
        self.streams: list[FakeStream] = []
        self.input_source: Callable[[int], np.ndarray] | None = None
        self.captured: list[np.ndarray] = []

    def list_devices(self) -> list[DeviceInfo]:
        return list(self._devices)

    def open_input(self, *, device: int | None, samplerate: int, blocksize: int,
                   callback: InputCallback) -> FakeStream:
        stream = FakeStream(self, True, blocksize, 1, callback)
        self.streams.append(stream)
        return stream

    def open_output(self, *, device: int | None, samplerate: int, blocksize: int,
                    channels: int, callback: OutputCallback) -> FakeStream:
        stream = FakeStream(self, False, blocksize, channels, callback)
        self.streams.append(stream)
        return stream

    def advance(self, blocks: int = 1) -> None:
        for _ in range(blocks):
            for stream in [s for s in self.streams if s.is_input and s.started]:
                source = self.input_source
                block = (
                    source(stream.blocksize)
                    if source is not None
                    else np.zeros(stream.blocksize, dtype=np.float32)
                )
                stream.callback(block)
            for stream in [s for s in self.streams if not s.is_input and s.started]:
                out = np.zeros((stream.blocksize, stream.channels), dtype=np.float32)
                stream.callback(out)
                self.captured.append(out)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_fake_backend.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/audio/backend.py src/soundboard/audio/fake_backend.py tests/unit/test_fake_backend.py
git commit -m "feat(audio): add AudioBackend protocol and deterministic fake backend"
```

---

### Task 5: Voice

**Files:**
- Create: `src/soundboard/audio/voice.py`
- Test: `tests/unit/test_voice.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `Voice(pcm: np.ndarray, gain: float = 1.0, loop: bool = False, start: int = 0,
    end: int | None = None)`
  - `Voice.mix_into(out: np.ndarray) -> None` — suma el siguiente bloque sobre `out`.
  - `Voice.finished: bool`
  - `Voice.position: int`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_voice.py`:

```python
import numpy as np

from soundboard.audio.voice import Voice


def test_mixes_samples_additively_with_gain() -> None:
    voice = Voice(np.ones(4, dtype=np.float32), gain=0.5)
    out = np.full(4, 1.0, dtype=np.float32)

    voice.mix_into(out)

    assert np.allclose(out, 1.5)


def test_respects_trim_start_and_end() -> None:
    voice = Voice(np.arange(10, dtype=np.float32), start=2, end=5)
    out = np.zeros(4, dtype=np.float32)

    voice.mix_into(out)

    assert np.array_equal(out, np.array([2, 3, 4, 0], dtype=np.float32))
    assert voice.finished


def test_finishes_and_leaves_the_rest_of_the_block_untouched() -> None:
    voice = Voice(np.ones(2, dtype=np.float32))
    out = np.zeros(5, dtype=np.float32)

    voice.mix_into(out)

    assert np.array_equal(out, np.array([1, 1, 0, 0, 0], dtype=np.float32))
    assert voice.finished


def test_finished_voice_writes_nothing_more() -> None:
    voice = Voice(np.ones(2, dtype=np.float32))
    out = np.zeros(4, dtype=np.float32)
    voice.mix_into(out)
    out[:] = 0.0

    voice.mix_into(out)

    assert np.array_equal(out, np.zeros(4, dtype=np.float32))


def test_loops_back_to_the_trim_start() -> None:
    voice = Voice(np.array([1, 2, 3], dtype=np.float32), loop=True)
    out = np.zeros(7, dtype=np.float32)

    voice.mix_into(out)

    assert np.array_equal(out, np.array([1, 2, 3, 1, 2, 3, 1], dtype=np.float32))
    assert not voice.finished


def test_spans_multiple_blocks() -> None:
    voice = Voice(np.arange(6, dtype=np.float32))
    first = np.zeros(4, dtype=np.float32)
    second = np.zeros(4, dtype=np.float32)

    voice.mix_into(first)
    voice.mix_into(second)

    assert np.array_equal(first, np.array([0, 1, 2, 3], dtype=np.float32))
    assert np.array_equal(second, np.array([4, 5, 0, 0], dtype=np.float32))


def test_empty_trim_range_finishes_immediately() -> None:
    voice = Voice(np.ones(4, dtype=np.float32), start=2, end=2)
    out = np.zeros(4, dtype=np.float32)

    voice.mix_into(out)

    assert voice.finished
    assert np.array_equal(out, np.zeros(4, dtype=np.float32))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_voice.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.voice'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/audio/voice.py`:

```python
"""A single clip playback in progress."""

from __future__ import annotations

import numpy as np


class Voice:
    """One playing clip: position, gain, looping and trim range.

    ``mix_into`` adds onto the destination block rather than overwriting it, so
    several voices can share one buffer.
    """

    def __init__(
        self,
        pcm: np.ndarray,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        length = pcm.shape[0]
        self._pcm = pcm
        self.gain = gain
        self.loop = loop
        self._start = max(0, min(start, length))
        self._end = length if end is None else max(self._start, min(end, length))
        self._position = self._start
        self.finished = self._end <= self._start

    @property
    def position(self) -> int:
        return self._position

    def mix_into(self, out: np.ndarray) -> None:
        """Add the next block of this voice onto ``out``."""
        written = 0
        total = out.shape[0]
        while written < total and not self.finished:
            take = min(total - written, self._end - self._position)
            chunk = self._pcm[self._position : self._position + take]
            out[written : written + take] += chunk * self.gain
            self._position += take
            written += take
            if self._position >= self._end:
                if self.loop:
                    self._position = self._start
                else:
                    self.finished = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_voice.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/voice.py tests/unit/test_voice.py
git commit -m "feat(audio): add Voice with trim, gain and looping"
```

---

### Task 6: Mixer

**Files:**
- Create: `src/soundboard/audio/mixer.py`
- Test: `tests/unit/test_mixer.py`

**Interfaces:**
- Consumes: `Voice` de la Task 5.
- Produces:
  - `CEILING: float` — `10 ** (-1/20)`, techo del limitador.
  - `Mixer(blocksize: int, samplerate: int = 48000, duck_db: float = -12.0,
    attack_ms: float = 10.0, release_ms: float = 300.0, duck_threshold: float = 0.01)`
  - `Mixer.add_voice(voice: Voice) -> None`
  - `Mixer.stop_all() -> None`
  - `Mixer.process(mic: np.ndarray, out: np.ndarray) -> None` — ambos `(blocksize,)` mono.
  - `Mixer.active_voices -> int`
  - `Mixer.output_gain: float`, `Mixer.ducking_enabled: bool`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_mixer.py`:

```python
import numpy as np

from soundboard.audio.mixer import CEILING, Mixer
from soundboard.audio.voice import Voice


def test_passes_the_microphone_through_when_idle() -> None:
    mixer = Mixer(blocksize=8)
    mic = np.full(8, 0.1, dtype=np.float32)
    out = np.zeros(8, dtype=np.float32)

    mixer.process(mic, out)

    assert np.allclose(out, 0.1, atol=1e-3)


def test_adds_voice_audio_to_the_microphone() -> None:
    mixer = Mixer(blocksize=4, duck_threshold=1.0)  # threshold high: no ducking here
    mixer.add_voice(Voice(np.full(4, 0.2, dtype=np.float32)))
    mic = np.full(4, 0.1, dtype=np.float32)
    out = np.zeros(4, dtype=np.float32)

    mixer.process(mic, out)

    # The soft limiter bends even quiet signals slightly, so compare loosely.
    assert np.allclose(out, 0.3, atol=0.02)


def test_ducking_attenuates_the_microphone_while_a_clip_plays() -> None:
    mixer = Mixer(blocksize=256, duck_db=-12.0)
    # Levels are kept low so the soft limiter stays out of the way and the
    # measured attenuation is the ducking gain alone.
    mixer.add_voice(Voice(np.full(256 * 100, 0.05, dtype=np.float32), loop=True))
    mic = np.full(256, 0.2, dtype=np.float32)
    out = np.zeros(256, dtype=np.float32)

    for _ in range(50):
        mixer.process(mic, out)

    expected_gain = 10.0 ** (-12.0 / 20.0)  # 0.2512
    mic_component = float(np.mean(out)) - 0.05
    assert abs(mic_component - 0.2 * expected_gain) < 0.005


def test_ducking_can_be_disabled() -> None:
    mixer = Mixer(blocksize=256, duck_db=-12.0)
    mixer.ducking_enabled = False
    mixer.add_voice(Voice(np.full(256 * 100, 0.05, dtype=np.float32), loop=True))
    mic = np.full(256, 0.2, dtype=np.float32)
    out = np.zeros(256, dtype=np.float32)

    for _ in range(50):
        mixer.process(mic, out)

    assert abs(float(np.mean(out)) - 0.25) < 0.005


def test_finished_voices_are_dropped() -> None:
    mixer = Mixer(blocksize=4)
    mixer.add_voice(Voice(np.ones(2, dtype=np.float32)))
    out = np.zeros(4, dtype=np.float32)
    mic = np.zeros(4, dtype=np.float32)

    assert mixer.active_voices == 1
    mixer.process(mic, out)
    assert mixer.active_voices == 0


def test_stop_all_clears_every_voice() -> None:
    mixer = Mixer(blocksize=4)
    mixer.add_voice(Voice(np.ones(1000, dtype=np.float32)))
    mixer.add_voice(Voice(np.ones(1000, dtype=np.float32)))

    mixer.stop_all()

    assert mixer.active_voices == 0


def test_limiter_keeps_the_output_under_the_ceiling() -> None:
    mixer = Mixer(blocksize=8, duck_threshold=1e9)
    mic = np.full(8, 5.0, dtype=np.float32)
    out = np.zeros(8, dtype=np.float32)

    mixer.process(mic, out)

    assert np.all(np.abs(out) < CEILING)


def test_output_gain_scales_the_mix() -> None:
    mixer = Mixer(blocksize=4, duck_threshold=1e9)
    mixer.output_gain = 0.5
    mic = np.full(4, 0.2, dtype=np.float32)
    out = np.zeros(4, dtype=np.float32)

    mixer.process(mic, out)

    assert np.allclose(out, 0.1, atol=1e-3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_mixer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.mixer'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/audio/mixer.py`:

```python
"""Mixes the microphone bus with the active clip voices."""

from __future__ import annotations

import math

import numpy as np

from soundboard.audio.voice import Voice

CEILING = 10.0 ** (-1.0 / 20.0)
"""Soft-clip ceiling, -1 dBFS."""


class Mixer:
    """Sums voices onto the microphone bus, with ducking and a soft limiter.

    Ducking is evaluated once per block rather than per sample. At 256 frames a
    block is 5.3 ms, an order of magnitude shorter than the attack time, so the
    extra resolution would buy nothing.
    """

    def __init__(
        self,
        blocksize: int,
        samplerate: int = 48_000,
        duck_db: float = -12.0,
        attack_ms: float = 10.0,
        release_ms: float = 300.0,
        duck_threshold: float = 0.01,
    ) -> None:
        self._sounds = np.zeros(blocksize, dtype=np.float32)
        self._voices: list[Voice] = []
        self._duck_floor = 10.0 ** (duck_db / 20.0)
        self._duck_gain = 1.0
        self._attack = math.exp(-1000.0 / (samplerate * attack_ms))
        self._release = math.exp(-1000.0 / (samplerate * release_ms))
        self._threshold = duck_threshold
        self.output_gain = 1.0
        self.ducking_enabled = True

    @property
    def active_voices(self) -> int:
        return len(self._voices)

    def add_voice(self, voice: Voice) -> None:
        self._voices.append(voice)

    def stop_all(self) -> None:
        self._voices.clear()

    def process(self, mic: np.ndarray, out: np.ndarray) -> None:
        """Render one block: ``out = limit((mic * duck) + sounds)``."""
        sounds = self._sounds
        sounds[:] = 0.0
        for voice in self._voices:
            voice.mix_into(sounds)
        if any(voice.finished for voice in self._voices):
            # Rebuilding the list allocates; it only happens on the blocks where a
            # clip actually ends, not on every block.
            self._voices = [voice for voice in self._voices if not voice.finished]

        loud = self.ducking_enabled and bool(np.max(np.abs(sounds)) > self._threshold)
        target = self._duck_floor if loud else 1.0
        coefficient = self._attack if target < self._duck_gain else self._release
        self._duck_gain = target + (self._duck_gain - target) * coefficient ** out.shape[0]

        np.multiply(mic, self._duck_gain, out=out)
        np.add(out, sounds, out=out)
        np.multiply(out, self.output_gain, out=out)
        np.divide(out, CEILING, out=out)
        np.tanh(out, out=out)
        np.multiply(out, CEILING, out=out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_mixer.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/soundboard/audio/mixer.py tests/unit/test_mixer.py
git commit -m "feat(audio): add mixer with ducking and soft limiter"
```

---

### Task 7: AudioEngine

**Files:**
- Create: `src/soundboard/audio/engine.py`
- Test: `tests/integration/test_engine.py`

**Interfaces:**
- Consumes: `AudioBackend`, `RingBuffer`, `DriftController`, `DriftResampler`, `Mixer`, `Voice`.
- Produces:
  - `EngineConfig(samplerate: int = 48000, blocksize: int = 256, input_device: int | None = None,
    output_device: int | None = None, output_channels: int = 1, target_fill_blocks: int = 2,
    capacity_blocks: int = 16)` — dataclass congelada.
  - `EngineMetrics(underruns: int, overruns: int, fill: int, ratio: float, active_voices: int)`
  - `AudioEngine(backend: AudioBackend, config: EngineConfig | None = None)`
  - `AudioEngine.start() -> None`, `AudioEngine.stop() -> None`
  - `AudioEngine.play(pcm, *, gain=1.0, loop=False, start=0, end=None) -> None` — seguro
    desde cualquier hilo; encola un comando.
  - `AudioEngine.stop_all() -> None`
  - `AudioEngine.metrics -> EngineMetrics`
  - `AudioEngine.mixer -> Mixer`

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_engine.py`:

```python
import numpy as np

from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.fake_backend import FakeBackend

CONFIG = EngineConfig(blocksize=64, output_channels=1)


def _tone(frames: int, level: float = 0.2) -> np.ndarray:
    return np.full(frames, level, dtype=np.float32)


def test_microphone_reaches_the_output() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: _tone(frames)
    engine = AudioEngine(backend, CONFIG)
    engine.start()

    backend.advance(40)

    tail = np.concatenate([block[:, 0] for block in backend.captured[-5:]])
    assert np.allclose(tail, 0.2, atol=0.02)


def test_priming_prevents_startup_underruns() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: _tone(frames)
    engine = AudioEngine(backend, CONFIG)
    engine.start()

    backend.advance(200)

    assert engine.metrics.underruns == 0


def test_played_clip_is_added_to_the_output() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)
    engine = AudioEngine(backend, CONFIG)
    engine.start()
    backend.advance(5)

    engine.play(np.full(64 * 4, 0.5, dtype=np.float32))
    backend.advance(3)

    recent = np.concatenate([block[:, 0] for block in backend.captured[-2:]])
    assert np.max(recent) > 0.4


def test_stop_all_silences_a_looping_clip() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: np.zeros(frames, dtype=np.float32)
    engine = AudioEngine(backend, CONFIG)
    engine.start()
    engine.play(np.full(64, 0.5, dtype=np.float32), loop=True)
    backend.advance(5)

    engine.stop_all()
    backend.advance(5)

    assert np.max(np.abs(backend.captured[-1])) < 1e-6


def test_drift_controller_keeps_the_buffer_near_target() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: _tone(frames)
    engine = AudioEngine(backend, CONFIG)
    engine.start()

    backend.advance(500)

    target = CONFIG.target_fill_blocks * CONFIG.blocksize
    assert abs(engine.metrics.fill - target) < CONFIG.blocksize


def test_output_is_broadcast_to_every_channel() -> None:
    backend = FakeBackend()
    backend.input_source = lambda frames: _tone(frames)
    engine = AudioEngine(backend, EngineConfig(blocksize=64, output_channels=2))
    engine.start()

    backend.advance(20)

    block = backend.captured[-1]
    assert block.shape == (64, 2)
    assert np.array_equal(block[:, 0], block[:, 1])


def test_stop_closes_every_stream() -> None:
    backend = FakeBackend()
    engine = AudioEngine(backend, CONFIG)
    engine.start()

    engine.stop()

    assert backend.streams == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/integration/test_engine.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.engine'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/audio/engine.py`:

```python
"""Wires the capture stream, the mixer and the output stream together."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from soundboard.audio.backend import AudioBackend, Stream
from soundboard.audio.drift import DriftController, DriftResampler
from soundboard.audio.mixer import Mixer
from soundboard.audio.ringbuffer import RingBuffer
from soundboard.audio.voice import Voice


@dataclass(frozen=True)
class EngineConfig:
    samplerate: int = 48_000
    blocksize: int = 256
    input_device: int | None = None
    output_device: int | None = None
    output_channels: int = 1
    target_fill_blocks: int = 2
    capacity_blocks: int = 16


@dataclass(frozen=True)
class EngineMetrics:
    underruns: int
    overruns: int
    fill: int
    ratio: float
    active_voices: int


class AudioEngine:
    """Owns the real-time audio path.

    The input callback only writes captured frames into the ring buffer. The
    output callback does everything else: drain pending commands, read the
    microphone bus at the drift-corrected rate, mix, and broadcast to the output
    channels.
    """

    def __init__(self, backend: AudioBackend, config: EngineConfig | None = None) -> None:
        self._backend = backend
        self._config = config or EngineConfig()
        block = self._config.blocksize
        self._target_fill = self._config.target_fill_blocks * block
        self._ring = RingBuffer(self._config.capacity_blocks * block + 1)
        self._controller = DriftController(target_fill=self._target_fill)
        self._resampler = DriftResampler(self._ring, max_block=block)
        self._mixer = Mixer(blocksize=block, samplerate=self._config.samplerate)
        self._mic_block = np.zeros(block, dtype=np.float32)
        self._mix_block = np.zeros(block, dtype=np.float32)
        self._commands: deque[tuple[str, Voice | None]] = deque()
        self._ratio = 1.0
        self._input_stream: Stream | None = None
        self._output_stream: Stream | None = None

    @property
    def mixer(self) -> Mixer:
        return self._mixer

    @property
    def config(self) -> EngineConfig:
        return self._config

    @property
    def metrics(self) -> EngineMetrics:
        return EngineMetrics(
            underruns=self._ring.underruns,
            overruns=self._ring.overruns,
            fill=self._ring.fill,
            ratio=self._ratio,
            active_voices=self._mixer.active_voices,
        )

    def start(self) -> None:
        # Prime the buffer so the first blocks do not underrun and the latency
        # settles immediately at the target instead of drifting up to it.
        self._ring.write(np.zeros(self._target_fill, dtype=np.float32))
        self._input_stream = self._backend.open_input(
            device=self._config.input_device,
            samplerate=self._config.samplerate,
            blocksize=self._config.blocksize,
            callback=self._on_input,
        )
        self._output_stream = self._backend.open_output(
            device=self._config.output_device,
            samplerate=self._config.samplerate,
            blocksize=self._config.blocksize,
            channels=self._config.output_channels,
            callback=self._on_output,
        )
        self._input_stream.start()
        self._output_stream.start()

    def stop(self) -> None:
        for stream in (self._output_stream, self._input_stream):
            if stream is not None:
                stream.stop()
                stream.close()
        self._output_stream = None
        self._input_stream = None

    def play(
        self,
        pcm: np.ndarray,
        *,
        gain: float = 1.0,
        loop: bool = False,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        """Queue a clip for playback. Safe to call from any thread."""
        voice = Voice(pcm, gain=gain, loop=loop, start=start, end=end)
        self._commands.append(("play", voice))

    def stop_all(self) -> None:
        """Stop every playing clip. Safe to call from any thread."""
        self._commands.append(("stop_all", None))

    def _on_input(self, block: np.ndarray) -> None:
        self._ring.write(block)

    def _on_output(self, out: np.ndarray) -> None:
        commands = self._commands
        while commands:
            name, voice = commands.popleft()
            if name == "play" and voice is not None:
                self._mixer.add_voice(voice)
            elif name == "stop_all":
                self._mixer.stop_all()

        self._ratio = self._controller.update(self._ring.fill)
        self._resampler.read(self._mic_block, self._ratio)
        self._mixer.process(self._mic_block, self._mix_block)
        out[:] = self._mix_block[:, None]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/integration/test_engine.py -v`
Expected: 7 passed.

- [ ] **Step 5: Run the whole suite and the checks**

Run: `.venv\Scripts\pytest.exe -v` then `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/audio/engine.py tests/integration/test_engine.py
git commit -m "feat(audio): add AudioEngine wiring capture, drift correction and mixing"
```

---

### Task 8: PortAudioBackend

**Files:**
- Create: `src/soundboard/audio/portaudio.py`
- Test: `tests/unit/test_portaudio.py`

**Interfaces:**
- Consumes: protocolo `AudioBackend` de la Task 4.
- Produces:
  - `PortAudioBackend()` — implementa `AudioBackend` sobre `sounddevice`.
  - `find_device(devices: list[DeviceInfo], needle: str, *, want_input: bool) -> DeviceInfo`
    — búsqueda por subcadena sin distinguir mayúsculas; lanza `LookupError` si no hay
    coincidencia y `LookupError` si hay más de una.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_portaudio.py`:

```python
import pytest

from soundboard.audio.backend import DeviceInfo
from soundboard.audio.portaudio import PortAudioBackend, find_device

DEVICES = [
    DeviceInfo(0, "Microphone (Realtek)", "MME", 2, 0, 44_100.0),
    DeviceInfo(1, "CABLE Input (VB-Audio Virtual Cable)", "MME", 0, 2, 48_000.0),
    DeviceInfo(2, "CABLE Output (VB-Audio Virtual Cable)", "MME", 2, 0, 48_000.0),
]


def test_find_device_matches_a_substring_case_insensitively() -> None:
    found = find_device(DEVICES, "realtek", want_input=True)

    assert found.index == 0


def test_find_device_filters_by_direction() -> None:
    found = find_device(DEVICES, "cable", want_input=False)

    assert found.index == 1


def test_find_device_rejects_an_ambiguous_needle() -> None:
    extended = [*DEVICES, DeviceInfo(3, "CABLE-A Output (VB-Audio)", "MME", 2, 0, 48_000.0)]

    with pytest.raises(LookupError, match="ambiguous"):
        find_device(extended, "cable", want_input=True)


def test_find_device_reports_a_missing_needle() -> None:
    with pytest.raises(LookupError, match="no device"):
        find_device(DEVICES, "nonexistent", want_input=True)


@pytest.mark.hardware
def test_lists_real_devices() -> None:
    devices = PortAudioBackend().list_devices()

    assert devices
    assert all(isinstance(d.name, str) for d in devices)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_portaudio.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'soundboard.audio.portaudio'`.

- [ ] **Step 3: Write the implementation**

`src/soundboard/audio/portaudio.py`:

```python
"""PortAudio backend, via the sounddevice bindings."""

from __future__ import annotations

from typing import Any

import numpy as np
import sounddevice as sd

from soundboard.audio.backend import DeviceInfo, InputCallback, OutputCallback, Stream


def find_device(devices: list[DeviceInfo], needle: str, *, want_input: bool) -> DeviceInfo:
    """Resolve a device by case-insensitive substring of its name.

    Devices are matched by name rather than index because PortAudio indices shift
    whenever hardware is plugged in or removed.
    """
    lowered = needle.lower()
    matches = [
        device
        for device in devices
        if lowered in device.name.lower()
        and (device.max_input_channels if want_input else device.max_output_channels) > 0
    ]
    if not matches:
        direction = "input" if want_input else "output"
        raise LookupError(f"no device matching {needle!r} with an {direction} channel")
    if len(matches) > 1:
        names = ", ".join(repr(device.name) for device in matches)
        raise LookupError(f"ambiguous device name {needle!r}; matches: {names}")
    return matches[0]


class _SoundDeviceStream:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()


class PortAudioBackend:
    """Real audio I/O. Mono in, N channels out, always float32."""

    def list_devices(self) -> list[DeviceInfo]:
        hostapis = sd.query_hostapis()
        return [
            DeviceInfo(
                index=index,
                name=str(device["name"]),
                hostapi=str(hostapis[device["hostapi"]]["name"]),
                max_input_channels=int(device["max_input_channels"]),
                max_output_channels=int(device["max_output_channels"]),
                default_samplerate=float(device["default_samplerate"]),
            )
            for index, device in enumerate(sd.query_devices())
        ]

    def open_input(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        callback: InputCallback,
    ) -> Stream:
        def on_data(indata: np.ndarray, frames: int, time: Any, status: Any) -> None:
            callback(indata[:, 0])

        return _SoundDeviceStream(
            sd.InputStream(
                device=device,
                samplerate=samplerate,
                blocksize=blocksize,
                channels=1,
                dtype="float32",
                latency="low",
                callback=on_data,
            )
        )

    def open_output(
        self,
        *,
        device: int | None,
        samplerate: int,
        blocksize: int,
        channels: int,
        callback: OutputCallback,
    ) -> Stream:
        def on_data(outdata: np.ndarray, frames: int, time: Any, status: Any) -> None:
            callback(outdata)

        return _SoundDeviceStream(
            sd.OutputStream(
                device=device,
                samplerate=samplerate,
                blocksize=blocksize,
                channels=channels,
                dtype="float32",
                latency="low",
                callback=on_data,
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_portaudio.py -v`
Expected: 4 passed, 1 deselected (la marcada `hardware`).

- [ ] **Step 5: Run the hardware test locally**

Run: `.venv\Scripts\pytest.exe tests/unit/test_portaudio.py -v -m hardware`
Expected: PASS en tu Windows. Si falla, PortAudio no encuentra dispositivos y hay que
resolverlo antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/audio/portaudio.py tests/unit/test_portaudio.py
git commit -m "feat(audio): add PortAudio backend with name-based device lookup"
```

---

### Task 9: CLI de prueba

**Files:**
- Create: `src/soundboard/audioio.py`, `src/soundboard/cli.py`, `src/soundboard/__main__.py`
- Test: `tests/unit/test_audioio.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `PortAudioBackend`, `AudioEngine`, `EngineConfig`, `find_device`.
- Produces:
  - `load_mono_48k(path: str | Path, samplerate: int = 48000) -> np.ndarray` — decodifica,
    mezcla a mono y remuestrea. Devuelve `(frames,)` float32.
  - `build_parser() -> argparse.ArgumentParser`
  - `main(argv: list[str] | None = None) -> int`
  - Subcomando `devices`: imprime índice, dirección y nombre de cada dispositivo.
  - Subcomando `run --mic NEEDLE --out NEEDLE --sound KEY=PATH [...]`: arranca el motor y
    dispara sonidos escribiendo la tecla y pulsando intro. `stop` para todos, `quit` sale.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_audioio.py`:

```python
from pathlib import Path

import numpy as np
import soundfile as sf

from soundboard.audioio import load_mono_48k


def test_downmixes_stereo_to_mono(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    stereo = np.zeros((100, 2), dtype=np.float32)
    stereo[:, 0] = 1.0
    stereo[:, 1] = 0.0
    sf.write(path, stereo, 48_000)

    pcm = load_mono_48k(path)

    assert pcm.ndim == 1
    assert pcm.dtype == np.float32
    assert np.allclose(pcm, 0.5, atol=1e-3)


def test_resamples_to_48k(tmp_path: Path) -> None:
    path = tmp_path / "low.wav"
    sf.write(path, np.zeros(24_000, dtype=np.float32), 24_000)

    pcm = load_mono_48k(path)

    assert abs(pcm.shape[0] - 48_000) < 100


def test_passes_through_matching_rate(tmp_path: Path) -> None:
    path = tmp_path / "match.wav"
    sf.write(path, np.full(1000, 0.25, dtype=np.float32), 48_000)

    pcm = load_mono_48k(path)

    assert pcm.shape[0] == 1000
    assert np.allclose(pcm, 0.25, atol=1e-4)
```

`tests/unit/test_cli.py`:

```python
import pytest

from soundboard.cli import build_parser, parse_sound_argument


def test_parses_a_sound_assignment() -> None:
    key, path = parse_sound_argument("a=C:/clips/laugh.wav")

    assert key == "a"
    assert path == "C:/clips/laugh.wav"


def test_rejects_a_sound_argument_without_a_key() -> None:
    with pytest.raises(ValueError, match="KEY=PATH"):
        parse_sound_argument("laugh.wav")


def test_devices_subcommand_is_available() -> None:
    args = build_parser().parse_args(["devices"])

    assert args.command == "devices"


def test_run_subcommand_collects_sounds() -> None:
    args = build_parser().parse_args(
        ["run", "--mic", "realtek", "--out", "cable", "--sound", "a=x.wav", "--sound", "b=y.wav"]
    )

    assert args.mic == "realtek"
    assert args.out == "cable"
    assert args.sound == ["a=x.wav", "b=y.wav"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest.exe tests/unit/test_audioio.py tests/unit/test_cli.py -v`
Expected: FAIL con `ModuleNotFoundError` para `soundboard.audioio` y `soundboard.cli`.

- [ ] **Step 3: Write the loader**

`src/soundboard/audioio.py`:

```python
"""Decoding clips into the engine's internal format."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import soxr


def load_mono_48k(path: str | Path, samplerate: int = 48_000) -> np.ndarray:
    """Decode a file into mono float32 at the engine sample rate.

    This is the phase-1 loader: soundfile only, decoding on demand. The library
    importer of phase 2 replaces it with a cached, multi-format pipeline.
    """
    data, file_rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if file_rate != samplerate:
        mono = soxr.resample(mono, file_rate, samplerate, quality="HQ")
    return np.ascontiguousarray(mono, dtype=np.float32)
```

- [ ] **Step 4: Write the CLI**

`src/soundboard/cli.py`:

```python
"""Phase-1 command line: list devices and run the engine."""

from __future__ import annotations

import argparse
import sys

from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.portaudio import PortAudioBackend, find_device
from soundboard.audioio import load_mono_48k


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
    run.add_argument("--sound", action="append", default=[], metavar="KEY=PATH")
    run.add_argument("--blocksize", type=int, default=256)
    return parser


def _print_devices(backend: PortAudioBackend) -> int:
    for device in backend.list_devices():
        direction = []
        if device.max_input_channels:
            direction.append("in")
        if device.max_output_channels:
            direction.append("out")
        print(f"{device.index:3d}  {'/'.join(direction):7s}  [{device.hostapi}]  {device.name}")
    return 0


def _run(args: argparse.Namespace) -> int:
    backend = PortAudioBackend()
    devices = backend.list_devices()
    microphone = find_device(devices, args.mic, want_input=True)
    cable = find_device(devices, args.out, want_input=False)

    clips = {}
    for assignment in args.sound:
        key, path = parse_sound_argument(assignment)
        clips[key] = load_mono_48k(path)

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
                print(f"unknown key {command!r} | {metrics}")
    finally:
        engine.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "devices":
        return _print_devices(PortAudioBackend())
    return _run(args)
```

`src/soundboard/__main__.py`:

```python
"""Entry point."""

from __future__ import annotations

import sys

from soundboard.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_audioio.py tests/unit/test_cli.py -v`
Expected: 7 passed.

- [ ] **Step 6: Run the full suite and the checks**

Run: `.venv\Scripts\pytest.exe -v` then `.venv\Scripts\ruff.exe check .` then `.venv\Scripts\mypy.exe`
Expected: todo en verde.

- [ ] **Step 7: Commit**

```bash
git add src/soundboard/audioio.py src/soundboard/cli.py src/soundboard/__main__.py tests/unit/test_audioio.py tests/unit/test_cli.py
git commit -m "feat(cli): add devices listing and engine runner"
```

---

### Task 10: Verificación manual en Discord

**Files:**
- Create: `docs/manual-checks/2026-07-29-phase-1.md`

**Interfaces:**
- Consumes: la CLI de la Task 9.
- Produces: documento con el resultado real de la comprobación, incluidas las métricas
  observadas.

Esta tarea no tiene pruebas automáticas: comprueba lo único que las pruebas no pueden,
que es que un tercero al otro lado de una llamada oiga lo correcto.

- [ ] **Step 1: Install VB-CABLE**

Descargar VB-CABLE de `https://vb-audio.com/Cable/`, ejecutar el instalador como
administrador y reiniciar. Verificar en el panel de sonido de Windows que aparecen
`CABLE Input` (reproducción) y `CABLE Output` (grabación).

- [ ] **Step 2: Confirm the engine sees both endpoints**

Run: `.venv\Scripts\python.exe -m soundboard devices`
Expected: la lista incluye `CABLE Input (VB-Audio Virtual Cable)` con canales de salida y
`CABLE Output (VB-Audio Virtual Cable)` con canales de entrada.

- [ ] **Step 3: Point Discord at the cable**

En Discord: Ajustes de usuario → Voz y vídeo → Dispositivo de entrada →
`CABLE Output (VB-Audio Virtual Cable)`. Desactivar la supresión de ruido y el control
automático de ganancia, que degradan los clips.

- [ ] **Step 4: Run the engine**

Run:
```
.venv\Scripts\python.exe -m soundboard run --mic "<parte del nombre de tu micro>" --out "CABLE Input" --sound a=<ruta a un wav>
```
Expected: imprime el micrófono y la salida resueltos y queda esperando comandos.

- [ ] **Step 5: Verify in a real call**

Entrar en un canal de voz con otra persona o usar la prueba de micrófono de Discord.
Comprobar los cuatro puntos:

1. Se te oye al hablar.
2. Escribir `a` e intro reproduce el clip para el interlocutor.
3. Al reproducirse el clip tu voz baja de volumen pero no desaparece (*ducking*).
4. Tras varios minutos no hay chasquidos ni cortes periódicos.

- [ ] **Step 6: Record the outcome**

Escribir `docs/manual-checks/2026-07-29-phase-1.md` con: versión de Windows, nombre y
frecuencia nativa del micrófono, tamaño de bloque usado, los cuatro puntos anteriores con
resultado real, y las métricas finales (`underruns`, `overruns`, `fill`, `ratio`) obtenidas
escribiendo cualquier tecla desconocida en la CLI. Si algún punto falla, anotar el síntoma
exacto: es la entrada del diagnóstico posterior, no un detalle menor.

- [ ] **Step 7: Commit**

```bash
git add docs/manual-checks/2026-07-29-phase-1.md
git commit -m "docs: record phase 1 manual verification in Discord"
```

---

## Definición de terminado

- `pytest`, `ruff check` y `mypy` en verde en Windows y en Linux vía CI.
- La CLI reproduce clips y pasa el micrófono a un dispositivo virtual real.
- La comprobación manual en Discord está documentada con resultados reales.
- Ningún fichero de `src/soundboard/audio/` importa PySide6, sqlite3 ni hace E/S.

## Qué queda explícitamente fuera

Biblioteca SQLite, importación multiformato, caché de PCM, interfaz gráfica, detección y
creación del dispositivo virtual, backend de Linux, asistente de primer arranque, atajos
globales, monitor local, categorías, editor de recorte, perfiles, efectos y empaquetado.
Todo eso vive en los planes de las fases siguientes.
