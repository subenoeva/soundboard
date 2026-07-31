"""LibraryModel: headless list model over the remote library, with a name filter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from soundboard.remote import sounds
from soundboard.remote.fake_client import FakeRemoteClient
from soundboard.ui.library_model import LibraryModel


def _add_sound(
    client: FakeRemoteClient, owner_email: str, tmp_path: Path, filename: str, sound_name: str
) -> None:
    session = client.sign_in_as_new_user(owner_email)
    client.insert(
        "profiles", {"id": session.user_id, "display_name": owner_email.split("@")[0]}
    )
    path = tmp_path / filename
    sf.write(str(path), np.zeros(480, dtype=np.float32), 48_000)
    sounds.add_sound(client, session, str(path), name=sound_name)


@pytest.fixture
def seeded_client(tmp_path: Path) -> FakeRemoteClient:
    client = FakeRemoteClient()
    _add_sound(client, "ana@x.com", tmp_path, "a.wav", "airhorn")
    _add_sound(client, "beto@x.com", tmp_path, "b.wav", "applause")
    return client


def test_reload_populates_rows(qtbot: Any, seeded_client: FakeRemoteClient) -> None:
    model = LibraryModel(seeded_client)
    with qtbot.waitSignal(model.loadingChanged, timeout=2000):
        model.reload()
    qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    assert model.rowCount() > 0
    first = model.index(0)
    assert model.data(first, LibraryModel.NAME_ROLE)
    assert model.data(first, LibraryModel.SOUND_ID_ROLE)


def test_filter_narrows_by_name_case_insensitive(
    qtbot: Any, seeded_client: FakeRemoteClient
) -> None:
    # seeded with "airhorn" and "applause"
    model = LibraryModel(seeded_client)
    model.reload()
    qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    model.filterText = "AIR"  # type: ignore[assignment]
    assert model.rowCount() == 1
    model.filterText = ""  # type: ignore[assignment]
    assert model.rowCount() == 2


def test_reload_failure_sets_error(qtbot: Any) -> None:
    class ExplodingClient:
        def select(self, *a: object, **k: object) -> object:
            raise RuntimeError("boom")

    model = LibraryModel(ExplodingClient())  # type: ignore[arg-type]
    model.reload()
    qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    assert "boom" in model.errorText  # type: ignore[operator]


def test_reload_while_already_loading_is_ignored(
    qtbot: Any, seeded_client: FakeRemoteClient
) -> None:
    model = LibraryModel(seeded_client)
    model.reload()
    model.reload()  # popup reopened, or "Reintentar" pressed, before the first landed
    qtbot.waitUntil(lambda: not model.loading, timeout=2000)
    assert model.rowCount() == 2


def test_data_out_of_range_returns_none(qtbot: Any, seeded_client: FakeRemoteClient) -> None:
    model = LibraryModel(seeded_client)
    # A view can ask for a row that a concurrent filter change just removed.
    assert model.data(model.index(0), LibraryModel.NAME_ROLE) is None
