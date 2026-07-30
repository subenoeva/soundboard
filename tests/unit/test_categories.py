import pytest

from soundboard.remote import categories
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.fake_client import FakeRemoteClient


def test_add_category_is_owned_by_the_creator() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")

    category = categories.add_category(client, session, "memes")

    assert category.name == "memes"
    assert category.created_by == session.user_id


def test_add_category_is_idempotent_by_name() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")

    first = categories.add_category(client, session, "memes")
    second = categories.add_category(client, session, "memes")

    assert first.id == second.id
    assert len(client.select("categories", filters=None)) == 1


def test_list_categories_returns_every_category() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    categories.add_category(client, session, "memes")
    categories.add_category(client, session, "reactions")

    names = {c.name for c in categories.list_categories(client)}

    assert names == {"memes", "reactions"}


def test_remove_category_by_the_creator_succeeds() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    categories.add_category(client, session, "memes")

    categories.remove_category(client, "memes")

    assert categories.list_categories(client) == []


def test_remove_category_by_a_stranger_is_denied() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("a@x.com")
    categories.add_category(client, session, "memes")
    client.sign_in_as_new_user("stranger@x.com")

    with pytest.raises(PermissionDeniedError):
        categories.remove_category(client, "memes")


def test_remove_category_raises_lookup_error_when_missing() -> None:
    client = FakeRemoteClient()
    client.sign_in_as_new_user("a@x.com")

    with pytest.raises(LookupError):
        categories.remove_category(client, "nonexistent")
