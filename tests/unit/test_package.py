def test_package_exposes_version() -> None:
    import soundboard

    assert soundboard.__version__ == "0.1.0"


def test_audio_subpackage_is_importable() -> None:
    import soundboard.audio  # noqa: F401
