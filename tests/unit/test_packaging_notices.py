import importlib.metadata
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_notices() -> ModuleType:
    """Loaded by path: the repo's packaging/ directory is shadowed on sys.path by the
    installed `packaging` distribution, so a plain import resolves to the wrong one."""
    spec = importlib.util.spec_from_file_location(
        "soundboard_third_party_notices", Path("packaging/third_party_notices.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


notices = _load_notices()
APACHE_NAME = notices.APACHE_NAME
APACHE_SOURCE = notices.APACHE_SOURCE
NOTICES_NAME = notices.NOTICES_NAME
Notice = notices.Notice
collect = notices.collect
installed_notices = notices.installed_notices
render = notices.render
write_notices = notices.write_notices


def test_every_redistributed_dependency_is_listed_with_its_installed_version() -> None:
    """The versions and licences come from the metadata of what is actually installed,
    so a dependency bump cannot leave the notices claiming the old terms."""
    listed = {notice.name.lower(): notice for notice in installed_notices()}

    for name in ("pedalboard", "onnxruntime", "pyside6", "numpy", "httpx"):
        assert name in listed, f"{name} is redistributed but not in the notices"
        assert listed[name].version == importlib.metadata.version(name)
        assert listed[name].license.strip()


def test_transitive_dependencies_are_listed_too() -> None:
    """PyInstaller bundles the whole closure, not just the names in pyproject.toml."""
    listed = {notice.name.lower() for notice in installed_notices()}

    assert "certifi" in listed
    assert "shiboken6" in listed


def test_the_build_only_tooling_is_not_listed_as_redistributed() -> None:
    listed = {notice.name.lower() for notice in installed_notices()}

    assert "pyinstaller" not in listed
    assert "pytest" not in listed


def test_licences_are_read_from_metadata_rather_than_guessed() -> None:
    listed = {notice.name.lower(): notice for notice in installed_notices()}

    assert "GPL" in listed["pedalboard"].license
    assert "MIT" in listed["onnxruntime"].license
    assert "LGPL" in listed["pyside6"].license


def test_the_rendered_notices_carry_the_dpdfnet_attribution() -> None:
    text = render(collect())

    assert "DPDFNet" in text
    assert "Copyright 2025 CEVA" in text
    assert "Apache-2.0" in text
    assert "dpdfnet2_48khz_hr.onnx" in text
    assert "https://github.com/ceva-ip/DPDFNet" in text
    assert APACHE_NAME in text, "the notices must point at the licence text shipped beside them"


def test_the_rendered_notices_name_every_collected_entry() -> None:
    entries = [
        Notice(name="Example", version="1.2.3", license="MIT", url="https://example.invalid"),
        Notice(name="Another", version="0.1", license="BSD-3-Clause", url=""),
    ]

    text = render(entries)

    assert "Example 1.2.3" in text
    assert "MIT" in text
    assert "https://example.invalid" in text
    assert "Another 0.1" in text
    assert "BSD-3-Clause" in text


def test_the_repository_carries_the_full_apache_licence_text() -> None:
    """Apache-2.0 §4 wants the licence shipped, not cited: the whole text, taken from
    the DPDFNet repository rather than paraphrased."""
    text = APACHE_SOURCE.read_text(encoding="utf-8")

    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in text
    assert "END OF TERMS AND CONDITIONS" in text
    assert "9. Accepting Warranty or Additional Liability" in text
    assert len(text) > 10_000


def test_writing_the_notices_produces_both_files_for_the_bundle_root(tmp_path: Path) -> None:
    datas = write_notices(tmp_path / "notices")

    destinations = {Path(source).name: destination for source, destination in datas}
    assert destinations == {NOTICES_NAME: ".", APACHE_NAME: "."}
    for source, _ in datas:
        assert Path(source).is_file()


def test_the_written_licence_is_the_full_text_byte_for_byte(tmp_path: Path) -> None:
    write_notices(tmp_path / "notices")

    written = (tmp_path / "notices" / APACHE_NAME).read_bytes()
    assert written == APACHE_SOURCE.read_bytes()


def test_the_written_notices_list_the_installed_dependencies(tmp_path: Path) -> None:
    write_notices(tmp_path / "notices")

    text = (tmp_path / "notices" / NOTICES_NAME).read_text(encoding="utf-8")
    assert f"pedalboard {importlib.metadata.version('pedalboard')}" in text
    assert f"onnxruntime {importlib.metadata.version('onnxruntime')}" in text
    assert "DPDFNet" in text


def test_a_missing_licence_text_fails_the_build_rather_than_shipping_without_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notices, "APACHE_SOURCE", tmp_path / "gone.txt")

    with pytest.raises(FileNotFoundError):
        write_notices(tmp_path / "notices")
