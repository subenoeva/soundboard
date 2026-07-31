"""Streaming download of a release asset, checked against the signed digest.

Hashing as the bytes arrive keeps memory flat for a ~100MB executable and means the
verification costs nothing beyond the download itself.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable
from pathlib import Path

import httpx

from soundboard.updater.errors import DigestMismatch, FeedUnavailable

ProgressCallback = Callable[[int, int | None], None]

_CHUNK_BYTES = 1 << 16


def fetch(
    url: str,
    dest: Path,
    expected_sha256: str,
    progress: ProgressCallback | None = None,
    client: httpx.Client | None = None,
) -> None:
    """Download ``url`` into ``dest`` and verify it hashes to ``expected_sha256``.

    ``progress`` receives ``(bytes_downloaded, total_or_None)``; the total is None when
    the response carries no Content-Length. On any failure ``dest`` is removed, so a
    rejected or half-written download can never be installed later.
    """
    owned = client is None
    client = client or httpx.Client(follow_redirects=True)
    digest = hashlib.sha256()
    downloaded = 0

    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            total = _content_length(response)
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes(_CHUNK_BYTES):
                    handle.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(downloaded, total)
    except httpx.HTTPError as error:
        _discard(dest)
        raise FeedUnavailable(f"could not download {url}: {error}") from error
    except BaseException:
        _discard(dest)
        raise
    finally:
        if owned:
            client.close()

    if digest.hexdigest() != expected_sha256:
        _discard(dest)
        raise DigestMismatch(
            f"{dest.name} hashes to {digest.hexdigest()}, the release manifest signed "
            f"{expected_sha256}"
        )


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
