"""Runs the VST3 editor process and turns its output into Qt signals.

The window itself belongs to ``effects/vst_editor.py``, which runs in a process of
its own because ``show_editor()`` blocks the main thread it is called on. Here is
the other end of that pipe: a QProcess, so the reading happens on the Qt thread
through ``readyReadStandardOutput`` and nothing in this app has to wait.

The parameters travel on stdin rather than on the command line — a plugin can
report hundreds of them and Windows caps a command line at 32k characters.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, Signal

from soundboard.effects.params import ParamValue

TERMINATE_MS = 3_000
"""How long a closing editor is given to take its window down before it is killed."""


def editor_command() -> tuple[str, list[str]]:
    """The command that opens a plugin window, frozen or from a checkout.

    A frozen build has no interpreter beside it, so it re-runs itself with the
    subcommand — the same trick ``devices`` is reached by.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ["vst-editor"]
    return sys.executable, ["-m", "soundboard", "vst-editor"]


class LineReader:
    """Turns arbitrary stdout chunks into the parameter updates they carry."""

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, chunk: bytes) -> list[dict[str, ParamValue]]:
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        return [update for line in lines if (update := _parse(line)) is not None]


class VstEditor(QObject):
    """One plugin window: at most one process, alive between ``open`` and ``closed``."""

    changed = Signal(dict)
    closed = Signal()
    failed = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        command: tuple[str, list[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._command = command
        self._process: QProcess | None = None
        self._reader = LineReader()

    @property
    def is_open(self) -> bool:
        return self._process is not None

    def open(self, path: Path | str, params: Mapping[str, ParamValue]) -> None:
        """Start the window for ``path``, with the knobs the chain is playing."""
        if self._process is not None:
            raise RuntimeError("this effect already has an editor window open")
        program, arguments = self._command or editor_command()
        process = QProcess(self)
        self._process = process
        self._reader = LineReader()
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        process.start(program, [*arguments, str(path)])
        # One line, and the channel stays open: closing it is how `close` below
        # asks for the window to go, so it cannot double as "here are the values".
        process.write(json.dumps({"params": dict(params)}).encode("utf-8") + b"\n")

    def close(self) -> None:
        """Ask the window to go away. Nothing to do if it already has.

        Measured against a real plugin: ``terminate()`` does not close a JUCE
        window, so this used to sit for the whole grace period and then kill the
        process, losing whatever the user had set in it. Letting go of stdin is
        what the editor process is waiting for, and it reports its last state on
        the way out; the kill is only for a window that ignores the cue.
        """
        process = self._process
        if process is None:
            return
        process.closeWriteChannel()
        if not process.waitForFinished(TERMINATE_MS):
            process.kill()

    def _read(self) -> None:
        process = self._process
        if process is None:
            return
        for update in self._reader.feed(bytes(process.readAllStandardOutput().data())):
            self.changed.emit(update)

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        self._read_last(process)
        if code == 0 or status == QProcess.ExitStatus.CrashExit:
            # A terminated editor is a closed editor: the user asked for it, or the
            # app is going down and took the window with it.
            self.closed.emit()
            return
        error = bytes(process.readAllStandardError().data())
        message = error.decode("utf-8", "replace").strip()
        self.failed.emit(message or f"the plugin window exited with code {code}")

    def _read_last(self, process: QProcess) -> None:
        """The state at the moment of closing arrives with, or just before, the exit."""
        for update in self._reader.feed(bytes(process.readAllStandardOutput().data())):
            self.changed.emit(update)

    def _error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return  # every other error is reported by `finished` with its exit code
        self._process = None
        self.failed.emit("the plugin window could not be started")


def _parse(line: bytes) -> dict[str, ParamValue] | None:
    """One output line, or None when it is not one of ours.

    Deliberately quiet: plugins log to stdout whenever they feel like it, and a
    JUCE banner landing in this pipe is not an error anyone can act on.
    """
    text = line.strip()
    if not text:
        return None
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("params"), dict):
        return None
    params: dict[str, ParamValue] = payload["params"]
    return params
