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
- **`effects/`** — the microphone effects chain, at the same layer as `audio/` and running
  on the same callback thread, so every rule above applies to it too. `chain.py` (the
  `Effect` protocol and `EffectChain`: ordered slots, in-place `process()`, per-block
  bypass, latency as the sum of the enabled blocks), `params.py` (`ParamSpec` — the
  parameter panel is generated from descriptors, never written per effect, which is what
  lets an arbitrary VST3 appear with working sliders), `pedal.py` (one pedalboard plugin
  behind the protocol) and `registry.py` (the built-in blocks, with defaults chosen for a
  voice rather than pedalboard's own). The engine swaps chains through the same command
  deque `play`/`stop_all` use and hands the outgoing one back through `drain_retired()`:
  releasing a plugin or an ONNX session on the callback thread is not allowed. Persistence
  is `ui/effects_store.py`, beside `ui_layout.json`; an entry that will not build is kept
  as a row carrying its error, never dropped. `vst_editor.py` is the plugin's own window:
  `show_editor()` blocks the thread it is called on and pedalboard only allows the main
  one, so it runs in a second process (`soundboard vst-editor <path>`, driven by
  `ui/vst_editor_process.py` over a QProcess) holding a second instance of the plugin.
  Parameters travel one way, as JSON lines on stdout, and land in the chain through the
  same funnel a slider uses; the parent closing stdin is what asks the window to go, and
  is the only cue that reaches a process sitting inside a plugin's message loop.
  `plugin.parameters` rebuilds its whole dictionary on every access (3.7 ms for a
  67-parameter plugin), so it is read once per poll rather than once per parameter, and
  `raw_state` — 0.01 ms — decides whether there is anything worth reading at all.
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
  - `log_out()` retires the engine stack through the same `_teardown_engine()` a device
    change uses: an engine, a poll timer or a global hotkey outliving the session is the
    bug that helper exists to prevent. `layout.json` deliberately survives a logout —
    the grid belongs to the machine and its team, not to whoever is signed in.
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
- **`updater/`** — the self-updater. `feed.py` is the seam (`ReleaseFeed` protocol,
  `HttpReleaseFeed` real / `FakeReleaseFeed` in-memory), reading `SHA256SUMS` +
  `SHA256SUMS.sig` through GitHub's `releases/latest/download/` redirect rather than the
  API: the version then sits inside the signed payload, there is no rate limit, and a
  release whose binaries are still building simply has no manifest yet (the CI `sign` job
  `needs` both builds). `signature.py` verifies Ed25519 against the key hardcoded in
  `keys.py` — hardcoded, not baked like `_baked_defaults.py`, so whoever controls CI
  secrets cannot swap it. The signature covers the manifest, and the manifest's SHA-256
  covers the binary, which keeps memory flat for a ~100MB asset. `install.py` swaps the
  running binary by renaming the old one aside first and the new one in second: Windows
  lets a running `.exe` be renamed but not deleted, so `os.replace()` onto it would fail.
  `locate.py` returns `None` outside a frozen build, which is the single switch that
  disables the feature for a checkout or a pip install; under an AppImage it returns
  `$APPIMAGE`, never `sys.executable` (that points inside the FUSE mount).
  `packaging/sign_release.py` is the producer side and is tested against this parser.
- **`packaging/`** — the build tooling both PyInstaller specs call before `Analysis`.
  `fetch_model.py` downloads the neural block's ONNX weights from a pinned Hugging Face
  revision and verifies the SHA-256 through `updater/download.py`, so the 10 MB file is
  not committed but the binary still ships it and works offline (`dpdfnet`'s own
  downloader checks nothing and defaults to the mutable `main` ref, which is why it is
  not used). `third_party_notices.py` generates `THIRD-PARTY-NOTICES` from the metadata
  of what is installed and ships it with the GPL-3.0, LGPL-3.0 and Apache-2.0 texts, the
  last two being what Apache-2.0 §4 and LGPL-3 §4(b) require the distribution to carry
  for CEVA's model and for Qt. Its header is also where the Windows `--onefile` build
  answers LGPL-3 §4 for Qt: the DLLs cannot be swapped inside a single executable, so
  the binary relies on §4(d)(0) — the whole program is GPL-3.0-or-later and its source
  and build are public, which is what makes relinking a modified Qt possible.
  Run either by hand from a checkout: `uv run python packaging/fetch_model.py`.
- **`hotkeys.py`** (top-level, not under `ui/`) — global keyboard shortcuts behind a
  `HotkeyManager` protocol: `PynputHotkeyManager` (real) / `FakeHotkeyManager` (tests, no OS
  hook). Only module that imports `pynput`.
- **`cli.py`** — subcommands (`devices`, `run`, `auth`, `sounds`, `categories`, `gui`, plus
  the hidden `vst-editor`, which is how the GUI reaches a plugin window: a frozen build
  has no interpreter beside it, so it runs itself again).
  Imports `soundboard.ui.app` lazily, only inside the `gui` branch, so headless CLI usage
  never pulls in PySide6.

Dependency direction: nothing under `audio/` or `effects/` may import `ui/`, `hotkeys.py`,
`remote/`, PySide6, or `pynput`. `ui/` and `hotkeys.py` may import `audio/`, `effects/`,
`remote/`, `library/`, `updater/`. `updater/` imports none of the others (it duplicates the
`settings.json` path helper rather than reach into `remote/`). `ui/` is the only importer
of PySide6; `hotkeys.py` is the only importer of `pynput`.

The GIL is a shared resource with a deadline on it. The chain runs inline in the audio
callback, and an ONNX inference releases the GIL for the compute and then has to take it
back before the block is due; if another thread is runnable at that moment the callback
waits for it, and on Windows that wait resolves no finer than ~15.6 ms against a 5.33 ms
budget. **So no background work in this process may occupy the GIL for long.** There are
two ways to break that and "it calls into C" only rules out one: a pure-Python loop
occupies it by running bytecode, and a long C call that never releases it (`json.loads`
over a multi-MB document is the standard example) occupies it just as effectively. What is
safe is C that releases the GIL and then blocks — `sf.read`, `soxr`, `hashlib`, socket
I/O, which is what every `QRunnable` here happens to do already. Anything else belongs in
a subprocess, which brings its own GIL. Measured, with the real model on the real cadence:
the app's own import path (`sf.read` + `soxr.resample`) is indistinguishable from an idle
machine, while a CPU-bound Python thread puts 139 of 258 blocks over budget. No knob fixes
it — the Windows timer-resolution mitigations were measured and rejected.

## Project conventions

- Everything committed to the repo is written in English: code, identifiers, docstrings,
  comments, commit messages, PR descriptions and the README.
- No AI attribution anywhere — not in commit messages, not in PR titles/descriptions, not
  anywhere else in the repo. No `Co-Authored-By: Claude ...` trailer, no "Generated with
  Claude Code" footer, no emoji robot signature. Commits and PRs read as if written by the
  human author, full stop.
- Soft limit of ~300 lines per file — split when a change would push a file past that
  (e.g. `_worker_dispatch.py` is split out of `grid_model.py`, and `engine_factory.py` and
  `session_actions.py` out of `controller.py`, for this reason).
- No silent failures — every error path is visible (a re-raised exception with a clear
  message, a toast in the GUI, a `QMessageBox` for the two fatal boot paths), never a
  swallowed exception or a default that masks the problem. Two deliberate exceptions,
  both commented where they live: `updater.install.sweep_stale` (a leftover that can't be
  deleted is retried next launch — nothing the user can act on) and the launch-time
  update check, which stays quiet on network failure while the manual check reports
  everything.
- Strict TDD: failing test first, minimal implementation, confirm it passes. For
  non-trivial features, agree on the design and a step-by-step plan before writing code —
  keep both out of the repo (the checkout carries code, tests and the README, nothing
  else). The reasoning behind a past decision belongs in a docstring or a comment next to
  the code it explains, where it can't drift out of sync.
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
  `QApplication` is constructed — Qt tests never need a real display (except
  `display`-marked ones). On Windows it also registers the PySide6 package directory
  via `os.add_dll_directory` so the QML plugin DLLs resolve.
- Every layer with a real external dependency sits behind a protocol with an in-memory
  double for tests: `AudioBackend`/`FakeBackend`, `RemoteClient`/`FakeRemoteClient`,
  `HotkeyManager`/`FakeHotkeyManager`, `ReleaseFeed`/`FakeReleaseFeed`. The HTTP paths in
  `updater/` are covered against `httpx.MockTransport`, so the real client code runs
  without a network.
- The updater's swap cannot be tested automatically — it needs a real frozen build. After
  changing anything under `updater/`, smoke-test on both platforms: rename over a live
  `.exe`, replace a mounted AppImage, restart into the new build, confirm the `.old` is
  swept on the next launch, and verify a genuine CI signature. `SOUNDBOARD_UPDATE_SIGNING_KEY`
  is a repository secret; its public half is hardcoded in `updater/keys.py`, and
  `packaging/sign_release.py --secret-key` prints the constant for a rotated key.
