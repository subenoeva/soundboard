from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundboard.library.cache import SoundCache
from soundboard.remote import sounds
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.fake_client import FakeRemoteClient


def _clip(tmp_path: Path, name: str = "clip.wav") -> Path:
    path = tmp_path / name
    sf.write(str(path), np.full(480, 0.3, dtype=np.float32), 48_000)
    return path


def test_add_sound_creates_a_row_owned_by_the_caller(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")

    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    assert sound.owner_id == session.user_id
    assert sound.name == "laugh"
    assert sound.duration_frames == 480


def test_add_sound_uploads_the_pcm_to_storage(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")

    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    blob = client.storage_download("sounds", sound.storage_path)
    assert np.frombuffer(blob, dtype=np.float32).shape[0] == sound.duration_frames


def test_add_sound_is_idempotent_for_the_same_owner_and_file(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    clip = _clip(tmp_path)

    first = sounds.add_sound(client, session, str(clip), name="laugh")
    second = sounds.add_sound(client, session, str(clip), name="laugh again")

    assert first.id == second.id
    assert len(client.select("sounds", filters=None)) == 1


def test_list_sounds_filters_by_owner(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    sounds.add_sound(client, owner, str(_clip(tmp_path, "a.wav")), name="a")
    other = client.sign_in_as_new_user("other@x.com")
    sounds.add_sound(client, other, str(_clip(tmp_path, "b.wav")), name="b")

    mine = sounds.list_sounds(client, owner_id=owner.user_id)

    assert [s.name for s in mine] == ["a"]


def test_edit_sound_by_the_owner_succeeds(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    edited = sounds.edit_sound(client, sound.id, name="renamed")

    assert edited.name == "renamed"


def test_edit_sound_by_a_stranger_is_denied(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, owner, str(_clip(tmp_path)), name="laugh")
    client.sign_in_as_new_user("stranger@x.com")

    with pytest.raises(PermissionDeniedError):
        sounds.edit_sound(client, sound.id, name="hijacked")


def test_remove_sound_by_the_owner_succeeds(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")

    sounds.remove_sound(client, sound.id)

    assert sounds.list_sounds(client) == []


def test_remove_sound_by_a_stranger_is_denied(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    owner = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, owner, str(_clip(tmp_path)), name="laugh")
    client.sign_in_as_new_user("stranger@x.com")

    with pytest.raises(PermissionDeniedError):
        sounds.remove_sound(client, sound.id)


def test_get_sound_raises_lookup_error_when_missing() -> None:
    client = FakeRemoteClient()

    with pytest.raises(LookupError):
        sounds.get_sound(client, "nonexistent")


def test_resolve_pcm_downloads_on_a_cache_miss(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")
    cache = SoundCache(tmp_path / "cache")

    pcm = sounds.resolve_pcm(client, cache, sound)

    assert pcm.shape[0] == sound.duration_frames
    assert cache.has(sound.sha256)


def test_resolve_pcm_uses_the_cache_on_a_hit(tmp_path: Path) -> None:
    client = FakeRemoteClient()
    session = client.sign_in_as_new_user("owner@x.com")
    sound = sounds.add_sound(client, session, str(_clip(tmp_path)), name="laugh")
    cache = SoundCache(tmp_path / "cache")
    sounds.resolve_pcm(client, cache, sound)  # populates the cache

    # Corrupt storage after the fact: a cache hit must never touch it again.
    client._storage[f"sounds/{sound.storage_path}"] = b""

    pcm = sounds.resolve_pcm(client, cache, sound)
    assert pcm.shape[0] == sound.duration_frames
