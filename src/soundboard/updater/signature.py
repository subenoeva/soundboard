"""Ed25519 verification of the release manifest.

The signature covers the manifest, not the binaries: Ed25519 needs the whole message in
memory and the packaged executable runs to ~100MB. Signing a 200-byte manifest that
carries the SHA-256 of each asset keeps memory constant while leaving the trust chain
intact — signature to digest to binary — the same shape Debian's Release/Release.gpg
uses.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from soundboard.updater.errors import SignatureError
from soundboard.updater.keys import UPDATE_PUBLIC_KEY

_SIGNATURE_BYTES = 64


def verify(payload: bytes, signature: str, public_key: bytes = UPDATE_PUBLIC_KEY) -> None:
    """Check that ``signature`` (base64, as stored in ``SHA256SUMS.sig``) covers
    ``payload``. Returns None on success, raises ``SignatureError`` otherwise."""
    try:
        raw = base64.b64decode(signature.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        raise SignatureError(f"signature is not valid base64: {error}") from error

    if len(raw) != _SIGNATURE_BYTES:
        raise SignatureError(
            f"signature is {len(raw)} bytes, expected {_SIGNATURE_BYTES}",
        )

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(raw, payload)
    except InvalidSignature as error:
        raise SignatureError(
            "release manifest signature does not verify against the shipped key"
        ) from error
