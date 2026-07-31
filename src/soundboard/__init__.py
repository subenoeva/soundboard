"""Cross-platform soundboard."""

# Kept in step with pyproject.toml by release-please (see release-please-config.json).
# The self-updater reads this at runtime to decide whether a published release is newer,
# so it has to be the real version: importlib.metadata is not an option because
# PyInstaller onefile builds ship no dist-info.
__version__ = "0.4.0"  # x-release-please-version
