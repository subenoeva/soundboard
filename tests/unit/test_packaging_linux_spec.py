import ast
import re
from pathlib import Path

SPEC_PATH = Path("packaging/linux/soundboard.spec")


def test_linux_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/linux/soundboard.spec").read_text()

    ast.parse(source)

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source


def test_linux_spec_registers_the_portaudio_runtime_hook() -> None:
    source = Path("packaging/linux/soundboard.spec").read_text()

    ast.parse(source)

    assert "rt_hook_portaudio.py" in source


def _analysis_call(source: str) -> ast.Call:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Analysis"
        ):
            return node
    raise AssertionError("Analysis(...) call not found in spec")


def _keyword_value(call: ast.Call, name: str) -> ast.expr:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    raise AssertionError(f"Analysis(...) has no '{name}' keyword")


def _path_segments(node: ast.AST) -> list[str]:
    """Flatten every string literal under ``node`` into path segments.

    Handles both ``os.path.join(...)`` calls (one string literal per path
    component) and a single literal that already contains separators, on
    either OS's separator style, so the assertion doesn't care whether the
    spec builds the path with ``os.path.join`` or a plain string.
    """
    segments: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            segments.extend(part for part in re.split(r"[\\/]+", n.value) if part)
    return segments


def test_spec_bundles_qml_source_dir_at_soundboard_ui_qml() -> None:
    source = SPEC_PATH.read_text()
    call = _analysis_call(source)
    datas = _keyword_value(call, "datas")

    pairs = [
        (elt.elts[0], elt.elts[1])
        for elt in ast.walk(datas)
        if isinstance(elt, ast.Tuple) and len(elt.elts) == 2
    ]
    assert pairs, "datas has no (source, destination) entries"

    matched = any(
        _path_segments(src)[-3:] == ["soundboard", "ui", "qml"]
        and "src" in _path_segments(src)
        and _path_segments(dest) == ["soundboard", "ui", "qml"]
        for src, dest in pairs
    )
    assert matched, (
        "datas must bundle src/soundboard/ui/qml at destination 'soundboard/ui/qml' "
        "(qml_root() resolves sys._MEIPASS/soundboard/ui/qml when frozen)"
    )


def test_spec_keeps_xlib_datas_when_adding_qml() -> None:
    source = SPEC_PATH.read_text()
    call = _analysis_call(source)
    datas = _keyword_value(call, "datas")
    assert isinstance(datas, ast.List), "datas must be a list literal"

    starred_names = {
        elt.value.id
        for elt in datas.elts
        if isinstance(elt, ast.Starred) and isinstance(elt.value, ast.Name)
    }
    assert "xlib_datas" in starred_names, (
        "adding the QML datas entry must not drop the existing xlib_datas unpacking"
    )


def test_spec_hiddenimports_includes_qtquick_modules() -> None:
    source = SPEC_PATH.read_text()
    call = _analysis_call(source)
    hiddenimports = _keyword_value(call, "hiddenimports")

    literals = {
        n.value
        for n in ast.walk(hiddenimports)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    required = {"PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2"}
    assert required <= literals, f"missing hiddenimports: {required - literals}"


def test_spec_hiddenimports_names_the_x11_backends_explicitly() -> None:
    """collect_submodules("pynput") imports the package to enumerate it, and on a
    headless build runner `import pynput.keyboard` raises before the X11 backend is ever
    seen, so the AppImage shipped without it and died on launch under a real X server:
    `No module named 'pynput.keyboard._xorg'`. Naming them removes the dependency on
    what the build machine happens to have."""
    source = SPEC_PATH.read_text()
    call = _analysis_call(source)
    hiddenimports = _keyword_value(call, "hiddenimports")

    literals = {
        n.value
        for n in ast.walk(hiddenimports)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    required = {
        "pynput.keyboard._xorg",
        "pynput.mouse._xorg",
        "pynput._util.xorg",
        "pynput._util.xorg_keysyms",
    }
    assert required <= literals, f"missing hiddenimports: {required - literals}"
