"""Sign-up, login, logout and the first-login profile bootstrap."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from soundboard.remote.client import SessionStore
from soundboard.remote.errors import NotAuthenticatedError
from soundboard.remote.models import RemoteClient, Session


def sign_up(client: RemoteClient, email: str, password: str) -> None:
    client.sign_up(email, password)


def log_in(
    client: RemoteClient,
    store: SessionStore,
    email: str,
    password: str,
    display_name_prompt: Callable[[], str],
) -> Session:
    session = client.sign_in(email, password)
    store.save(session)
    if not client.select("profiles", filters={"id": session.user_id}):
        client.insert("profiles", {"id": session.user_id, "display_name": display_name_prompt()})
    return session


def log_out(client: RemoteClient, store: SessionStore) -> None:
    client.sign_out()
    store.clear()


def require_session(client: RemoteClient, store: SessionStore) -> Session:
    """Load the stored session, restore it onto ``client``, and return it.

    Raises ``NotAuthenticatedError`` rather than silently proceeding unauthenticated —
    every remote command needs a clear, actionable error instead of a confusing
    downstream RLS rejection.
    """
    session = store.load()
    if session is None:
        raise NotAuthenticatedError("no session found; run `soundboard auth login` first")
    client.restore_session(session)
    return session


def display_names(client: RemoteClient, user_ids: Iterable[str]) -> dict[str, str]:
    wanted = set(user_ids)
    if not wanted:
        return {}
    rows = client.select("profiles", filters=None)
    return {row["id"]: row["display_name"] for row in rows if row["id"] in wanted}
