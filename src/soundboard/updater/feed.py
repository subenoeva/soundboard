"""Where releases are announced, behind a protocol so the UI can be tested offline.

The check does not use api.github.com. It reads two assets through the stable
``releases/latest/download/`` redirect:

* the version is inside the signed payload, so the claim "the newest release is v0.4.0"
  is authenticated too, not just the binary it points at;
* it is not subject to the API's 60-requests-per-hour-per-IP limit, which a shared
  address can exhaust;
* SHA256SUMS is uploaded by a CI job that needs both build jobs, so a release whose
  binaries are still building simply has no manifest and stays invisible — no special
  case here.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from soundboard.updater.errors import FeedUnavailable, SignatureError
from soundboard.updater.keys import UPDATE_PUBLIC_KEY
from soundboard.updater.manifest import Manifest, parse
from soundboard.updater.signature import verify

MANIFEST_NAME = "SHA256SUMS"
SIGNATURE_NAME = "SHA256SUMS.sig"

DEFAULT_REPO = "subenoeva/soundboard"

_TIMEOUT = httpx.Timeout(10.0, read=30.0)


class ReleaseFeed(Protocol):
    def latest(self) -> Manifest | None:
        """The newest installable release, or None when there is not one."""
        ...

    def asset_url(self, tag: str, asset_name: str) -> str: ...


class HttpReleaseFeed:
    def __init__(
        self,
        repo: str = DEFAULT_REPO,
        client: httpx.Client | None = None,
        public_key: bytes = UPDATE_PUBLIC_KEY,
    ) -> None:
        self._repo = repo
        self._client = client or httpx.Client(follow_redirects=True, timeout=_TIMEOUT)
        self._public_key = public_key

    def manifest_url(self) -> str:
        return f"https://github.com/{self._repo}/releases/latest/download/{MANIFEST_NAME}"

    def _signature_url(self) -> str:
        return f"https://github.com/{self._repo}/releases/latest/download/{SIGNATURE_NAME}"

    def asset_url(self, tag: str, asset_name: str) -> str:
        return f"https://github.com/{self._repo}/releases/download/{tag}/{asset_name}"

    def latest(self) -> Manifest | None:
        manifest_text = self._get(self.manifest_url())
        if manifest_text is None:
            return None

        signature = self._get(self._signature_url())
        if signature is None:
            # The manifest exists but its signature does not. Not a half-built release —
            # a manifest nobody vouched for, which is exactly what must not be acted on.
            raise SignatureError(f"{MANIFEST_NAME} is published without {SIGNATURE_NAME}")

        verify(manifest_text.encode(), signature, self._public_key)
        return parse(manifest_text)

    def _get(self, url: str) -> str | None:
        """Fetch ``url``, mapping 404 to None and every other failure to FeedUnavailable.

        Only 404 means "not published"; a 503 read as "up to date" would hide a real
        release behind a transient outage.
        """
        try:
            response = self._client.get(url)
            if response.status_code == httpx.codes.NOT_FOUND:
                return None
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise FeedUnavailable(f"could not reach the release feed: {error}") from error
        return response.text
