"""Errors raised while checking for, downloading or installing an update.

All of them derive from ``UpdateError`` so the UI can catch the whole family in one
place and show the message, while still being able to single out the ones that mean
"someone tampered with this" from the ones that mean "the network is down".
"""

from __future__ import annotations


class UpdateError(Exception):
    """Base class for every failure on the update path."""


class FeedUnavailable(UpdateError):
    """Raised when the release manifest could not be fetched."""


class ManifestError(UpdateError):
    """Raised when the release manifest is absent, malformed or self-inconsistent."""


class SignatureError(UpdateError):
    """Raised when the manifest signature does not verify against the shipped key.

    Never recoverable and never retried: it means the manifest was not produced by the
    release pipeline, so nothing downstream of it may be trusted.
    """


class DigestMismatch(UpdateError):
    """Raised when a downloaded asset does not hash to the digest the manifest signed."""


class NotWritable(UpdateError):
    """Raised when the directory holding the running binary cannot be written to."""
