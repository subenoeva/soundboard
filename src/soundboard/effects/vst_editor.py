"""Runs one VST3's own editor window in a process of its own.

``show_editor()`` blocks the thread it is called on and pedalboard only allows the
main thread, so the app cannot host it: the Qt event loop would stop for as long as
the plugin window is open, and the window can stay open for minutes. A second
process has a main thread nobody else wants, and — the reason that matters here —
its own GIL, which is what keeps a plugin's message loop away from the audio
callback's deadline (see AGENTS.md).

The process is deliberately one-way. It loads a *second* instance of the plugin,
shows its window, and reports parameter changes on stdout as JSON lines. The
instance in the chain is still the only one making sound and never learns this
process exists: values reach it through the same path a slider uses, which is also
what keeps clamping and persistence in one place.

Run by ``soundboard vst-editor <plugin path>``, with the parameters to start from
sent as one JSON object on stdin.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Mapping
from typing import Any

from pedalboard import load_plugin  # type: ignore[attr-defined]

from soundboard.effects.params import ParamValue
from soundboard.effects.vst import plugin_params

POLL_SECONDS = 0.05
"""How often the window is asked what its knobs are at. Fast enough to tune by ear,
and far too small a read to matter next to a plugin's own redraw."""

Sink = Callable[[dict[str, ParamValue]], None]


def watch(plugin: Any, sink: Sink, stop: threading.Event, *, poll: float) -> None:
    """Report every parameter that moves, until ``stop`` is set.

    ``raw_state`` is the plugin's own state blob and costs 0.01 ms against the
    4.5 ms a full parameter read costs, so it decides whether there is anything to
    read at all: a window sitting open with nobody touching it should not keep a
    core busy on the machine an audio callback is due on every 5.33 ms.
    """
    previous = plugin_params(plugin)
    state = _state(plugin)
    while not stop.wait(poll):
        current_state = _state(plugin)
        if current_state is not None and current_state == state:
            continue
        state = current_state
        current = plugin_params(plugin)
        changed = {
            name: value for name, value in current.items() if previous.get(name) != value
        }
        if changed:
            sink(changed)
            previous = current


def _state(plugin: Any) -> bytes | None:
    """The plugin's state blob, or None if it does not offer one to compare."""
    try:
        return bytes(plugin.raw_state)
    except Exception:
        # Not every plugin implements it, and a plugin that raises here is saying
        # exactly one thing: read the parameters every time, like this used to.
        return None


def run_editor(
    plugin: Any,
    params: Mapping[str, ParamValue],
    sink: Sink,
    *,
    poll: float = POLL_SECONDS,
    close: threading.Event | None = None,
) -> None:
    """Show ``plugin``'s window and report its knobs until the user closes it.

    ``close`` is pedalboard's own way out of the window's message loop, and the
    only one that does not involve the user: whoever sets it takes the window down.
    """
    for name, value in params.items():
        setattr(plugin, name, value)
    stop = threading.Event()
    watcher = threading.Thread(
        target=watch, args=(plugin, sink, stop), kwargs={"poll": poll}, daemon=True
    )
    watcher.start()
    try:
        plugin.show_editor(close)
    finally:
        stop.set()
        watcher.join()
    # The last move before the window closed can fall between two polls, and the
    # chain would then keep playing a value the user cannot see any more.
    sink(plugin_params(plugin))


def main(
    argv: list[str] | None = None,
    *,
    loader: Callable[[str], Any] = load_plugin,
) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("error: no VST3 path given", file=sys.stderr)
        return 1
    params = _initial_params()
    try:
        plugin = loader(argv[0])
    except Exception as exc:  # process boundary: the parent shows this in a toast
        print(f"error: {exc}", file=sys.stderr)
        return 1
    close = threading.Event()
    threading.Thread(target=_close_on_eof, args=(close,), daemon=True).start()
    run_editor(plugin, params, _emit, close=close)
    return 0


def _initial_params() -> dict[str, ParamValue]:
    """What the chain's instance is set to, as the parent wrote it on stdin."""
    raw = sys.stdin.readline().strip()
    if not raw:
        return {}
    payload: dict[str, Any] = json.loads(raw)
    params: dict[str, ParamValue] = payload.get("params", {})
    return params


def _close_on_eof(close: threading.Event) -> None:
    """The parent letting go of stdin is how it asks for the window to close.

    It has no other way in: this process is sitting inside the plugin's own
    message loop, and killing it would take the last thing the user did with it.
    """
    sys.stdin.read()
    close.set()


def _emit(params: Mapping[str, ParamValue]) -> None:
    # A plugin parameter can sit at -inf (a mix control at silence), which json
    # writes as -Infinity: not valid JSON, and read back by the only reader this
    # has — Python's own json, on the other end of the pipe. Verified against the
    # frozen --windowed build, where stdout is a pipe rather than a console.
    print(json.dumps({"params": dict(params)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    sys.exit(main())
