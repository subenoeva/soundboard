import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from soundboard.updater.errors import SignatureError
from soundboard.updater.keys import UPDATE_PUBLIC_KEY
from soundboard.updater.signature import verify

PAYLOAD = b"version v0.4.0\n"


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return private, public


def _sign(private: Ed25519PrivateKey, payload: bytes) -> str:
    return base64.b64encode(private.sign(payload)).decode()


def test_a_genuine_signature_verifies() -> None:
    private, public = _keypair()

    verify(PAYLOAD, _sign(private, PAYLOAD), public)


def test_surrounding_whitespace_in_the_signature_file_is_ignored() -> None:
    private, public = _keypair()

    verify(PAYLOAD, f"  {_sign(private, PAYLOAD)}\n", public)


def test_a_tampered_payload_is_rejected() -> None:
    private, public = _keypair()
    signature = _sign(private, PAYLOAD)

    with pytest.raises(SignatureError):
        verify(PAYLOAD + b"x", signature, public)


def test_a_tampered_signature_is_rejected() -> None:
    private, public = _keypair()
    raw = bytearray(private.sign(PAYLOAD))
    raw[0] ^= 0x01

    with pytest.raises(SignatureError):
        verify(PAYLOAD, base64.b64encode(bytes(raw)).decode(), public)


def test_a_signature_from_another_key_is_rejected() -> None:
    attacker, _ = _keypair()
    _, public = _keypair()

    with pytest.raises(SignatureError):
        verify(PAYLOAD, _sign(attacker, PAYLOAD), public)


@pytest.mark.parametrize(
    "signature",
    [
        pytest.param("", id="empty"),
        pytest.param("not base64 !!", id="not base64"),
        pytest.param(base64.b64encode(b"too short").decode(), id="wrong length"),
        pytest.param(base64.b64encode(bytes(64)).decode() + "==", id="bad padding"),
    ],
)
def test_a_malformed_signature_file_is_rejected(signature: str) -> None:
    _, public = _keypair()

    with pytest.raises(SignatureError):
        verify(PAYLOAD, signature, public)


def test_the_baked_public_key_is_a_valid_ed25519_key() -> None:
    """A truncated or mistyped constant here would only surface at the first real
    update, on a user's machine."""
    assert len(UPDATE_PUBLIC_KEY) == 32
