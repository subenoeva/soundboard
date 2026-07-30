def test_models_and_protocol_are_importable() -> None:
    from soundboard.remote.models import (  # noqa: F401
        Category,
        Profile,
        RemoteClient,
        Session,
        Sound,
    )


def test_session_is_a_frozen_dataclass() -> None:
    from soundboard.remote.models import Session

    session = Session(access_token="a", refresh_token="b", user_id="u", email="e@x.com")

    assert session.user_id == "u"
