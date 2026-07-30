"""Proves RLS against a real local Postgres — FakeRemoteClient only simulates the
row-count contract these policies are supposed to produce; this is what checks the
SQL in the migration actually enforces it.
"""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
import soundfile as sf

from soundboard.remote import categories, sounds
from soundboard.remote.client import SupabaseRemoteClient
from soundboard.remote.errors import PermissionDeniedError
from soundboard.remote.models import Session

pytestmark = pytest.mark.supabase


def _fresh_user(env: dict[str, str]) -> tuple[SupabaseRemoteClient, Session]:
    email = f"{uuid4()}@example.com"
    client = SupabaseRemoteClient(env["url"], env["anon_key"])
    client.sign_up(email, "correct horse battery staple")
    session = client.sign_in(email, "correct horse battery staple")
    client.restore_session(session)
    return client, session


def test_owner_can_edit_but_a_stranger_cannot(
    supabase_env: dict[str, str], tmp_path: Path
) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)

    owner, owner_session = _fresh_user(supabase_env)
    stranger, _ = _fresh_user(supabase_env)

    sound = sounds.add_sound(owner, owner_session, str(clip), name="integration clip")

    edited = sounds.edit_sound(owner, sound.id, name="renamed by owner")
    assert edited.name == "renamed by owner"

    with pytest.raises(PermissionDeniedError):
        sounds.edit_sound(stranger, sound.id, name="hijacked")


def test_owner_can_delete_but_a_stranger_cannot(
    supabase_env: dict[str, str], tmp_path: Path
) -> None:
    clip = tmp_path / "clip.wav"
    sf.write(str(clip), np.zeros(480, dtype=np.float32), 48_000)

    owner, owner_session = _fresh_user(supabase_env)
    stranger, _ = _fresh_user(supabase_env)
    sound = sounds.add_sound(owner, owner_session, str(clip), name="integration clip")

    with pytest.raises(PermissionDeniedError):
        sounds.remove_sound(stranger, sound.id)

    sounds.remove_sound(owner, sound.id)  # the actual owner can still remove it


def test_category_deletion_is_restricted_to_its_creator(supabase_env: dict[str, str]) -> None:
    creator, creator_session = _fresh_user(supabase_env)
    stranger, _ = _fresh_user(supabase_env)
    category = categories.add_category(creator, creator_session, f"cat-{uuid4()}")

    with pytest.raises(PermissionDeniedError):
        categories.remove_category(stranger, category.name)

    categories.remove_category(creator, category.name)
