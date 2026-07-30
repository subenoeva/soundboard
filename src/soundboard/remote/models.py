"""Data shapes shared across the remote sound library and its client protocol.

``RemoteClient`` is the seam between the library logic (auth.py, sounds.py,
categories.py) and whatever talks to Supabase — the same role ``AudioBackend`` plays
for the audio engine. Two implementations exist: ``SupabaseRemoteClient`` (real) and
``FakeRemoteClient`` (in-memory, for tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    user_id: str
    email: str


@dataclass(frozen=True)
class Profile:
    id: str
    display_name: str


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    color: str | None
    position: int
    created_by: str


@dataclass(frozen=True)
class Sound:
    id: str
    owner_id: str
    category_id: str | None
    name: str
    sha256: str
    storage_path: str
    source_filename: str
    duration_frames: int
    orig_samplerate: int
    orig_channels: int
    gain_db: float
    trim_start_frames: int
    trim_end_frames: int | None
    loop: bool
    color: str | None
    tags: list[str] = field(default_factory=list)


class RemoteClient(Protocol):
    def sign_up(self, email: str, password: str) -> None: ...
    def sign_in(self, email: str, password: str) -> Session: ...
    def sign_out(self) -> None: ...
    def restore_session(self, session: Session) -> None: ...

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    def update(self, table: str, id_: str, fields: dict[str, Any]) -> int:
        """Returns the number of rows affected. 0 means not found or not permitted."""
        ...

    def delete(self, table: str, id_: str) -> int:
        """Returns the number of rows affected. 0 means not found or not permitted."""
        ...

    def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
        """Idempotent: uploading the same content-addressed path twice is a no-op."""
        ...

    def storage_download(self, bucket: str, path: str) -> bytes: ...
