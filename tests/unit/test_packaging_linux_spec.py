import ast
from pathlib import Path


def test_linux_spec_is_valid_python_and_collects_keyring_backends() -> None:
    source = Path("packaging/linux/soundboard.spec").read_text()

    ast.parse(source)

    assert 'collect_submodules("keyring.backends")' in source
    assert 'name="soundboard"' in source
