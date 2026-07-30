import ast
import ctypes.util
import sys
from pathlib import Path
from typing import Any

import pytest

HOOK_PATH = Path("packaging/linux/rt_hook_portaudio.py")


def test_hook_defines_find_library_and_reassigns_ctypes_util() -> None:
    tree = ast.parse(HOOK_PATH.read_text())

    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert "find_library" in functions

    assigned = [
        ast.unparse(target)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
    ]
    assert "ctypes.util.find_library" in assigned


def test_hook_returns_the_bundled_portaudio_and_delegates_every_other_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Executing the hook reassigns ctypes.util.find_library for the whole process, so
    the original is saved and restored explicitly — monkeypatch cannot undo a rebinding
    it did not perform itself."""
    bundled = tmp_path / "libportaudio.so.2"
    bundled.write_bytes(b"")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    def stub(name: str) -> str | None:
        return f"stub:{name}"

    original = ctypes.util.find_library
    monkeypatch.setattr(ctypes.util, "find_library", stub)
    try:
        namespace: dict[str, Any] = {"__name__": "rt_hook_portaudio"}
        exec(compile(HOOK_PATH.read_text(), str(HOOK_PATH), "exec"), namespace)

        assert ctypes.util.find_library("portaudio") == str(bundled)
        assert ctypes.util.find_library("something-else") == "stub:something-else"

        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(sys, "_MEIPASS", str(empty), raising=False)
        assert ctypes.util.find_library("portaudio") == "stub:portaudio"
    finally:
        ctypes.util.find_library = original


def test_hook_leaves_the_real_find_library_in_place_for_the_rest_of_the_suite() -> None:
    assert ctypes.util.find_library.__module__ == "ctypes.util"
