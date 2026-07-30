import ast
from pathlib import Path


def test_windows_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/windows/soundboard.spec").read_text()

    ast.parse(source)  # PyInstaller execs .spec files as plain Python

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source
