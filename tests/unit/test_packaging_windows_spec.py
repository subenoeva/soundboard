import ast
import re
from pathlib import Path

SPEC_PATH = Path("packaging/windows/soundboard.spec")


def test_windows_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/windows/soundboard.spec").read_text()

    ast.parse(source)  # PyInstaller execs .spec files as plain Python

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source


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


def _literals(node: ast.AST) -> set[str]:
    return {
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _starred_names(node: ast.expr) -> set[str]:
    assert isinstance(node, ast.List), "the keyword must be a list literal to unpack into"
    return {
        elt.value.id
        for elt in node.elts
        if isinstance(elt, ast.Starred) and isinstance(elt.value, ast.Name)
    }


def _statement_index(tree: ast.Module, func: str) -> int:
    """Position in the spec's top-level body of the statement calling ``func``."""
    for index, statement in enumerate(tree.body):
        for node in ast.walk(statement):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == func
            ):
                return index
    raise AssertionError(f"the spec never calls {func}()")


def _assigned_name(tree: ast.Module, func: str) -> str:
    """The variable a top-level ``name = func(...)`` binds."""
    statement = tree.body[_statement_index(tree, func)]
    assert isinstance(statement, ast.Assign), f"{func}() must bind its result"
    target = statement.targets[0]
    assert isinstance(target, ast.Name)
    return target.id


def _data_pairs(call: ast.Call) -> list[tuple[ast.expr, ast.expr]]:
    return [
        (elt.elts[0], elt.elts[1])
        for elt in ast.walk(_keyword_value(call, "datas"))
        if isinstance(elt, ast.Tuple) and len(elt.elts) == 2
    ]


def test_spec_bundles_the_verified_model_where_the_neural_effect_looks_for_it() -> None:
    """soundboard.effects.neural.default_model_path() resolves
    sys._MEIPASS/soundboard/effects/models/, and the file bundled there has to be the
    one ensure_model() hashed — not a path literal that could point anywhere."""
    tree = ast.parse(SPEC_PATH.read_text())
    model = _assigned_name(tree, "ensure_model")

    matched = any(
        model in _names(src) and _path_segments(dest) == ["soundboard", "effects", "models"]
        for src, dest in _data_pairs(_analysis_call(SPEC_PATH.read_text()))
    )
    assert matched, "datas must carry the fetched ONNX at 'soundboard/effects/models'"


def test_the_model_is_fetched_before_analysis_reads_the_datas() -> None:
    tree = ast.parse(SPEC_PATH.read_text())

    assert _statement_index(tree, "ensure_model") < _statement_index(tree, "Analysis")


def test_the_notices_are_generated_before_analysis_and_bundled_at_the_root() -> None:
    tree = ast.parse(SPEC_PATH.read_text())
    notices = _assigned_name(tree, "write_notices")

    assert _statement_index(tree, "write_notices") < _statement_index(tree, "Analysis")
    datas = _keyword_value(_analysis_call(SPEC_PATH.read_text()), "datas")
    assert notices in _starred_names(datas), (
        "the generated THIRD-PARTY-NOTICES and Apache-2.0 text must be unpacked into datas"
    )


def test_spec_collects_the_pedalboard_and_onnxruntime_runtimes() -> None:
    """pedalboard and onnxruntime are extension modules whose libraries PyInstaller's
    module graph does not reach on its own: pedalboard_native is a separate top-level
    .pyd, and onnxruntime loads its provider DLLs from onnxruntime/capi at runtime."""
    source = SPEC_PATH.read_text()
    tree = ast.parse(source)
    call = _analysis_call(source)

    collected = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "collect_all"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert {"pedalboard", "onnxruntime"} <= collected

    for keyword in ("binaries", "datas", "hiddenimports"):
        starred = _starred_names(_keyword_value(call, keyword))
        assert {"pedalboard", "onnxruntime"} <= {name.split("_")[0] for name in starred}, (
            f"{keyword} must unpack what collect_all() returned for both packages"
        )

    assert "pedalboard_native" in _literals(_keyword_value(call, "hiddenimports")), (
        "pedalboard imports its .pyd as a separate top-level module"
    )


def test_the_existing_bundle_contents_survive_the_new_entries() -> None:
    source = SPEC_PATH.read_text()
    call = _analysis_call(source)

    hidden = _literals(_keyword_value(call, "hiddenimports"))
    assert {"PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2"} <= hidden
    assert 'collect_submodules("keyring.backends")' in source
    assert 'collect_submodules("pynput")' in source
    assert "prune(a.binaries)" in source and "prune(a.datas, verify=False)" in source
