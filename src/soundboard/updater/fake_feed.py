"""In-memory ``ReleaseFeed`` for tests — the role ``FakeBackend`` plays for audio and
``FakeRemoteClient`` plays for the remote library.

Takes manifest text rather than a ``Manifest`` so tests exercise the same parser the
real feed does, and skips signature verification because the signature is what
``HttpReleaseFeed`` is responsible for.
"""

from __future__ import annotations

from soundboard.updater.manifest import Manifest, parse


class FakeReleaseFeed:
    def __init__(
        self,
        manifest_text: str | None = None,
        error: Exception | None = None,
        repo: str = "example/soundboard",
    ) -> None:
        self._manifest_text = manifest_text
        self._error = error
        self._repo = repo
        self.checks = 0

    def latest(self) -> Manifest | None:
        self.checks += 1
        if self._error is not None:
            raise self._error
        if self._manifest_text is None:
            return None
        return parse(self._manifest_text)

    def asset_url(self, tag: str, asset_name: str) -> str:
        return f"https://example.invalid/{self._repo}/{tag}/{asset_name}"
