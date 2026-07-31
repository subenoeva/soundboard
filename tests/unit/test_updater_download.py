import hashlib
from pathlib import Path

import httpx
import pytest

from soundboard.updater.download import fetch
from soundboard.updater.errors import DigestMismatch, FeedUnavailable

PAYLOAD = b"a plausible executable" * 100
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _serving(content: bytes, status: int = 200) -> httpx.Client:
    return _client(lambda request: httpx.Response(status, content=content))


def test_fetch_writes_the_asset_when_the_digest_matches(tmp_path: Path) -> None:
    dest = tmp_path / "staged.tmp"

    fetch("https://example.invalid/asset", dest, DIGEST, client=_serving(PAYLOAD))

    assert dest.read_bytes() == PAYLOAD


def test_fetch_rejects_and_deletes_an_asset_whose_digest_differs(tmp_path: Path) -> None:
    """The digest comes from the signed manifest, so a mismatch means the bytes are not
    the ones that were released. Leaving the file behind risks it being installed later."""
    dest = tmp_path / "staged.tmp"

    with pytest.raises(DigestMismatch):
        fetch("https://example.invalid/asset", dest, DIGEST, client=_serving(b"something else"))

    assert not dest.exists()


def test_fetch_reports_progress_against_the_content_length(tmp_path: Path) -> None:
    seen: list[tuple[int, int | None]] = []

    fetch(
        "https://example.invalid/asset",
        tmp_path / "staged.tmp",
        DIGEST,
        progress=lambda done, total: seen.append((done, total)),
        client=_serving(PAYLOAD),
    )

    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert [done for done, _ in seen] == sorted(done for done, _ in seen)


def test_fetch_still_works_without_a_content_length(tmp_path: Path) -> None:
    seen: list[tuple[int, int | None]] = []

    def chunked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(PAYLOAD))

    fetch(
        "https://example.invalid/asset",
        tmp_path / "staged.tmp",
        DIGEST,
        progress=lambda done, total: seen.append((done, total)),
        client=_client(chunked),
    )

    assert seen[-1] == (len(PAYLOAD), None)


def test_fetch_raises_on_a_failed_response(tmp_path: Path) -> None:
    dest = tmp_path / "staged.tmp"

    with pytest.raises(FeedUnavailable):
        fetch("https://example.invalid/asset", dest, DIGEST, client=_serving(b"", status=500))

    assert not dest.exists()


def test_fetch_raises_on_a_transport_failure(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(FeedUnavailable):
        fetch(
            "https://example.invalid/asset",
            tmp_path / "staged.tmp",
            DIGEST,
            client=_client(refuse),
        )


def test_fetch_overwrites_an_interrupted_earlier_download(tmp_path: Path) -> None:
    dest = tmp_path / "staged.tmp"
    dest.write_bytes(b"half of a previous attempt")

    fetch("https://example.invalid/asset", dest, DIGEST, client=_serving(PAYLOAD))

    assert dest.read_bytes() == PAYLOAD
