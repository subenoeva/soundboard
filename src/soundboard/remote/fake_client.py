"""In-memory RemoteClient, for tests. No network, no Supabase."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from soundboard.remote.models import Session

_OWNER_COLUMN = {
    "sounds": "owner_id",
    "categories": "created_by",
    "profiles": "id",
}


class FakeRemoteClient:
    def __init__(self) -> None:
        self._passwords: dict[str, str] = {}
        self._user_ids: dict[str, str] = {}
        self._tables: dict[str, dict[str, dict[str, Any]]] = {}
        self._storage: dict[str, bytes] = {}
        self._current_user_id: str | None = None

    # -- auth ---------------------------------------------------------------

    def sign_up(self, email: str, password: str) -> None:
        if email not in self._user_ids:
            self._user_ids[email] = str(uuid4())
        self._passwords[email] = password

    def sign_in(self, email: str, password: str) -> Session:
        if self._passwords.get(email) != password:
            raise ValueError(f"invalid credentials for {email!r}")
        self._current_user_id = self._user_ids[email]
        return Session(
            access_token=f"fake-access-{email}",
            refresh_token=f"fake-refresh-{email}",
            user_id=self._current_user_id,
            email=email,
        )

    def sign_in_as_new_user(self, email: str) -> Session:
        """Test convenience: sign_up + sign_in in one call, random password."""
        self.sign_up(email, "password")
        return self.sign_in(email, "password")

    def sign_out(self) -> None:
        self._current_user_id = None

    def restore_session(self, session: Session) -> None:
        self._current_user_id = session.user_id

    # -- tables ---------------------------------------------------------------

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        stored = dict(row)
        stored.setdefault("id", str(uuid4()))
        self._tables.setdefault(table, {})[stored["id"]] = stored
        return dict(stored)

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        rows = list(self._tables.get(table, {}).values())
        if filters:
            rows = [r for r in rows if all(r.get(k) == v for k, v in filters.items())]
        return [dict(r) for r in rows]

    def _authorized_row(self, table: str, id_: str) -> dict[str, Any] | None:
        row = self._tables.get(table, {}).get(id_)
        if row is None:
            return None
        owner_column = _OWNER_COLUMN.get(table)
        if owner_column is not None and row.get(owner_column) != self._current_user_id:
            return None
        return row

    def update(self, table: str, id_: str, fields: dict[str, Any]) -> int:
        row = self._authorized_row(table, id_)
        if row is None:
            return 0
        row.update(fields)
        return 1

    def delete(self, table: str, id_: str) -> int:
        row = self._authorized_row(table, id_)
        if row is None:
            return 0
        del self._tables[table][id_]
        return 1

    # -- storage ---------------------------------------------------------------

    def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
        self._storage[f"{bucket}/{path}"] = data

    def storage_download(self, bucket: str, path: str) -> bytes:
        return self._storage[f"{bucket}/{path}"]
