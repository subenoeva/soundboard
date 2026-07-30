# Ejecutables standalone + release automática — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar ejecutables standalone de Windows (`.exe`) y Linux (`.AppImage`)
como assets de GitHub Releases, generados solos al mergear el "Release PR" de
`release-please`, con la config de Supabase horneada en el binario para que amigos no
técnicos puedan correrlo sin instalar Python ni setear variables de entorno.

**Architecture:** Dos workflows nuevos en `.github/workflows/` (`release-please.yml`
gestiona versionado/changelog y abre el Release PR; `release-build.yml` corre en el
evento `release: published`, construye con PyInstaller en una matrix
`[windows-latest, ubuntu-latest]` y sube los binarios a esa Release ya creada). Un
directorio nuevo `packaging/` con los `.spec` de PyInstaller y los scripts de ensamblado
del AppImage de Linux. Tres cambios de código mínimos: `cli.main()` por defecto lanza la
GUI sin argumentos (para que doble clic funcione), `load_supabase_config()` gana un
tercer nivel de fallback opcional (`_baked_defaults.py`, generado y horneado solo en CI,
nunca commiteado), y un dependency-group `packaging` separado de `dev` para que
`ci.yml` no instale PyInstaller.

**Tech Stack:** PyInstaller `>=6.0` (+ `pyinstaller-hooks-contrib`, dependencia
transitiva), `googleapis/release-please-action@v4`, `softprops/action-gh-release@v2`,
`appimagetool` (descargado en el runner, no es una dependencia Python).

**Spec:** `docs/superpowers/specs/2026-07-30-standalone-executables-design.md`

## Global Constraints

- Python `>=3.13`, igual que el resto del repo.
- `pyinstaller>=6.0` vive en su propio dependency-group `packaging` en `pyproject.toml`,
  **nunca** instalado por los jobs de `ci.yml` (que pasan a usar `uv sync --group dev`
  en vez de `uv sync --all-groups`, ahora que hay más de un grupo).
- Orden de resolución de credenciales Supabase en `load_supabase_config()`: variables de
  entorno → `settings.json` → `soundboard._baked_defaults` (import opcional). Este
  tercer nivel no cambia nada en desarrollo local ni en `ci.yml`: el módulo
  `_baked_defaults.py` nunca se commitea (gitignored) y solo existe dentro del runner de
  `release-build.yml`, generado desde los secrets `SOUNDBOARD_SUPABASE_URL` /
  `SOUNDBOARD_SUPABASE_ANON_KEY` del repo.
- Nombre de los assets: `soundboard-vX.Y.Z-windows.exe`,
  `soundboard-vX.Y.Z-linux-x86_64.AppImage`. `release-please-config.json` fija
  `"include-component-in-tag": false` para que el tag sea `vX.Y.Z` (sin prefijo de
  paquete) — el prefijo `soundboard-` del asset lo agrega el workflow al nombrar el
  archivo, no el tag de git.
- Fuera de alcance (ya aprobado en el spec, no lo reabras): firma de código /
  notarización, auto-actualización del binario, ícono de app custom (se usa un
  placeholder generado en build, sin arte), soporte macOS, publicar en AUR / winget /
  Flatpak.
- No hay tests automatizados de "el binario arranca de verdad" — la suite de `pytest`
  no puede correr un `.exe`/`.AppImage` real de forma útil en CI. La verificación de que
  el binario arranca es manual y cierra este plan (Tarea 9).
- Código, identificadores, docstrings, nombres de ficheros de workflow/script y mensajes
  de commit en **inglés**. Documentación de producto (README, specs, planes) en
  **español** — misma convención que ya usa el repo.
- Comandos en esta máquina: `uv` está en
  `C:\Users\k\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.
  Tras `uv sync` se puede usar `.venv\Scripts\pytest.exe`, `.venv\Scripts\ruff.exe` y
  `.venv\Scripts\mypy.exe` directamente, que es lo que asumen los pasos de este plan.
- Este plan se ejecuta en una worktree nueva (`worktree-packaging`, creada vía
  `superpowers:using-git-worktrees` al arrancar la ejecución, no en esta fase de
  planning) — misma convención que `worktree-gui` y `worktree-supabase-sounds`.

---

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `pyproject.toml` | + dependency-group `packaging` (`pyinstaller>=6.0`); + override de mypy para `soundboard._baked_defaults` |
| `uv.lock` | Regenerado por `uv lock` tras el cambio anterior |
| `.github/workflows/ci.yml` | `uv sync --all-groups` → `uv sync --group dev` en ambos jobs, para no instalar `packaging` |
| `.github/workflows/release-please.yml` | Nuevo. Push a `master` → abre/actualiza el Release PR |
| `.github/workflows/release-build.yml` | Nuevo. Evento `release: published` → build + upload matrix Windows/Linux |
| `release-please-config.json` | Nuevo. Config de `release-please` (release-type `simple`, versiona `pyproject.toml`) |
| `.release-please-manifest.json` | Nuevo. Versión actual trackeada (`0.1.0`) |
| `src/soundboard/cli.py` | `main()` inyecta `["gui"]` cuando se invoca sin argumentos |
| `src/soundboard/remote/client.py` | `load_supabase_config()` gana el fallback a `_baked_defaults` |
| `.gitignore` | + `src/soundboard/_baked_defaults.py` |
| `packaging/windows/soundboard.spec` | Nuevo. Spec de PyInstaller `--onefile --windowed` |
| `packaging/linux/soundboard.spec` | Nuevo. Spec de PyInstaller `--onedir` |
| `packaging/linux/make_icon.py` | Nuevo. Genera un ícono PNG placeholder (solo stdlib) |
| `packaging/linux/AppRun` | Nuevo. Entry point del AppImage |
| `packaging/linux/soundboard.desktop` | Nuevo. Descriptor `.desktop` del AppImage |
| `packaging/linux/build_appimage.sh` | Nuevo. Ensambla el AppDir y corre `appimagetool` |
| `tests/unit/test_cli.py` | + tests del default a `gui` |
| `tests/unit/test_client.py` | + tests del fallback a `_baked_defaults` |
| `tests/unit/test_packaging_config.py` | Nuevo. Prueba que el dependency-group existe |
| `tests/unit/test_packaging_windows_spec.py` | Nuevo. Valida sintaxis y contenido del spec de Windows |
| `tests/unit/test_packaging_icon.py` | Nuevo. Prueba `make_icon.py` |
| `tests/unit/test_packaging_linux_spec.py` | Nuevo. Valida sintaxis y contenido del spec de Linux |
| `README.md` | + sección "Descargar ejecutable" |

---

### Task 1: Dependency-group `packaging` y ajuste de `ci.yml`

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (regenerado, no a mano)
- Modify: `.github/workflows/ci.yml`
- Test: `tests/unit/test_packaging_config.py`

**Interfaces:**
- Consumes: nada.
- Produces: dependency-group `packaging = ["pyinstaller>=6.0"]` en `pyproject.toml`,
  instalable vía `uv sync --group packaging`; los jobs `test` y `rls` de `ci.yml` ya no
  lo instalan.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_packaging_config.py`:

```python
import tomllib
from pathlib import Path


def test_packaging_dependency_group_declares_pyinstaller() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())

    assert data["dependency-groups"]["packaging"] == ["pyinstaller>=6.0"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_config.py -v`
Expected: FAIL con `KeyError: 'packaging'`.

- [ ] **Step 3: Add the dependency-group**

En `pyproject.toml`, dentro de `[dependency-groups]`, después de `dev = [...]`:

```toml
packaging = ["pyinstaller>=6.0"]
```

- [ ] **Step 4: Regenerate the lockfile**

Run: `uv lock`
Expected: termina sin error; `uv.lock` queda modificado (agrega `pyinstaller` y
`pyinstaller-hooks-contrib`, su dependencia transitiva).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_config.py -v`
Expected: PASS.

- [ ] **Step 6: Fix `ci.yml` so the test/rls jobs don't install `packaging`**

En `.github/workflows/ci.yml`, en el job `test` reemplazar:

```yaml
      - run: uv sync --all-groups
```

por:

```yaml
      - run: uv sync --group dev
```

y en el job `rls`, el mismo reemplazo (`uv sync --all-groups` → `uv sync --group dev`).

- [ ] **Step 7: Verify the dev workflow still works end to end**

Run:
```
uv sync --group dev
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe
.venv\Scripts\pytest.exe -v
```
Expected: los tres comandos terminan sin error (mismo resultado que antes del cambio,
`packaging` no estaba entre las dependencias que estos comandos necesitan).

- [ ] **Step 8: Verify the packaging group resolves on its own**

Run: `uv sync --group packaging`
Expected: termina sin error; `.venv\Scripts\pyinstaller.exe --version` imprime una
versión `>=6.0`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml tests/unit/test_packaging_config.py
git commit -m "chore: add packaging dependency-group for PyInstaller"
```

---

### Task 2: `cli.main()` lanza la GUI por defecto sin argumentos

**Files:**
- Modify: `src/soundboard/cli.py:293-294`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `soundboard.ui.app.run_gui` (ya existe, firma sin cambios).
- Produces: `main(argv: list[str] | None = None) -> int` — si no llegan argumentos
  (ni por `argv` ni por `sys.argv`), se comporta como `main(["gui"])`. Con argumentos
  explícitos (`devices`, `run`, `auth`, ...) el comportamiento no cambia.

- [ ] **Step 1: Write the failing test**

En `tests/unit/test_cli.py`, agregar al principio del archivo `import sys` y sumar
`main` al import existente de `soundboard.cli` (queda
`from soundboard.cli import _run, build_parser, main, parse_sound_argument`). Después,
al final del archivo:

```python
def test_main_launches_the_gui_when_invoked_without_any_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run_gui() -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr("soundboard.ui.app.run_gui", fake_run_gui)
    monkeypatch.setattr(sys, "argv", ["soundboard"])

    exit_code = main()

    assert exit_code == 0
    assert calls == [True]


def test_main_with_an_empty_explicit_argv_also_launches_the_gui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        "soundboard.ui.app.run_gui", lambda: calls.append(True) or 0
    )

    exit_code = main([])

    assert exit_code == 0
    assert calls == [True]
```

(No se llama a `main(["devices"])` en este test porque tocaría hardware real vía
`PortAudioBackend()` — la regresión de que los comandos explícitos siguen andando ya la
cubre `test_devices_subcommand_is_available`, que ejercita `build_parser()` directo.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_cli.py -k main_launches_the_gui -v`
Expected: FAIL — `argparse` corta con `SystemExit(2)` ("the following arguments are
required: command") en vez de devolver `0`.

- [ ] **Step 3: Inject the `gui` default in `main()`**

En `src/soundboard/cli.py`, reemplazar:

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
```

por:

```python
def main(argv: list[str] | None = None) -> int:
    effective_argv = sys.argv[1:] if argv is None else argv
    if not effective_argv:
        effective_argv = ["gui"]
    args = build_parser().parse_args(effective_argv)
```

(`sys` ya está importado en `cli.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_cli.py -v`
Expected: todos PASS, incluyendo los dos nuevos.

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` luego `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 6: Commit**

```bash
git add src/soundboard/cli.py tests/unit/test_cli.py
git commit -m "fix: default to the gui subcommand when invoked with no arguments"
```

---

### Task 3: `_baked_defaults` como tercer fallback de `load_supabase_config()`

**Files:**
- Modify: `src/soundboard/remote/client.py:55-74`
- Modify: `pyproject.toml` (override de mypy)
- Modify: `.gitignore`
- Test: `tests/unit/test_client.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `load_supabase_config()` intenta, cuando faltan `url`/`key` tras revisar
  entorno y `settings.json`, importar `soundboard._baked_defaults` y leer sus
  constantes `SUPABASE_URL: str` / `SUPABASE_ANON_KEY: str`. Si el módulo no existe
  (`ImportError`), el comportamiento es idéntico al actual.

- [ ] **Step 1: Write the failing test**

En `tests/unit/test_client.py`, agregar `import sys` y `import types` a los imports del
principio del archivo. Después, junto a los demás tests de `load_supabase_config`:

```python
def test_load_supabase_config_falls_back_to_baked_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baked = types.ModuleType("soundboard._baked_defaults")
    baked.SUPABASE_URL = "https://baked.supabase.co"  # type: ignore[attr-defined]
    baked.SUPABASE_ANON_KEY = "baked-key"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundboard._baked_defaults", baked)

    url, key = load_supabase_config(env={}, settings_path=tmp_path / "missing.json")

    assert (url, key) == ("https://baked.supabase.co", "baked-key")


def test_load_supabase_config_prefers_env_over_baked_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baked = types.ModuleType("soundboard._baked_defaults")
    baked.SUPABASE_URL = "https://baked.supabase.co"  # type: ignore[attr-defined]
    baked.SUPABASE_ANON_KEY = "baked-key"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundboard._baked_defaults", baked)
    env = {
        "SOUNDBOARD_SUPABASE_URL": "https://env.supabase.co",
        "SOUNDBOARD_SUPABASE_ANON_KEY": "env-key",
    }

    url, key = load_supabase_config(env=env, settings_path=tmp_path / "missing.json")

    assert (url, key) == ("https://env.supabase.co", "env-key")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_client.py -k baked_defaults -v`
Expected: FAIL — `load_supabase_config` levanta `RuntimeError` porque todavía no conoce
`_baked_defaults`.

- [ ] **Step 3: Implement the fallback**

En `src/soundboard/remote/client.py`, agregar una función auxiliar antes de
`load_supabase_config` y usarla dentro:

```python
def _baked_config() -> tuple[str | None, str | None]:
    try:
        from soundboard._baked_defaults import SUPABASE_ANON_KEY, SUPABASE_URL
    except ImportError:
        return None, None
    return SUPABASE_URL, SUPABASE_ANON_KEY


def load_supabase_config(
    env: Mapping[str, str] | None = None, settings_path: Path | None = None
) -> tuple[str, str]:
    """Resolve ``(url, anon_key)``: environment, then ``settings.json``, then the
    baked-in defaults a packaged executable ships with."""
    resolved_env: Mapping[str, str] = os.environ if env is None else env
    settings_path = settings_path or _default_settings_path()

    url = resolved_env.get("SOUNDBOARD_SUPABASE_URL")
    key = resolved_env.get("SOUNDBOARD_SUPABASE_ANON_KEY")
    if (not url or not key) and settings_path.exists():
        data = json.loads(settings_path.read_text())
        supabase_cfg = data.get("supabase", {})
        url = url or supabase_cfg.get("url")
        key = key or supabase_cfg.get("anon_key")
    if not url or not key:
        baked_url, baked_key = _baked_config()
        url = url or baked_url
        key = key or baked_key
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured: set SOUNDBOARD_SUPABASE_URL and "
            f"SOUNDBOARD_SUPABASE_ANON_KEY, or add them to {settings_path}"
        )
    return url, key
```

- [ ] **Step 4: Add the mypy override**

En `pyproject.toml`, después del último bloque `[[tool.mypy.overrides]]` (el de
`pynput.*`), agregar:

```toml
[[tool.mypy.overrides]]
module = ["soundboard._baked_defaults"]
ignore_missing_imports = true
```

(El módulo no existe en el working tree — se genera y hornea solo dentro del runner de
`release-build.yml` — así que mypy necesita que le digan explícitamente que no falle al
no encontrarlo, igual que ya hace con `keyring`/`pynput`/`sounddevice`.)

- [ ] **Step 5: Ignore the generated file**

En `.gitignore`, agregar bajo la sección "Packaging output":

```
src/soundboard/_baked_defaults.py
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\pytest.exe tests/unit/test_client.py -v`
Expected: todos PASS, incluyendo los dos nuevos y los tres ya existentes de
`load_supabase_config` (regresión: siguen pasando sin cambios).

- [ ] **Step 7: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .` luego `.venv\Scripts\mypy.exe`
Expected: ambos sin errores.

- [ ] **Step 8: Commit**

```bash
git add src/soundboard/remote/client.py pyproject.toml .gitignore tests/unit/test_client.py
git commit -m "feat: fall back to baked-in Supabase defaults when unconfigured"
```

---

### Task 4: Versionado y changelog con `release-please`

**Files:**
- Create: `release-please-config.json`
- Create: `.release-please-manifest.json`
- Create: `.github/workflows/release-please.yml`

**Interfaces:**
- Consumes: nada (lee el historial de commits del repo, que ya sigue Conventional
  Commits).
- Produces: en cada push a `master`, abre/actualiza un Release PR con el bump de
  versión y el changelog; al mergear ese PR, crea el tag `vX.Y.Z` y publica una GitHub
  Release, disparando el evento `release: published` que consume la Tarea 8.

- [ ] **Step 1: Create the release-please config**

`release-please-config.json`:

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "packages": {
    ".": {
      "release-type": "simple",
      "package-name": "soundboard",
      "include-component-in-tag": false,
      "extra-files": [
        {
          "type": "toml",
          "path": "pyproject.toml",
          "jsonpath": "$.project.version"
        }
      ]
    }
  }
}
```

- [ ] **Step 2: Create the version manifest**

`.release-please-manifest.json`:

```json
{
  ".": "0.1.0"
}
```

(Coincide con la `version = "0.1.0"` actual de `pyproject.toml` — release-please la
toma como punto de partida para el próximo bump semver según los commits desde acá.)

- [ ] **Step 3: Create the workflow**

`.github/workflows/release-please.yml`:

```yaml
name: release-please

on:
  push:
    branches: [master]

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    steps:
      - uses: googleapis/release-please-action@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 4: Validate the JSON files parse**

Run: `python -c "import json; json.load(open('release-please-config.json')); json.load(open('.release-please-manifest.json'))"`
Expected: sin salida, sin error (JSON válido en ambos).

- [ ] **Step 5: Commit**

```bash
git add release-please-config.json .release-please-manifest.json .github/workflows/release-please.yml
git commit -m "ci: add release-please for automated versioning and changelogs"
```

- [ ] **Step 6 (verificación diferida, no bloquea el resto del plan):** Una vez
  mergeado este plan a `master`, confirmar que aparece un Release PR de
  `release-please` y que su diff incluye el bump de `version` en `pyproject.toml` (el
  `extra-files` con `jsonpath` recién configurado). Si el PR no toca `pyproject.toml`,
  revisar la versión soportada de `googleapis/release-please-action@v4` (el esquema de
  `extra-files`/`jsonpath` pudo cambiar) antes de seguir.

---

### Task 5: Spec de PyInstaller para Windows

**Files:**
- Create: `packaging/windows/soundboard.spec`
- Test: `tests/unit/test_packaging_windows_spec.py`

**Interfaces:**
- Consumes: `src/soundboard/__main__.py` (entry point existente, sin cambios).
- Produces: invocable como `pyinstaller packaging/windows/soundboard.spec` desde la
  raíz del repo → `dist/soundboard.exe`. Usado por la Tarea 8.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_packaging_windows_spec.py`:

```python
import ast
from pathlib import Path


def test_windows_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/windows/soundboard.spec").read_text()

    ast.parse(source)  # PyInstaller execs .spec files as plain Python

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_windows_spec.py -v`
Expected: FAIL con `FileNotFoundError`.

- [ ] **Step 3: Create the spec file**

`packaging/windows/soundboard.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows --onefile --windowed build.

keyring discovers its backends (here: the Windows Credential Locker) via
entry-points, which PyInstaller's static import analysis does not follow —
without collect_submodules the packaged exe raises "no recommended backend"
at runtime. See docs/superpowers/specs/2026-07-30-standalone-executables-design.md.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

entry_point = os.path.join(SPECPATH, "..", "..", "src", "soundboard", "__main__.py")

a = Analysis(
    [entry_point],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("keyring.backends"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="soundboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_windows_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packaging/windows/soundboard.spec tests/unit/test_packaging_windows_spec.py
git commit -m "build: add the PyInstaller spec for the Windows executable"
```

---

### Task 6: Ícono placeholder para el AppImage

**Files:**
- Create: `packaging/linux/make_icon.py`
- Test: `tests/unit/test_packaging_icon.py`

**Interfaces:**
- Consumes: nada (solo stdlib: `struct`, `zlib`, `argparse`, `pathlib`).
- Produces: script ejecutable `python packaging/linux/make_icon.py <output.png> [--size N]`
  y la función `make_icon(path: Path, size: int = 256) -> None`. Usado por
  `build_appimage.sh` en la Tarea 7.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_packaging_icon.py`:

```python
import struct
import subprocess
import sys
from pathlib import Path


def test_make_icon_writes_a_valid_png(tmp_path: Path) -> None:
    output = tmp_path / "icon.png"

    subprocess.run(
        [sys.executable, "packaging/linux/make_icon.py", str(output), "--size", "32"],
        check=True,
    )

    data = output.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (32, 32)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_icon.py -v`
Expected: FAIL — `subprocess.run(..., check=True)` levanta porque el script no existe
todavía.

- [ ] **Step 3: Write the icon generator**

`packaging/linux/make_icon.py`:

```python
"""Generates a flat-color placeholder PNG icon for the AppImage.

No custom icon design is in scope (see the "Fuera de alcance" section of
docs/superpowers/specs/2026-07-30-standalone-executables-design.md) — this only
needs to exist so appimagetool has something to point ``Icon=`` at. Uses only the
standard library so the release workflow doesn't need an extra system package (e.g.
ImageMagick) or Python dependency (e.g. Pillow) just to draw one flat-color square.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

_COLOR = (0x2D, 0x2D, 0x2D)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def make_icon(path: Path, size: int = 256) -> None:
    row = bytes([0]) + bytes(_COLOR) * size  # filter-type byte + RGB pixels
    raw = row * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit depth, RGB
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args(argv)
    make_icon(args.output, args.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_icon.py -v`
Expected: PASS.

- [ ] **Step 5: Verify lint and types are clean**

Run: `.venv\Scripts\ruff.exe check .`
Expected: sin errores (`packaging/linux/make_icon.py` es un `.py` normal, `ruff check .`
sí lo recorre aunque viva fuera de `src/`).

- [ ] **Step 6: Commit**

```bash
git add packaging/linux/make_icon.py tests/unit/test_packaging_icon.py
git commit -m "build: add a stdlib-only placeholder icon generator for the AppImage"
```

---

### Task 7: Spec de PyInstaller + ensamblado del AppImage para Linux

**Files:**
- Create: `packaging/linux/soundboard.spec`
- Create: `packaging/linux/AppRun`
- Create: `packaging/linux/soundboard.desktop`
- Create: `packaging/linux/build_appimage.sh`
- Test: `tests/unit/test_packaging_linux_spec.py`

**Interfaces:**
- Consumes: `packaging/linux/make_icon.py` (Tarea 6); `dist/soundboard/` producido por
  `pyinstaller packaging/linux/soundboard.spec`.
- Produces: `packaging/linux/build_appimage.sh <output.AppImage>`, invocable desde la
  raíz del repo. Usado por la Tarea 8.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_packaging_linux_spec.py`:

```python
import ast
from pathlib import Path


def test_linux_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/linux/soundboard.spec").read_text()

    ast.parse(source)

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_linux_spec.py -v`
Expected: FAIL con `FileNotFoundError`.

- [ ] **Step 3: Create the PyInstaller spec (onedir)**

`packaging/linux/soundboard.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Linux --onedir build, later assembled into an AppImage
by build_appimage.sh.

Same keyring hidden-import risk as Windows, here for the SecretService backend.
See docs/superpowers/specs/2026-07-30-standalone-executables-design.md.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

entry_point = os.path.join(SPECPATH, "..", "..", "src", "soundboard", "__main__.py")

a = Analysis(
    [entry_point],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("keyring.backends"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="soundboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="soundboard",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest.exe tests/unit/test_packaging_linux_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Create the AppRun entry point**

`packaging/linux/AppRun`:

```sh
#!/bin/sh
here="$(dirname "$(readlink -f "${0}")")"
exec "${here}/usr/bin/soundboard/soundboard" "$@"
```

- [ ] **Step 6: Create the .desktop descriptor**

`packaging/linux/soundboard.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Soundboard
Exec=soundboard
Icon=soundboard
Categories=AudioVideo;
Terminal=false
```

- [ ] **Step 7: Create the AppImage assembly script**

`packaging/linux/build_appimage.sh`:

```bash
#!/usr/bin/env bash
# Assembles the PyInstaller onedir build produced by packaging/linux/soundboard.spec
# into a single-file AppImage. Run from the repo root with one argument: the output
# .AppImage path (e.g. soundboard-v1.2.3-linux-x86_64.AppImage).
#
# See docs/superpowers/specs/2026-07-30-standalone-executables-design.md.
set -euo pipefail

output="$1"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
appdir="$(mktemp -d)/AppDir"

mkdir -p "${appdir}/usr/bin"
cp -r dist/soundboard "${appdir}/usr/bin/soundboard"

# sounddevice's Linux wheel does not bundle PortAudio (ci.yml installs it via apt to
# run the tests) — bundle the system copy so the AppImage needs no runtime dependency
# beyond ALSA, present on practically any Linux distro with audio.
portaudio_so="$(find /usr -name 'libportaudio.so.2' -print -quit)"
if [[ -z "${portaudio_so}" ]]; then
    echo "libportaudio.so.2 not found — install libportaudio2 before building" >&2
    exit 1
fi
cp "${portaudio_so}" "${appdir}/usr/bin/soundboard/_internal/"

cp "${script_dir}/AppRun" "${appdir}/AppRun"
chmod +x "${appdir}/AppRun"
cp "${script_dir}/soundboard.desktop" "${appdir}/soundboard.desktop"
python3 "${script_dir}/make_icon.py" "${appdir}/soundboard.png"

appimagetool="$(mktemp -d)/appimagetool-x86_64.AppImage"
curl -sL -o "${appimagetool}" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x "${appimagetool}"

# GitHub Actions runners have no FUSE; extract-and-run avoids needing to mount the tool.
APPIMAGE_EXTRACT_AND_RUN=1 "${appimagetool}" "${appdir}" "${output}"
```

- [ ] **Step 8: Verify the shell scripts parse**

Run (Git Bash): `bash -n packaging/linux/build_appimage.sh && bash -n packaging/linux/AppRun`
Expected: sin salida, exit code 0 en ambos (chequeo de sintaxis, no ejecuta nada —
`appimagetool` es un binario Linux y esta máquina es Windows).

- [ ] **Step 9: Commit**

```bash
git add packaging/linux/soundboard.spec packaging/linux/AppRun packaging/linux/soundboard.desktop packaging/linux/build_appimage.sh tests/unit/test_packaging_linux_spec.py
git commit -m "build: assemble the Linux onedir PyInstaller output into an AppImage"
```

---

### Task 8: Workflow `release-build.yml` — build y publicación

**Files:**
- Create: `.github/workflows/release-build.yml`

**Interfaces:**
- Consumes: dependency-group `packaging` (Tarea 1); fallback `_baked_defaults`
  (Tarea 3); `packaging/windows/soundboard.spec` (Tarea 5); `packaging/linux/soundboard.spec`
  + `build_appimage.sh` (Tarea 7); default a `gui` de `cli.main()` (Tarea 2, para que el
  binario sea usable con doble clic); workflow `release-please.yml` (Tarea 4), cuyo
  merge del Release PR dispara el evento que arranca este workflow.
- Produces: assets `soundboard-vX.Y.Z-windows.exe` y
  `soundboard-vX.Y.Z-linux-x86_64.AppImage` subidos a la GitHub Release publicada.

- [ ] **Step 1: Create the workflow**

`.github/workflows/release-build.yml`:

```yaml
name: release-build

on:
  release:
    types: [published]

permissions:
  contents: write

jobs:
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group packaging
      - name: Bake Supabase config
        shell: python
        env:
          SOUNDBOARD_SUPABASE_URL: ${{ secrets.SOUNDBOARD_SUPABASE_URL }}
          SOUNDBOARD_SUPABASE_ANON_KEY: ${{ secrets.SOUNDBOARD_SUPABASE_ANON_KEY }}
        run: |
          import os
          from pathlib import Path

          url = os.environ["SOUNDBOARD_SUPABASE_URL"]
          key = os.environ["SOUNDBOARD_SUPABASE_ANON_KEY"]
          Path("src/soundboard/_baked_defaults.py").write_text(
              f"SUPABASE_URL = {url!r}\nSUPABASE_ANON_KEY = {key!r}\n"
          )
      - run: uv run pyinstaller packaging/windows/soundboard.spec
      - name: Rename artifact to the release asset name
        shell: bash
        run: mv dist/soundboard.exe "soundboard-${{ github.event.release.tag_name }}-windows.exe"
      - uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.event.release.tag_name }}
          files: soundboard-${{ github.event.release.tag_name }}-windows.exe

  linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install PortAudio and Qt runtime libraries
        run: sudo apt-get update && sudo apt-get install -y libportaudio2 libegl1 libxkbcommon0 libxcb-cursor0 libgl1 libdbus-1-3
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group packaging
      - name: Bake Supabase config
        shell: python
        env:
          SOUNDBOARD_SUPABASE_URL: ${{ secrets.SOUNDBOARD_SUPABASE_URL }}
          SOUNDBOARD_SUPABASE_ANON_KEY: ${{ secrets.SOUNDBOARD_SUPABASE_ANON_KEY }}
        run: |
          import os
          from pathlib import Path

          url = os.environ["SOUNDBOARD_SUPABASE_URL"]
          key = os.environ["SOUNDBOARD_SUPABASE_ANON_KEY"]
          Path("src/soundboard/_baked_defaults.py").write_text(
              f"SUPABASE_URL = {url!r}\nSUPABASE_ANON_KEY = {key!r}\n"
          )
      - run: uv run pyinstaller packaging/linux/soundboard.spec
      - name: Assemble the AppImage
        run: |
          chmod +x packaging/linux/AppRun packaging/linux/build_appimage.sh
          packaging/linux/build_appimage.sh "soundboard-${{ github.event.release.tag_name }}-linux-x86_64.AppImage"
      - uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.event.release.tag_name }}
          files: soundboard-${{ github.event.release.tag_name }}-linux-x86_64.AppImage
```

- [ ] **Step 2: Validate the workflow YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release-build.yml'))"`
Expected: sin salida, sin error. (Si `pyyaml` no está instalado en el venv, usar
`.venv\Scripts\python.exe -c "..."` tras `uv add --group dev pyyaml` no es necesario —
alternativamente, validar con cualquier linter YAML ya disponible, o simplemente revisar
a ojo la indentación contra el bloque de arriba.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-build.yml
git commit -m "ci: build and publish standalone executables on release"
```

---

### Task 9: Documentación y verificación manual final

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: sección "Descargar ejecutable" documentada; cierre manual del plan.

- [ ] **Step 1: Add the "Descargar ejecutable" section**

En `README.md`, después de la sección `## Instalación` (antes de
`### Dispositivo virtual (requisito externo)`), insertar:

```markdown
### Descargar el ejecutable (sin instalar Python)

Para amigos que solo quieren correr la app, sin clonar el repo ni instalar `uv`:
descarga el binario de la [página de Releases](https://github.com/subenoeva/soundboard/releases) —
`soundboard-vX.Y.Z-windows.exe` o `soundboard-vX.Y.Z-linux-x86_64.AppImage`. Viene
configurado para hablar contra la biblioteca de sonidos compartida, sin setear nada.

Limitaciones que se heredan del proyecto:

- **Windows**: igual hace falta instalar [VB-CABLE](https://vb-audio.com/Cable/) aparte
  (no se puede empaquetar un driver de kernel firmado). El `.exe` no está firmado
  digitalmente — si Windows SmartScreen avisa "editor desconocido", es normal;
  "más información → ejecutar de todas formas".
- **Linux**: igual hace falta configurar un null-sink de PipeWire/PulseAudio a mano (ver
  arriba). Los atajos globales no funcionan bajo Wayland. Si no hay `gnome-keyring` ni
  `kwalletd` corriendo, guardar la sesión puede fallar — asegúrate de tener uno de los
  dos activo.
```

- [ ] **Step 2: Update the roadmap note**

En la sección `## Roadmap`, agregar una entrada nueva antes de "**Enrutado
automático**":

```markdown
- **Ejecutables standalone**: ✅ diseñado e implementado — releases automáticas vía
  `release-please` + PyInstaller, ver
  [`docs/superpowers/specs/2026-07-30-standalone-executables-design.md`](docs/superpowers/specs/2026-07-30-standalone-executables-design.md).
```

- [ ] **Step 3: Run the full suite once more**

Run:
```
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe
.venv\Scripts\pytest.exe -v
```
Expected: los tres sin errores.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document downloading the standalone executables"
```

- [ ] **Step 5 (gate manual de cierre, no se puede automatizar):** Una vez este plan
  esté mergeado a `master` y `release-please` haya abierto su Release PR (Tarea 4,
  Step 6), mergear ese Release PR, esperar a que `release-build.yml` termine, y bajar
  los dos binarios de la Release recién publicada. Correr el `.exe` en un Windows real y
  el `.AppImage` en un Linux real (Arch u otra distro) — al menos uno de los dos antes
  de considerar la feature terminada, los dos si es posible. Confirmar: la ventana abre
  con doble clic (sin consola de fondo en Windows), pide login si no hay sesión, y
  reproduce un sonido de la biblioteca compartida sin haber tocado configuración
  ninguna. Importante: la máquina donde se prueba el `.AppImage` **no** debe tener
  `libportaudio2` instalado a nivel sistema, porque una máquina de desarrollo que ya lo
  tenga por otros motivos enmascara justamente la regresión de PortAudio que el
  runtime hook `packaging/linux/rt_hook_portaudio.py` corrige. Lo más simple es un
  contenedor limpio:
  `docker run --rm -v "$PWD:/x" ubuntu:24.04 /x/soundboard-vX.Y.Z-linux-x86_64.AppImage`.

---

## Self-Review

- **Cobertura del spec:** las 5 secciones de arquitectura del spec (versionado,
  build/publicación, config horneada, default a `gui`, documentación) tienen tarea
  dedicada (4; 5+6+7+8; 3; 2; 9). La sección "Fuera de alcance" no generó tareas,
  correcto. La sección "Testing/verificación" del spec se refleja en el Step 5 final de
  la Tarea 9 y en las notas de verificación diferida de las Tareas 4 y 8.
- **Placeholders:** ninguno — cada paso trae el código/config completo, sin "TODO" ni
  "agregar validación acá".
- **Consistencia de tipos/nombres:** `make_icon(path: Path, size: int = 256) -> None`
  (Tarea 6) es el nombre que usa `build_appimage.sh` (Tarea 7) vía CLI, no importado
  directo — sin acoplamiento de firma entre tareas ahí. `load_supabase_config()` y
  `_baked_config()` (Tarea 3) mantienen los nombres ya existentes en el código real
  (no el `resolve_config()` que menciona el spec, que no existe en el repo — se corrigió
  al nombre real durante la exploración de código previa a este plan).
