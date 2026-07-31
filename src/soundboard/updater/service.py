"""The update flow, assembled: check the feed, download, verify, swap.

Kept free of Qt so the whole decision path — which release is newer, whether this build
can update itself at all, what happens when the swap fails — is exercised headlessly.
The Qt layer only moves this off the GUI thread and renders the result.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import platformdirs

from soundboard import __version__
from soundboard.updater.download import ProgressCallback, fetch
from soundboard.updater.feed import HttpReleaseFeed, ReleaseFeed
from soundboard.updater.install import install, staged_path, sweep_stale
from soundboard.updater.locate import current_asset_name, ensure_writable, installed_binary

__all__ = [
    "AvailableUpdate",
    "UpdateService",
    "automatic_check_enabled",
    "relaunch",
    "sweep_stale",
]

_DISABLE_ENV = "SOUNDBOARD_NO_UPDATE_CHECK"


@dataclass(frozen=True)
class AvailableUpdate:
    tag: str
    version: str
    asset_name: str
    asset_url: str
    digest: str
    binary: Path


class UpdateService:
    def __init__(
        self,
        feed: ReleaseFeed | None = None,
        current_version: str = __version__,
        client: httpx.Client | None = None,
    ) -> None:
        self._feed = feed or HttpReleaseFeed()
        self._current_version = current_version
        self._client = client

    def is_supported(self) -> bool:
        """False for a source checkout or a pip install, where there is no single file
        to replace."""
        return installed_binary() is not None

    def check(self) -> AvailableUpdate | None:
        """The release worth installing, or None if there is not one.

        None covers all three quiet cases — this build cannot update itself, no release
        is published yet, the published one is not newer. Anything that went *wrong*
        raises instead, so a failure never reads as "up to date".
        """
        binary = installed_binary()
        if binary is None:
            return None

        manifest = self._feed.latest()
        if manifest is None or not manifest.is_newer_than(self._current_version):
            return None

        asset_name = current_asset_name(manifest.tag)
        return AvailableUpdate(
            tag=manifest.tag,
            version=".".join(str(part) for part in manifest.version),
            asset_name=asset_name,
            asset_url=self._feed.asset_url(manifest.tag, asset_name),
            digest=manifest.digest_for(asset_name),
            binary=binary,
        )

    def apply(self, update: AvailableUpdate, progress: ProgressCallback | None = None) -> None:
        """Download, verify and install ``update``. The caller restarts afterwards."""
        # First, and before any network: a binary parked somewhere unwritable should cost
        # the user a second, not a full download.
        ensure_writable(update.binary)

        staged = staged_path(update.binary, update.tag)
        fetch(update.asset_url, staged, update.digest, progress=progress, client=self._client)
        install(staged, update.binary)


def relaunch(binary: Path, spawn: Callable[..., Any] | None = None) -> None:
    """Start ``binary`` detached from this process. The caller exits afterwards.

    Starting before exiting is safe: by this point the path holds the new build, so the
    old process and the new one are running different files. Detached so the new
    instance does not die with the shell or process group that owned the old one.
    """
    spawn = spawn or subprocess.Popen
    if sys.platform == "win32":
        spawn(
            [str(binary)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        spawn([str(binary)], start_new_session=True, close_fds=True)


def _default_settings_path() -> Path:
    # The same file remote.client reads the Supabase config from; kept as a local helper
    # because nothing under updater/ may import remote/.
    return Path(platformdirs.user_config_dir("soundboard")) / "settings.json"


def automatic_check_enabled(
    env: Mapping[str, str] | None = None, settings_path: Path | None = None
) -> bool:
    """Whether to check on launch. The manual check ignores this entirely.

    Defaults to on, including when the settings file is missing or unreadable: a corrupt
    file should not quietly cost someone every future fix.
    """
    resolved_env: Mapping[str, str] = os.environ if env is None else env
    if resolved_env.get(_DISABLE_ENV):
        return False

    settings_path = settings_path or _default_settings_path()
    try:
        settings = json.loads(settings_path.read_text())
    except (OSError, json.JSONDecodeError):
        return True
    return bool(settings.get("update_check", True))
