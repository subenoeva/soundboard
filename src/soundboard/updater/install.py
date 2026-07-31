"""Swapping the running binary for a freshly downloaded one.

Windows allows a running .exe to be renamed — the loader opens it with
FILE_SHARE_DELETE — but not deleted, so ``os.replace(new, running)`` would fail: it has
to remove the destination. Hence two steps, in this order: move the old one aside, then
move the new one in. On Linux the old inode stays alive for as long as the AppImage is
mounted, so the same sequence works unchanged and both platforms share one code path.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
from pathlib import Path

STAGED_PREFIX = ".soundboard-update-"


def staged_path(binary: Path, tag: str) -> Path:
    """Where to download the release for ``tag`` before installing it.

    Next to the binary rather than in the system temp directory: a rename across volumes
    is not atomic, and on Windows the temp directory is often on another drive entirely.
    """
    return binary.with_name(f"{STAGED_PREFIX}{tag}.tmp")


def install(staged: Path, target: Path) -> None:
    """Move ``staged`` into ``target``, keeping the previous build alongside as ``.old``.

    Raises whatever the underlying rename raises, after restoring the previous build.
    """
    if sys.platform != "win32":
        # The staged file came from a plain write and carries no execute bit; an AppImage
        # without one is a file the desktop silently refuses to launch.
        os.chmod(staged, 0o755)

    # A random token rather than a fixed ".old": on Windows the previous build cannot be
    # deleted while the process is still running from it, so updating twice in one
    # session would collide on a fixed name.
    previous = target.with_name(f"{target.name}.{secrets.token_hex(4)}.old")

    os.replace(target, previous)
    try:
        os.replace(staged, target)
    except OSError:
        os.replace(previous, target)
        raise


def sweep_stale(binary: Path) -> None:
    """Delete leftovers from earlier updates: previous builds and interrupted downloads.

    Anchored to the exact binary name instead of a wider glob — the binary usually sits
    in the user's Downloads folder, where anything looser is a cheap way to delete a file
    that is not ours.

    A leftover that cannot be deleted (an antivirus still scanning it, or a previous
    build the running process is executing from) is left in place and retried on the next
    launch. This is the one place the project's no-silent-failures rule is set aside on
    purpose: there is no action for the user to take and the application works either
    way, so a toast would be pure noise.
    """
    directory = binary.parent
    stale = [*directory.glob(f"{binary.name}.*.old"), *directory.glob(f"{STAGED_PREFIX}*.tmp")]
    for leftover in stale:
        with contextlib.suppress(OSError):
            leftover.unlink()
