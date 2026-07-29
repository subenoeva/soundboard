def test_library_subpackage_is_importable() -> None:
    import soundboard.library  # noqa: F401


def test_remote_subpackage_is_importable() -> None:
    import soundboard.remote  # noqa: F401


def test_remote_errors_are_exceptions() -> None:
    from soundboard.remote.errors import NotAuthenticatedError, PermissionDeniedError

    assert issubclass(NotAuthenticatedError, Exception)
    assert issubclass(PermissionDeniedError, Exception)
