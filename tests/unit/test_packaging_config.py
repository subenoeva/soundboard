import tomllib
from pathlib import Path


def test_packaging_dependency_group_declares_pyinstaller() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())

    assert data["dependency-groups"]["packaging"] == ["pyinstaller>=6.0"]
