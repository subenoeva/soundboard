import base64

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from soundboard.updater.errors import FeedUnavailable, ManifestError, SignatureError
from soundboard.updater.fake_feed import FakeReleaseFeed
from soundboard.updater.feed import MANIFEST_NAME, SIGNATURE_NAME, HttpReleaseFeed

MANIFEST = (
    "version v0.4.0\n"
    "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08  "
    "soundboard-v0.4.0-windows.exe\n"
    "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae  "
    "soundboard-v0.4.0-linux-x86_64.AppImage\n"
)


@pytest.fixture
def signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def public_key(signing_key: Ed25519PrivateKey) -> bytes:
    return signing_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def _feed(routes: dict[str, httpx.Response], public_key: bytes) -> HttpReleaseFeed:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name not in routes:
            return httpx.Response(404)
        return routes[name]

    return HttpReleaseFeed(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        public_key=public_key,
    )


def _signed(signing_key: Ed25519PrivateKey, manifest: str) -> dict[str, httpx.Response]:
    signature = base64.b64encode(signing_key.sign(manifest.encode())).decode()
    return {
        MANIFEST_NAME: httpx.Response(200, text=manifest),
        SIGNATURE_NAME: httpx.Response(200, text=signature),
    }


def test_latest_returns_the_signed_manifest(
    signing_key: Ed25519PrivateKey, public_key: bytes
) -> None:
    manifest = _feed(_signed(signing_key, MANIFEST), public_key).latest()

    assert manifest is not None
    assert manifest.tag == "v0.4.0"


def test_a_release_whose_binaries_are_still_building_is_invisible(public_key: bytes) -> None:
    """release-please publishes the release, then the build jobs run for ~10 minutes.
    SHA256SUMS is uploaded by a job that needs both of them, so its absence is precisely
    the signal that there is nothing installable yet."""
    assert _feed({}, public_key).latest() is None


def test_a_manifest_signed_by_another_key_is_refused(public_key: bytes) -> None:
    attacker = Ed25519PrivateKey.generate()

    with pytest.raises(SignatureError):
        _feed(_signed(attacker, MANIFEST), public_key).latest()


def test_a_manifest_altered_after_signing_is_refused(
    signing_key: Ed25519PrivateKey, public_key: bytes
) -> None:
    routes = _signed(signing_key, MANIFEST)
    routes[MANIFEST_NAME] = httpx.Response(200, text=MANIFEST.replace("v0.4.0", "v9.9.9"))

    with pytest.raises(SignatureError):
        _feed(routes, public_key).latest()


def test_a_missing_signature_is_refused(
    signing_key: Ed25519PrivateKey, public_key: bytes
) -> None:
    """An unsigned manifest is not a partial release, it is one we must not act on."""
    routes = _signed(signing_key, MANIFEST)
    del routes[SIGNATURE_NAME]

    with pytest.raises(SignatureError):
        _feed(routes, public_key).latest()


def test_a_malformed_manifest_is_reported_after_the_signature_checks_out(
    signing_key: Ed25519PrivateKey, public_key: bytes
) -> None:
    with pytest.raises(ManifestError):
        _feed(_signed(signing_key, "version v0.4.0\ngarbage\n"), public_key).latest()


def test_a_server_error_is_reported_rather_than_read_as_up_to_date(public_key: bytes) -> None:
    routes = {MANIFEST_NAME: httpx.Response(503, text="")}

    with pytest.raises(FeedUnavailable):
        _feed(routes, public_key).latest()


def test_a_transport_failure_is_reported(public_key: bytes) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    feed = HttpReleaseFeed(
        client=httpx.Client(transport=httpx.MockTransport(refuse)), public_key=public_key
    )

    with pytest.raises(FeedUnavailable):
        feed.latest()


def test_asset_url_points_at_the_tagged_release() -> None:
    feed = HttpReleaseFeed(repo="subenoeva/soundboard")

    assert feed.asset_url("v0.4.0", "soundboard-v0.4.0-windows.exe") == (
        "https://github.com/subenoeva/soundboard/releases/download/v0.4.0/"
        "soundboard-v0.4.0-windows.exe"
    )


def test_the_manifest_is_read_from_the_latest_release_alias() -> None:
    feed = HttpReleaseFeed(repo="subenoeva/soundboard")

    assert feed.manifest_url() == (
        "https://github.com/subenoeva/soundboard/releases/latest/download/SHA256SUMS"
    )


def test_fake_feed_serves_a_configured_release() -> None:
    feed = FakeReleaseFeed(manifest_text=MANIFEST)

    manifest = feed.latest()

    assert manifest is not None
    assert manifest.is_newer_than("0.3.0")


def test_fake_feed_can_report_no_release() -> None:
    assert FakeReleaseFeed().latest() is None


def test_fake_feed_can_raise_the_failure_under_test() -> None:
    feed = FakeReleaseFeed(error=FeedUnavailable("network down"))

    with pytest.raises(FeedUnavailable):
        feed.latest()
