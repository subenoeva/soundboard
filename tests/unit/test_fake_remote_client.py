import pytest

from soundboard.remote.fake_client import FakeRemoteClient


def test_sign_up_then_sign_in_returns_a_session_with_a_stable_user_id() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")

    session = client.sign_in("a@x.com", "hunter2")

    assert session.email == "a@x.com"
    assert session.user_id


def test_sign_in_with_wrong_password_raises() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")

    with pytest.raises(ValueError):
        client.sign_in("a@x.com", "wrong")


def test_insert_then_select_roundtrips_a_row() -> None:
    client = FakeRemoteClient()
    client.sign_up("a@x.com", "hunter2")
    client.sign_in("a@x.com", "hunter2")

    row = client.insert("categories", {"name": "memes", "created_by": "u1"})
    found = client.select("categories", filters={"name": "memes"})

    assert found == [row]


def test_select_with_no_filters_returns_every_row() -> None:
    client = FakeRemoteClient()
    client.insert("categories", {"name": "a"})
    client.insert("categories", {"name": "b"})

    rows = client.select("categories", filters=None)

    assert {r["name"] for r in rows} == {"a", "b"}


def test_owner_can_update_their_own_sound_row() -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    row = client.insert("sounds", {"owner_id": session.user_id, "name": "old"})

    affected = client.update("sounds", row["id"], {"name": "new"})

    assert affected == 1
    assert client.select("sounds", filters={"id": row["id"]})[0]["name"] == "new"


def test_stranger_cannot_update_someone_elses_sound_row() -> None:
    client = FakeRemoteClient()
    owner_session = client.sign_in_as_new_user("owner@x.com")
    client.sign_in_as_new_user("stranger@x.com")  # switches "current user" to the stranger
    row = client.insert("sounds", {"owner_id": owner_session.user_id, "name": "old"})

    affected = client.update("sounds", row["id"], {"name": "hijacked"})

    assert affected == 0
    assert client.select("sounds", filters={"id": row["id"]})[0]["name"] == "old"


def test_stranger_cannot_delete_someone_elses_category() -> None:
    client = FakeRemoteClient()
    owner_session = client.sign_in_as_new_user("owner@x.com")
    row = client.insert("categories", {"name": "owned", "created_by": owner_session.user_id})
    client.sign_in_as_new_user("stranger@x.com")

    affected = client.delete("categories", row["id"])

    assert affected == 0
    assert client.select("categories", filters={"id": row["id"]})


def test_update_of_a_missing_row_returns_zero() -> None:
    client = FakeRemoteClient()
    client.sign_in_as_new_user("a@x.com")

    assert client.update("sounds", "nonexistent", {"name": "x"}) == 0


def test_storage_upload_then_download_roundtrips_bytes() -> None:
    client = FakeRemoteClient()

    client.storage_upload("sounds", "abc.f32", b"\x01\x02\x03\x04")

    assert client.storage_download("sounds", "abc.f32") == b"\x01\x02\x03\x04"


def test_storage_upload_is_idempotent_on_the_same_path() -> None:
    client = FakeRemoteClient()

    client.storage_upload("sounds", "abc.f32", b"first")
    client.storage_upload("sounds", "abc.f32", b"first")  # same content, re-uploaded

    assert client.storage_download("sounds", "abc.f32") == b"first"
