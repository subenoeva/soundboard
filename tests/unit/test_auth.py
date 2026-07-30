import pytest

from soundboard.remote import auth
from soundboard.remote.client import SessionStore
from soundboard.remote.errors import NotAuthenticatedError
from soundboard.remote.fake_client import FakeRemoteClient


class _DictKeyringBackend:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


def _store() -> SessionStore:
    return SessionStore(backend=_DictKeyringBackend())


def test_log_in_saves_the_session() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()

    session = auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    assert store.load() == session


def test_log_in_creates_a_profile_on_first_login() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()

    session = auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    profiles = client.select("profiles", filters={"id": session.user_id})
    assert profiles == [{"id": session.user_id, "display_name": "Pablo"}]


def test_log_in_does_not_prompt_or_duplicate_an_existing_profile() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()
    auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    def fail_if_called() -> str:
        raise AssertionError("must not prompt again on a second login")

    auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=fail_if_called)

    assert len(client.select("profiles", filters=None)) == 1


def test_log_out_clears_the_stored_session() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()
    auth.log_in(client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo")

    auth.log_out(client, store)

    assert store.load() is None


def test_require_session_raises_when_none_is_stored() -> None:
    client = FakeRemoteClient()
    store = _store()

    with pytest.raises(NotAuthenticatedError):
        auth.require_session(client, store)


def test_require_session_restores_and_returns_the_stored_session() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    store = _store()
    logged_in = auth.log_in(
        client, store, "a@x.com", "hunter2", display_name_prompt=lambda: "Pablo"
    )

    restored = auth.require_session(client, store)

    assert restored == logged_in


def test_display_names_maps_user_ids_to_names() -> None:
    client = FakeRemoteClient()
    client.insert("profiles", {"id": "u1", "display_name": "Pablo"})
    client.insert("profiles", {"id": "u2", "display_name": "Ana"})

    names = auth.display_names(client, ["u1", "u2", "u3"])

    assert names == {"u1": "Pablo", "u2": "Ana"}
