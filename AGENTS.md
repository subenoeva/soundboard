# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) working with
code in this repository.

## Commands

Setup: `uv sync --all-groups` (or `--group dev` for tests/lint only, `--group packaging` for
the PyInstaller build tooling under `packaging/`).

```bash
uv run pytest                                   # full suite; hardware/supabase/display marks excluded by default
uv run pytest tests/unit/test_sounds.py::test_add_sound_is_idempotent_per_owner_and_content -v  # single test
uv run pytest -m supabase -v                    # RLS integration tests — needs `supabase start` first (Supabase CLI + Docker)
uv run pytest -m display -v                     # tests that spawn a real OS keyboard hook (global hotkeys)
uv run pytest -m hardware -v                    # tests that need a real audio device
uv run ruff check .
uv run mypy
```

On Linux, CI runs the suite under `xvfb-run -a` — `pynput` picks an X11 backend at import
time and raises even though Qt itself runs fine `offscreen` (see `tests/unit/conftest.py`).

Running the app:

```bash
uv run soundboard devices                       # list PortAudio devices, to find exact mic/cable names
uv run soundboard run --mic "..." --out "CABLE Input" --sound key=path.wav
uv run soundboard gui                            # PySide6 desktop UI
uv run soundboard auth signup|login|whoami|logout
uv run soundboard sounds add|list|edit|rm
uv run soundboard categories add
```

## Architecture

Layered, with the real-time audio core kept isolated from anything that does I/O:

- **`audio/`** — the real-time engine. Two independent PortAudio streams (input/output),
  each with its own clock, bridged by a `RingBuffer` (SPSC) plus a `DriftController` /
  `DriftResampler` that resample at a fractional rate to compensate clock drift between the
  two devices. `Mixer` sums the mic bus with active `Voice`s, applies ducking and a tanh
  limiter. `AudioEngine` orchestrates stream lifecycle, a command queue, and metrics. The
  callback-thread path (capture → ring buffer → drift-corrected read → mix → output) must
  never do I/O, logging, `queue.Queue`, or non-trivial allocation — numpy vector ops only.
  Internal format is fixed: 48kHz mono float32. Tested without hardware via the
  `AudioBackend` protocol + `FakeBackend` (simulated clock, deterministic).
- **`remote/`** — the Supabase-backed shared sound library. `RemoteClient` is the seam
  between library logic and the backend (`SupabaseRemoteClient` real,
  `FakeRemoteClient` in-memory for tests — the same role `AudioBackend` plays for audio).
  `auth.py` (session/login/profile bootstrap), `sounds.py` (CRUD + `resolve_pcm` for
  playback), `categories.py`. RLS enforces per-owner edit/delete; any authenticated user can
  read and add. Migrations live in `supabase/migrations/`.
- **`library/`** — `importer.py` decodes a new upload, hashes it (dedup key) and measures
  the gain that would bring its peak to the limiter ceiling; `cache.py` caches downloaded
  remote PCM on disk, keyed by sha256.
- **`ui/`** — the Qt Quick desktop GUI; the only package that imports Qt. `app.py` builds
  an `AppController` (`controller.py`), exposes it to QML as the `App` context property and
  loads `qml/Main.qml`. The controller owns the session, the engine lifecycle and the view
  the window shows; the QML is a dumb view over three testable models — `GridModel`
  (the clip grid), `EngineBridge` (polls peak/metrics/voice progress at ~30 Hz),
  `LibraryModel` (the remote library). All three are exercised headless, without rendering.
  Anything that can block (downloading a remote sound, uploading a dropped file) runs on a
  `QRunnable` (`download_worker.py`, `upload_worker.py`) with `finished`/`failed` signals —
  never on the Qt thread, and kept alive in a `self._active_*` set until its signal fires
  (`QThreadPool` doesn't keep Python's refcount alive across the thread hop); see
  `_worker_dispatch.py`, whose `is_live` check drops results belonging to a model that was
  retired while the work was in flight.
  - Python↔QML boundary: properties exposed to QML are camelCase (`userEmail`,
    `metricsText`), slots are snake_case and QML calls them as-is (`App.log_in(...)`).
  - Model role names avoid QML's own property names: `cellState` (not `state`, which
    collides with `Item.state`) and `cellColor` (not `color`, which collides with
    `Rectangle.color`).
  - Components under `qml/components/` use `property` with defaults, never
    `required property`, and never reference `App` — that is what lets the smoke test
    instantiate each one standalone with no context.
  - `qml_root()` in `app.py` resolves `qml/` in a checkout and under PyInstaller via
    `sys._MEIPASS`; the packaging specs must bundle the tree at `soundboard/ui/qml`.
    On Windows the same module registers the PySide6 package directory via
    `os.add_dll_directory` before any engine is built, or the QML plugin DLLs fail to
    resolve their sibling Qt DLLs.
- **`hotkeys.py`** (top-level, not under `ui/`) — global keyboard shortcuts behind a
  `HotkeyManager` protocol: `PynputHotkeyManager` (real) / `FakeHotkeyManager` (tests, no OS
  hook). Only module that imports `pynput`.
- **`cli.py`** — subcommands (`devices`, `run`, `auth`, `sounds`, `categories`, `gui`).
  Imports `soundboard.ui.app` lazily, only inside the `gui` branch, so headless CLI usage
  never pulls in PySide6.

Dependency direction: nothing under `audio/` may import `ui/`, `hotkeys.py`, `remote/`,
PySide6, or `pynput`. `ui/` and `hotkeys.py` may import `audio/`, `remote/`, `library/`.
`ui/` is the only importer of PySide6; `hotkeys.py` is the only importer of `pynput`.

## Project conventions

- Code, identifiers, docstrings, and commit messages: English. Product docs (README,
  design specs, plans): Spanish.
- No AI attribution anywhere — not in commit messages, not in PR titles/descriptions, not
  anywhere else in the repo. No `Co-Authored-By: Claude ...` trailer, no "Generated with
  Claude Code" footer, no emoji robot signature. Commits and PRs read as if written by the
  human author, full stop.
- Soft limit of ~300 lines per file — split when a change would push a file past that
  (e.g. `_worker_dispatch.py` is split out of `grid_model.py`, and `engine_factory.py` out
  of `controller.py`, for this reason).
- No silent failures — every error path is visible (a re-raised exception with a clear
  message, a toast in the GUI, a `QMessageBox` for the two fatal boot paths), never a
  swallowed exception or a default that masks the problem.
- Strict TDD: failing test first, minimal implementation, confirm it passes. Non-trivial
  features get a design spec at `docs/superpowers/specs/YYYY-MM-DD-<name>-design.md`
  (approved before planning) broken down into a step-by-step, bite-sized TDD plan at
  `docs/superpowers/plans/YYYY-MM-DD-<name>.md` — see the existing specs/plans in
  `docs/superpowers/` for the established format and the reasoning behind past decisions
  before writing a new one.
- No worktrees — one branch, one checkout. Don't create a `git worktree` for a feature; just
  branch off `master` in the normal working directory.
- Branch names use a slash, not a hyphen: `feature/<name>`, `fix/<name>`, off `master`
  directly (no `develop` branch — `release-please` automates versioning straight off
  `master`).
- Commit messages follow **Conventional Commits** (`feat:`, `fix:`, `docs:`, `chore:`,
  `build:`, `ci:`, ... — already the style used throughout the history; `release-please`
  depends on it to compute the next version).
- PRs merge via **squash** (the repo only allows squash merge — merge commit and rebase
  merge are disabled), and the branch is deleted automatically on merge
  (`delete_branch_on_merge` is on). Don't keep pushing new commits to an already-merged
  branch name expecting them to land later — they won't be tracked by any PR; open a new
  branch/PR instead.

## Testing

- Pytest marks deselected by default (run explicitly when relevant): `hardware` (real audio
  device), `supabase` (local Supabase stack via `supabase start`, needs the Supabase CLI +
  Docker), `display` (real OS keyboard hook; also needs Xvfb on headless Linux).
- `tests/unit/conftest.py` forces `QT_QPA_PLATFORM=offscreen` before the first
  `QApplication` is constructed — widget tests never need a real display (except
  `display`-marked ones).
- Every layer with a real external dependency sits behind a protocol with an in-memory
  double for tests: `AudioBackend`/`FakeBackend`, `RemoteClient`/`FakeRemoteClient`,
  `HotkeyManager`/`FakeHotkeyManager`.
