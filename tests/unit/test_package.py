import tomllib
from pathlib import Path


def test_package_version_matches_pyproject() -> None:
    """The updater compares __version__ against the latest release, so a drift between
    it and the version release-please tagged would offer an update forever."""
    import soundboard

    declared = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]

    assert soundboard.__version__ == declared


def test_audio_subpackage_is_importable() -> None:
    import soundboard.audio  # noqa: F401
