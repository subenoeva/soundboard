import pytest

from soundboard.updater.errors import ManifestError
from soundboard.updater.manifest import expected_asset_names, parse, parse_version

WINDOWS_DIGEST = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
LINUX_DIGEST = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"

VALID = (
    "version v0.4.0\n"
    f"{WINDOWS_DIGEST}  soundboard-v0.4.0-windows.exe\n"
    f"{LINUX_DIGEST}  soundboard-v0.4.0-linux-x86_64.AppImage\n"
)


def test_parse_reads_the_tag_version_and_digests() -> None:
    manifest = parse(VALID)

    assert manifest.tag == "v0.4.0"
    assert manifest.version == (0, 4, 0)
    assert manifest.digest_for("soundboard-v0.4.0-windows.exe") == WINDOWS_DIGEST
    assert manifest.digest_for("soundboard-v0.4.0-linux-x86_64.AppImage") == LINUX_DIGEST


def test_parse_tolerates_trailing_blank_lines() -> None:
    assert parse(VALID + "\n\n").tag == "v0.4.0"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param(VALID.split("\n", 1)[1], id="no version line"),
        pytest.param(VALID.replace("version v0.4.0", "version 0.4.0"), id="tag without v"),
        pytest.param(VALID.replace("version v0.4.0", "version v0.4"), id="two components"),
        pytest.param(VALID.replace("version v0.4.0", "version v0.4.0-rc.1"), id="pre-release"),
        pytest.param(VALID.replace(WINDOWS_DIGEST, WINDOWS_DIGEST[:-1]), id="short digest"),
        pytest.param(VALID.replace(WINDOWS_DIGEST, WINDOWS_DIGEST.upper()), id="uppercase digest"),
        pytest.param(VALID.replace(f"{WINDOWS_DIGEST}  ", f"{WINDOWS_DIGEST} "), id="one space"),
        pytest.param(VALID.replace("v0.4.0-windows", "v0.3.0-windows"), id="mixed versions"),
        pytest.param(
            VALID.replace(f"{LINUX_DIGEST}  soundboard-v0.4.0-linux-x86_64.AppImage\n", ""),
            id="missing linux asset",
        ),
    ],
)
def test_parse_rejects_malformed_input(text: str) -> None:
    with pytest.raises(ManifestError):
        parse(text)


def test_is_newer_than_compares_component_wise() -> None:
    manifest = parse(VALID)

    assert manifest.is_newer_than("0.3.0")
    assert manifest.is_newer_than("0.3.9")
    assert not manifest.is_newer_than("0.4.0")
    assert not manifest.is_newer_than("1.0.0")


def test_is_newer_than_rejects_a_malformed_running_version() -> None:
    with pytest.raises(ManifestError):
        parse(VALID).is_newer_than("unknown")


def test_digest_for_an_absent_asset_is_an_error() -> None:
    with pytest.raises(ManifestError):
        parse(VALID).digest_for("soundboard-v0.4.0-macos.dmg")


def test_parse_version_accepts_both_spellings() -> None:
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3") == (1, 2, 3)


def test_expected_asset_names_covers_both_platforms() -> None:
    assert expected_asset_names("v0.4.0") == (
        "soundboard-v0.4.0-windows.exe",
        "soundboard-v0.4.0-linux-x86_64.AppImage",
    )
