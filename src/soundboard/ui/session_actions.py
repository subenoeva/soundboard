"""The three transitions of the stored session, as `AppController` needs them.

Split out of `controller.py` to keep that file within its line budget. The three
share one rule that `auth.py` alone does not encode: whatever the remote call does,
what is left on disk must match what the app believes about the session.

`auth`'s functions are typed against the concrete `SessionStore`, not the `Store`
protocol the controller is wired with; the two are structurally compatible (the real
`SessionStore`, or the tests' duck-typed double), hence the ignores below.
"""

from __future__ import annotations

from soundboard.remote import auth
from soundboard.remote.models import RemoteClient, Session
from soundboard.ui.engine_factory import Store


def start(client: RemoteClient, store: Store, email: str, password: str) -> Session:
    """Sign in, persist the session, and seed a profile on the very first login."""
    return auth.log_in(
        client, store, email, password, lambda: email.split("@")[0]  # type: ignore[arg-type]
    )


def restore(client: RemoteClient, store: Store) -> Session | None:
    """Return the stored session restored onto `client`, or None if there is none."""
    if store.load() is None:
        return None
    try:
        return auth.require_session(client, store)  # type: ignore[arg-type]
    except Exception:
        # Supabase rotates the refresh token; one that was already consumed has to
        # read as "no session", not as a crash on startup.
        store.clear()
        return None


def discard(client: RemoteClient, store: Store) -> str | None:
    """Sign out and forget the session; returns the server's error, if it failed.

    Revoking the token remotely can fail (offline, token already expired) and the
    local half still has to happen: a session left on disk signs the user straight
    back in on the next start, which is the one thing logging out must prevent.
    """
    try:
        auth.log_out(client, store)  # type: ignore[arg-type]
    except Exception as exc:
        store.clear()
        return str(exc)
    return None
