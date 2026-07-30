import ast
from pathlib import Path


def test_linux_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/linux/soundboard.spec").read_text()

    ast.parse(source)

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source


def test_linux_spec_registers_the_portaudio_runtime_hook() -> None:
    source = Path("packaging/linux/soundboard.spec").read_text()

    ast.parse(source)

    assert "rt_hook_portaudio.py" in source
