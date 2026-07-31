"""Where the replaceable binary lives, and whether we are allowed to replace it.

Returning None from ``installed_binary`` is what switches the whole feature off for a
source checkout or a pip install, in one place, instead of scattering "are we frozen?"
checks through the UI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from soundboard.updater.errors import NotWritable, UpdateError
from soundboard.updater.manifest import expected_asset_names


def installed_binary() -> Path | None:
    """The file a downloaded release should replace, or None if there is not one."""
    if not getattr(sys, "frozen", False):
        return None

    if sys.platform.startswith("linux"):
        # Under an AppImage, sys.executable points inside the FUSE mount
        # (/tmp/.mount_XXXX/...), which disappears when the process exits. APPIMAGE is
        # the outer file, and the only thing worth replacing. Without it we are running
        # from an extracted AppDir and there is no single file to swap.
        appimage = os.environ.get("APPIMAGE")
        return Path(appimage) if appimage else None

    return Path(sys.executable)


def ensure_writable(binary: Path) -> None:
    """Raise ``NotWritable`` unless the binary's directory accepts writes.

    The directory, not the file: both renames happen there, and a read-only executable
    in a writable folder can still be moved aside. Called before any download so a
    binary parked somewhere privileged fails immediately instead of after 100MB.
    """
    directory = binary.parent
    if not os.access(directory, os.W_OK):
        raise NotWritable(
            f"no write permission in {directory} — move the application to a folder you "
            f"own, or run it as an administrator"
        )


def current_asset_name(tag: str) -> str:
    """The release asset matching the running platform."""
    windows, linux = expected_asset_names(tag)
    if sys.platform == "win32":
        return windows
    if sys.platform.startswith("linux"):
        return linux
    raise UpdateError(f"no release asset is built for {sys.platform}")
