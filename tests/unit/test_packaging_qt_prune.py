import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_qt_prune() -> ModuleType:
    """Loaded by path: the repo's packaging/ directory is shadowed on sys.path by the
    installed `packaging` distribution, so a plain import resolves to the wrong one."""
    spec = importlib.util.spec_from_file_location(
        "soundboard_qt_prune", Path("packaging/qt_prune.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qt_prune = _load_qt_prune()


def _entry(dest: str) -> tuple[str, str, str]:
    return (dest, f"/wheel/{dest}", "BINARY")


def test_drops_the_webengine_library_on_windows() -> None:
    kept = qt_prune.prune([_entry(r"PySide6\Qt6WebEngineCore.dll")], verify=False)

    assert kept == []


def test_drops_the_webengine_library_on_linux() -> None:
    """Linux ships the same library as libQt6WebEngineCore.so.6 — same prefix once the
    `lib` prefix is stripped, which is why matching is not a plain basename compare."""
    kept = qt_prune.prune(
        [_entry("PySide6/Qt/lib/libQt6WebEngineCore.so.6")], verify=False
    )

    assert kept == []


@pytest.mark.parametrize(
    "dest",
    [
        r"PySide6\Qt6Core.dll",
        r"PySide6\Qt6Gui.dll",
        r"PySide6\Qt6Widgets.dll",
        r"PySide6\Qt6Quick.dll",
        r"PySide6\Qt6Qml.dll",
        r"PySide6\Qt6QuickControls2.dll",
        r"PySide6\Qt6QuickControls2Basic.dll",
        r"PySide6\Qt6QuickControls2BasicStyleImpl.dll",
        r"PySide6\Qt6QuickControls2Impl.dll",
        r"PySide6\Qt6QuickTemplates2.dll",
        r"PySide6\Qt6QuickLayouts.dll",
        r"PySide6\Qt6Network.dll",
        r"PySide6\Qt6OpenGL.dll",
        r"PySide6\Qt6Svg.dll",
        "PySide6/Qt/lib/libQt6Core.so.6",
    ],
)
def test_keeps_the_libraries_the_app_actually_loads(dest: str) -> None:
    """QtQuick.Controls.Basic plus the QMessageBox/tray widgets path — see the module
    docstring for why each of these has to survive."""
    assert qt_prune.prune([_entry(dest)], verify=False) == [_entry(dest)]


def test_keeps_non_qt_binaries_untouched() -> None:
    entries = [_entry(r"numpy.libs\libscipy_openblas64_.dll"), _entry("python313.dll")]

    assert qt_prune.prune(entries, verify=False) == entries


def test_drops_unused_qml_module_trees() -> None:
    entries = [
        _entry(r"PySide6\qml\QtWebEngine\qtwebenginequickplugin.dll"),
        _entry(r"PySide6\qml\QtQuick\VirtualKeyboard\qmldir"),
        _entry(r"PySide6\qml\QtQuick\Controls\Material\qmldir"),
        _entry("PySide6/Qt/qml/QtQuick3D/qmldir"),
    ]

    assert qt_prune.prune(entries, verify=False) == []


@pytest.mark.parametrize(
    "dest",
    [
        r"PySide6\qml\QtQuick\qtquick2plugin.dll",
        r"PySide6\qml\QtQuick\Controls\qmldir",
        r"PySide6\qml\QtQuick\Controls\Basic\qmldir",
        r"PySide6\qml\QtQuick\Layouts\qquicklayoutsplugin.dll",
        r"PySide6\qml\QtQuick\Window\qmldir",
        r"PySide6\qml\QtQml\qmlplugin.dll",
        "PySide6/Qt/qml/QtQuick/Controls/Basic/qmldir",
    ],
)
def test_keeps_the_qml_modules_main_qml_imports(dest: str) -> None:
    assert qt_prune.prune([_entry(dest)], verify=False) == [_entry(dest)]


def test_a_pruned_style_does_not_take_the_basic_style_with_it() -> None:
    """`Qt6QuickControls2Material` must not match `Qt6QuickControls2MaterialStyleImpl`'s
    sibling `Qt6QuickControls2Basic` — prefix matching is easy to get subtly wrong."""
    basic = _entry(r"PySide6\Qt6QuickControls2Basic.dll")
    material = _entry(r"PySide6\Qt6QuickControls2Material.dll")

    assert qt_prune.prune([basic, material], verify=False) == [basic]


def test_verify_raises_when_a_load_bearing_pattern_matches_nothing() -> None:
    """The whole point of the module: if a Qt release renames or moves the heavy
    libraries, the build has to fail loudly instead of silently shipping them again."""
    with pytest.raises(qt_prune.PruneError) as excinfo:
        qt_prune.prune([_entry(r"PySide6\Qt6Core.dll")])

    assert "qt6webengine" in str(excinfo.value)


def test_verify_passes_once_every_required_pattern_matched() -> None:
    entries = [_entry(rf"PySide6\{name}.dll") for name in qt_prune.REQUIRED_PREFIXES]
    entries.append(_entry(r"PySide6\Qt6Core.dll"))

    assert qt_prune.prune(entries) == [_entry(r"PySide6\Qt6Core.dll")]


def _qml_imports() -> set[str]:
    imports: set[str] = set()
    for path in Path("src/soundboard/ui/qml").rglob("*.qml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") and not stripped.startswith('import "'):
                imports.add(stripped.removeprefix("import ").split()[0])
    return imports


def test_every_qml_module_the_project_imports_survives_the_prune() -> None:
    """The prune's real failure mode: someone adds `import QtQuick.Shapes` to a .qml and
    the frozen build dies at load time with a module the checkout has and the exe does
    not. This catches that in CI instead of in a release binary."""
    found = _qml_imports()
    assert found, "no QML imports found — did the qml/ tree move?"

    for module in sorted(found):
        dest = "PySide6/qml/" + module.replace(".", "/") + "/qmldir"
        assert qt_prune.prune([_entry(dest)], verify=False) == [_entry(dest)], (
            f"{module} is imported by the app's QML but packaging/qt_prune.py drops it "
            f"from the bundle"
        )
