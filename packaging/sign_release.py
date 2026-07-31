"""Builds and signs the SHA256SUMS manifest the self-updater reads.

Run by the ``sign`` job of the release workflow, after both build jobs have uploaded
their assets. Its output being present on a release is what tells the updater the
release is installable — see soundboard.updater.feed.

Kept as a file rather than inlined in the workflow so mypy checks it and the tests can
verify the manifest it writes against the parser that consumes it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

MANIFEST_NAME = "SHA256SUMS"
SIGNATURE_NAME = "SHA256SUMS.sig"


def build_manifest(tag: str, assets: list[Path]) -> str:
    """The manifest text for ``tag``. Assets are listed in the order given.

    Two spaces between digest and name, matching sha256sum's binary-mode output, so
    ``tail -n +2 SHA256SUMS | sha256sum -c`` verifies a download by hand.
    """
    lines = [f"version {tag}"]
    for asset in assets:
        lines.append(f"{hashlib.sha256(asset.read_bytes()).hexdigest()}  {asset.name}")
    return "\n".join(lines) + "\n"


def sign(manifest: str, secret_key_b64: str) -> str:
    """Base64 Ed25519 signature over the manifest bytes."""
    seed = base64.b64decode(secret_key_b64.strip(), validate=True)
    private = Ed25519PrivateKey.from_private_bytes(seed)
    return base64.b64encode(private.sign(manifest.encode())).decode()


def public_key_hex(secret_key_b64: str) -> str:
    """The constant that belongs in soundboard/updater/keys.py for this secret."""
    seed = base64.b64decode(secret_key_b64.strip(), validate=True)
    public = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    return public.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def write_release_files(tag: str, assets: list[Path], secret_key_b64: str, out_dir: Path) -> None:
    manifest = build_manifest(tag, assets)
    # newline="" so the platform never rewrites \n as \r\n: the signature covers the
    # bytes held in memory, and a translated file would not verify against its own
    # signature. Explicit encoding for the same reason.
    _write(out_dir / MANIFEST_NAME, manifest)
    _write(out_dir / SIGNATURE_NAME, sign(manifest, secret_key_b64) + "\n")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, e.g. v1.2.3")
    parser.add_argument("assets", type=Path, nargs="*")
    parser.add_argument("--out-dir", type=Path, default=Path())
    parser.add_argument(
        "--secret-key",
        required=True,
        help="base64 Ed25519 seed (SOUNDBOARD_UPDATE_SIGNING_KEY)",
    )
    parser.add_argument(
        "--print-public-key",
        action="store_true",
        help="print the constant for soundboard/updater/keys.py and exit, for key rotation",
    )
    args = parser.parse_args(argv)

    if args.print_public_key:
        print(public_key_hex(args.secret_key))
        return 0

    if not args.assets:
        parser.error("at least one asset is required")

    missing = [asset for asset in args.assets if not asset.is_file()]
    if missing:
        # Signing a manifest that omits an asset would publish a release the updater
        # rejects on the platform whose binary went missing.
        parser.error(f"asset not found: {', '.join(str(path) for path in missing)}")

    write_release_files(args.tag, args.assets, args.secret_key, args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
