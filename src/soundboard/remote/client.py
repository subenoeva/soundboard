"""Session persistence, config resolution and the real Supabase-backed client."""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, cast

import keyring
import platformdirs
from keyring.errors import NoKeyringError, PasswordDeleteError
from supabase import create_client

from soundboard.remote.models import Session

_SERVICE_NAME = "soundboard"
_KEYRING_USERNAME = "session"


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class SessionStore:
    """Persists the active session in the OS credential store between CLI runs."""

    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend: KeyringBackend = backend if backend is not None else keyring

    def save(self, session: Session) -> None:
        # no OS credential store running (e.g. a bare Wayland WM with no Secret Service
        # daemon): degrade to an unpersisted session instead of crashing right after login
        with contextlib.suppress(NoKeyringError):
            self._backend.set_password(
                _SERVICE_NAME, _KEYRING_USERNAME, json.dumps(asdict(session))
            )

    def load(self) -> Session | None:
        try:
            raw = self._backend.get_password(_SERVICE_NAME, _KEYRING_USERNAME)
        except NoKeyringError:
            return None
        if raw is None:
            return None
        return Session(**json.loads(raw))

    def clear(self) -> None:
        # already empty: clearing an absent session is not an error
        with contextlib.suppress(PasswordDeleteError, NoKeyringError):
            self._backend.delete_password(_SERVICE_NAME, _KEYRING_USERNAME)


def _default_settings_path() -> Path:
    return Path(platformdirs.user_config_dir("soundboard")) / "settings.json"


def _baked_config() -> tuple[str | None, str | None]:
    try:
        from soundboard._baked_defaults import SUPABASE_ANON_KEY, SUPABASE_URL
    except ImportError:
        return None, None
    return SUPABASE_URL, SUPABASE_ANON_KEY


def load_supabase_config(
    env: Mapping[str, str] | None = None, settings_path: Path | None = None
) -> tuple[str, str]:
    """Resolve ``(url, anon_key)``: environment, then ``settings.json``, then the
    baked-in defaults a packaged executable ships with."""
    resolved_env: Mapping[str, str] = os.environ if env is None else env
    settings_path = settings_path or _default_settings_path()

    url = resolved_env.get("SOUNDBOARD_SUPABASE_URL")
    key = resolved_env.get("SOUNDBOARD_SUPABASE_ANON_KEY")
    if (not url or not key) and settings_path.exists():
        data = json.loads(settings_path.read_text())
        supabase_cfg = data.get("supabase", {})
        url = url or supabase_cfg.get("url")
        key = key or supabase_cfg.get("anon_key")
    if not url or not key:
        baked_url, baked_key = _baked_config()
        url = url or baked_url
        key = key or baked_key
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured: set SOUNDBOARD_SUPABASE_URL and "
            f"SOUNDBOARD_SUPABASE_ANON_KEY, or add them to {settings_path}"
        )
    return url, key


class SupabaseRemoteClient:
    """Wraps the official ``supabase`` SDK behind the ``RemoteClient`` protocol."""

    def __init__(self, url: str, anon_key: str) -> None:
        self._client = create_client(url, anon_key)

    def sign_up(self, email: str, password: str) -> None:
        self._client.auth.sign_up({"email": email, "password": password})

    def sign_in(self, email: str, password: str) -> Session:
        result = self._client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        if result.session is None or result.user is None or result.user.email is None:
            # Happens when the project requires email confirmation: credentials are
            # valid but no session is issued yet. Never hand back a half-built Session.
            raise RuntimeError(f"sign-in for {email!r} did not return a session")
        return Session(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            user_id=result.user.id,
            email=result.user.email,
        )

    def sign_out(self) -> None:
        self._client.auth.sign_out()

    def restore_session(self, session: Session) -> None:
        self._client.auth.set_session(session.access_token, session.refresh_token)

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        response = self._client.table(table).insert(row).execute()
        return dict(cast("dict[str, Any]", response.data[0]))

    def select(
        self, table: str, *, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        query = self._client.table(table).select("*")
        for column, value in (filters or {}).items():
            query = query.eq(column, value)
        return [dict(cast("dict[str, Any]", row)) for row in query.execute().data]

    def update(self, table: str, id_: str, fields: dict[str, Any]) -> int:
        response = self._client.table(table).update(fields).eq("id", id_).execute()
        return len(response.data)

    def delete(self, table: str, id_: str) -> int:
        response = self._client.table(table).delete().eq("id", id_).execute()
        return len(response.data)

    def storage_upload(self, bucket: str, path: str, data: bytes) -> None:
        self._client.storage.from_(bucket).upload(path, data, file_options={"upsert": "true"})

    def storage_download(self, bucket: str, path: str) -> bytes:
        result = self._client.storage.from_(bucket).download(path)
        return bytes(result)


def build_client() -> SupabaseRemoteClient:
    url, anon_key = load_supabase_config()
    return SupabaseRemoteClient(url, anon_key)
