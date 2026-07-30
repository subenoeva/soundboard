"""CRUD for the shared sound library, plus PCM resolution for playback."""

from __future__ import annotations

from typing import Any

import numpy as np

from soundboard.library.cache import SoundCache
from soundboard.library.importer import import_sound
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.models import RemoteClient, Session, Sound

BUCKET = "sounds"


def _row_to_sound(row: dict[str, Any]) -> Sound:
    return Sound(
        id=row["id"],
        owner_id=row["owner_id"],
        category_id=row.get("category_id"),
        name=row["name"],
        sha256=row["sha256"],
        storage_path=row["storage_path"],
        source_filename=row["source_filename"],
        duration_frames=row["duration_frames"],
        orig_samplerate=row["orig_samplerate"],
        orig_channels=row["orig_channels"],
        gain_db=row["gain_db"],
        trim_start_frames=row.get("trim_start_frames", 0),
        trim_end_frames=row.get("trim_end_frames"),
        loop=row.get("loop", False),
        color=row.get("color"),
        tags=row.get("tags") or [],
    )


def add_sound(
    client: RemoteClient,
    session: Session,
    path: str,
    name: str,
    category_id: str | None = None,
) -> Sound:
    """Import ``path`` and add it to the library. Idempotent per (owner, content)."""
    imported = import_sound(path)

    existing = client.select(
        "sounds", filters={"owner_id": session.user_id, "sha256": imported.sha256}
    )
    if existing:
        return _row_to_sound(existing[0])

    storage_path = f"{imported.sha256}.f32"
    client.storage_upload(BUCKET, storage_path, imported.pcm.tobytes())

    row = client.insert(
        "sounds",
        {
            "owner_id": session.user_id,
            "category_id": category_id,
            "name": name,
            "sha256": imported.sha256,
            "storage_path": storage_path,
            "source_filename": imported.source_filename,
            "duration_frames": imported.duration_frames,
            "orig_samplerate": imported.orig_samplerate,
            "orig_channels": imported.orig_channels,
            "gain_db": imported.gain_db,
            "trim_start_frames": 0,
            "trim_end_frames": None,
            "loop": False,
        },
    )
    return _row_to_sound(row)


def list_sounds(
    client: RemoteClient, *, owner_id: str | None = None, category_id: str | None = None
) -> list[Sound]:
    filters: dict[str, Any] = {}
    if owner_id is not None:
        filters["owner_id"] = owner_id
    if category_id is not None:
        filters["category_id"] = category_id
    rows = client.select("sounds", filters=filters or None)
    return [_row_to_sound(row) for row in rows]


def get_sound(client: RemoteClient, sound_id: str) -> Sound:
    rows = client.select("sounds", filters={"id": sound_id})
    if not rows:
        raise LookupError(f"no sound with id {sound_id!r}")
    return _row_to_sound(rows[0])


def find_sound_by_name(client: RemoteClient, name: str) -> Sound | None:
    rows = client.select("sounds", filters={"name": name})
    return _row_to_sound(rows[0]) if rows else None


def edit_sound(client: RemoteClient, sound_id: str, **fields: Any) -> Sound:
    affected = client.update("sounds", sound_id, fields)
    if affected == 0:
        raise PermissionDeniedError(f"cannot edit sound {sound_id!r}: not found or not yours")
    return get_sound(client, sound_id)


def remove_sound(client: RemoteClient, sound_id: str) -> None:
    affected = client.delete("sounds", sound_id)
    if affected == 0:
        raise PermissionDeniedError(f"cannot delete sound {sound_id!r}: not found or not yours")


def resolve_pcm(client: RemoteClient, cache: SoundCache, sound: Sound) -> np.ndarray:
    def fetch() -> bytes:
        return client.storage_download(BUCKET, sound.storage_path)

    return cache.get_or_fetch(sound.sha256, fetch, expected_frames=sound.duration_frames)
