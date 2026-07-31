import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from keyring.errors import NoKeyringError, PasswordDeleteError

from soundboard.remote.client import (
    SessionStore,
    SupabaseRemoteClient,
    load_supabase_config,
)
from soundboard.remote.models import Session


class _FakeKeyringBackend:
    """Dict-backed stand-in for the ``keyring`` module's module-level functions."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError:
            raise PasswordDeleteError("password not found") from None


class _NoBackendKeyring:
    """Stand-in for a machine with no Secret Service/keyring daemon running."""

    def get_password(self, service: str, username: str) -> str | None:
        raise NoKeyringError("no recommended backend was available")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise NoKeyringError("no recommended backend was available")

    def delete_password(self, service: str, username: str) -> None:
        raise NoKeyringError("no recommended backend was available")


def test_session_store_round_trips_a_session() -> None:
    store = SessionStore(backend=_FakeKeyringBackend())
    session = Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com")

    store.save(session)

    assert store.load() == session


def test_session_store_load_returns_none_when_empty() -> None:
    store = SessionStore(backend=_FakeKeyringBackend())

    assert store.load() is None


def test_session_store_clear_is_idempotent() -> None:
    store = SessionStore(backend=_FakeKeyringBackend())
    store.save(Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com"))

    store.clear()
    store.clear()  # second clear on an already-empty store must not raise

    assert store.load() is None


def test_session_store_load_falls_back_to_none_without_a_keyring_backend() -> None:
    store = SessionStore(backend=_NoBackendKeyring())

    assert store.load() is None


def test_session_store_save_does_not_raise_without_a_keyring_backend() -> None:
    store = SessionStore(backend=_NoBackendKeyring())

    store.save(Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com"))


def test_session_store_clear_does_not_raise_without_a_keyring_backend() -> None:
    store = SessionStore(backend=_NoBackendKeyring())

    store.clear()


def test_load_supabase_config_prefers_environment_variables() -> None:
    env = {
        "SOUNDBOARD_SUPABASE_URL": "https://env.supabase.co",
        "SOUNDBOARD_SUPABASE_ANON_KEY": "env-key",
    }

    url, key = load_supabase_config(env=env, settings_path=Path("/nonexistent"))

    assert (url, key) == ("https://env.supabase.co", "env-key")


def test_load_supabase_config_falls_back_to_settings_file(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"supabase": {"url": "https://file.supabase.co", "anon_key": "file-key"}})
    )

    url, key = load_supabase_config(env={}, settings_path=settings_path)

    assert (url, key) == ("https://file.supabase.co", "file-key")


def test_load_supabase_config_raises_a_clear_error_when_unconfigured(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="SOUNDBOARD_SUPABASE_URL"):
        load_supabase_config(env={}, settings_path=tmp_path / "missing.json")


def test_load_supabase_config_falls_back_to_baked_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baked = types.ModuleType("soundboard._baked_defaults")
    baked.SUPABASE_URL = "https://baked.supabase.co"  # type: ignore[attr-defined]
    baked.SUPABASE_ANON_KEY = "baked-key"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundboard._baked_defaults", baked)

    url, key = load_supabase_config(env={}, settings_path=tmp_path / "missing.json")

    assert (url, key) == ("https://baked.supabase.co", "baked-key")


def test_load_supabase_config_prefers_env_over_baked_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baked = types.ModuleType("soundboard._baked_defaults")
    baked.SUPABASE_URL = "https://baked.supabase.co"  # type: ignore[attr-defined]
    baked.SUPABASE_ANON_KEY = "baked-key"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundboard._baked_defaults", baked)
    env = {
        "SOUNDBOARD_SUPABASE_URL": "https://env.supabase.co",
        "SOUNDBOARD_SUPABASE_ANON_KEY": "env-key",
    }

    url, key = load_supabase_config(env=env, settings_path=tmp_path / "missing.json")

    assert (url, key) == ("https://env.supabase.co", "env-key")


class _FakeQuery:
    def __init__(self, table: "_FakeTable", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []

    def eq(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append((column, value))
        return self

    def execute(self) -> Any:
        return self._table.run(self._op, self._payload, self._filters)


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, columns: str) -> _FakeQuery:
        return _FakeQuery(self, "select")

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self, "insert", row)

    def update(self, fields: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self, "update", fields)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self, "delete")

    def run(self, op: str, payload: Any, filters: list[tuple[str, Any]]) -> _FakeResponse:
        if op == "insert":
            row = dict(payload)
            row.setdefault("id", "new-id")
            self.rows.append(row)
            return _FakeResponse([row])

        matched = [
            r for r in self.rows if all(r.get(col) == val for col, val in filters)
        ]
        if op == "select":
            return _FakeResponse(matched)
        if op == "update":
            for row in matched:
                row.update(payload)
            return _FakeResponse(matched)
        if op == "delete":
            for row in matched:
                self.rows.remove(row)
            return _FakeResponse(matched)
        raise AssertionError(f"unexpected op {op!r}")


class _FakeStorageBucket:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, bytes, dict[str, Any]]] = []
        self._blobs: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, file_options: dict[str, Any]) -> None:
        self.uploaded.append((path, data, file_options))
        self._blobs[path] = data

    def download(self, path: str) -> bytes:
        return self._blobs[path]


class _FakeStorage:
    def __init__(self) -> None:
        self.bucket = _FakeStorageBucket()

    def from_(self, bucket: str) -> _FakeStorageBucket:
        return self.bucket


class _FakeAuth:
    def sign_up(self, credentials: dict[str, str]) -> None:
        pass

    def sign_out(self) -> None:
        pass


class _FakeSDKClient:
    def __init__(self) -> None:
        self.auth = _FakeAuth()
        self.storage = _FakeStorage()
        self._tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self._tables.setdefault(name, _FakeTable([]))


def test_supabase_remote_client_insert_select_update_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sdk = _FakeSDKClient()
    monkeypatch.setattr(
        "soundboard.remote.client.create_client", lambda url, key: fake_sdk
    )
    client = SupabaseRemoteClient("https://x.supabase.co", "anon-key")

    row = client.insert("categories", {"name": "memes"})
    assert client.select("categories", filters={"name": "memes"}) == [row]

    affected = client.update("categories", row["id"], {"name": "renamed"})
    assert affected == 1
    assert client.select("categories", filters={"id": row["id"]})[0]["name"] == "renamed"

    affected = client.delete("categories", row["id"])
    assert affected == 1
    assert client.select("categories", filters={"id": row["id"]}) == []


def test_supabase_remote_client_uploads_with_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sdk = _FakeSDKClient()
    monkeypatch.setattr(
        "soundboard.remote.client.create_client", lambda url, key: fake_sdk
    )
    client = SupabaseRemoteClient("https://x.supabase.co", "anon-key")

    client.storage_upload("sounds", "abc.f32", b"\x00\x01")

    path, data, options = fake_sdk.storage.bucket.uploaded[0]
    assert path == "abc.f32"
    assert data == b"\x00\x01"
    assert options["upsert"] == "true"
    assert client.storage_download("sounds", "abc.f32") == b"\x00\x01"
