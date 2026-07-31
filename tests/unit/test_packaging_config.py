import json
import tomllib
from pathlib import Path


def test_packaging_dependency_group_declares_pyinstaller() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())

    assert data["dependency-groups"]["packaging"] == ["pyinstaller>=6.0"]


def test_release_please_bumps_the_package_version_constant() -> None:
    """Without this entry the x-release-please-version annotation in __init__.py is
    inert and the version the updater compares against silently rots."""
    config = json.loads(Path("release-please-config.json").read_text())

    assert "src/soundboard/__init__.py" in config["packages"]["."]["extra-files"]


def test_updater_dependencies_are_declared_directly() -> None:
    """httpx and cryptography arrive transitively through supabase. The updater's trust
    chain must not rest on supabase keeping the same HTTP and crypto stack."""
    data = tomllib.loads(Path("pyproject.toml").read_text())

    declared = {requirement.split(">=")[0] for requirement in data["project"]["dependencies"]}

    assert {"httpx", "cryptography"} <= declared
