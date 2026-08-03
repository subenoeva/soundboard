"""Fetches the DPDFNet ONNX weights the frozen build embeds, verified by digest.

The model is not committed — 10.49 MB of binary that a pinned URL plus a SHA-256
reproduces exactly — but it is also not downloaded at first launch: both PyInstaller
specs call ``ensure_model()`` before ``Analysis`` reads its ``datas``, so the binary
ships with the weights inside it and works offline.

``dpdfnet`` itself is deliberately not used for this. Its ``models.py`` accepts any
file whose size is greater than zero, has no checksum anywhere, and defaults to
``DEFAULT_REVISION = "main"``, a mutable Hugging Face ref — a release built on a bad
day would embed whatever ``main`` served that morning and the updater would then sign
it, leaving the model as the one unverified blob in an otherwise verified release. So
the revision commit and the digest are pinned here and the transfer reuses
``soundboard.updater.download.fetch``, which already streams to a destination, hashes
as the bytes arrive and raises on a mismatch.

Run it by hand from a checkout with:

    uv run python packaging/fetch_model.py

The pinned file is 10 493 337 bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from soundboard.updater.download import fetch

HF_REPO = "Ceva-IP/DPDFNet"
HF_REVISION = "dd6818d00f50c836fed43a6243ebe49116de5964"
HF_PATH = "onnx/dpdfnet2_48khz_hr.onnx"

_CHUNK_BYTES = 1 << 16


@dataclass(frozen=True)
class PinnedModel:
    """One model file, identified by the bytes it must hash to rather than by a name."""

    filename: str
    url: str
    sha256: str


DPDFNET = PinnedModel(
    filename="dpdfnet2_48khz_hr.onnx",
    url=f"https://huggingface.co/{HF_REPO}/resolve/{HF_REVISION}/{HF_PATH}",
    sha256="7f0575a5cec0ba4ffd8f8bd657e06d007e4ccdd955d76faab922b9d3291dc14b",
)


def default_destination(model: PinnedModel = DPDFNET) -> Path:
    """Where ``soundboard.effects.neural.default_model_path()`` looks in a checkout."""
    root = Path(__file__).resolve().parents[1]
    return root / "src" / "soundboard" / "effects" / "models" / model.filename


def ensure_model(
    model: PinnedModel = DPDFNET,
    destination: Path | None = None,
    *,
    client: httpx.Client | None = None,
) -> Path:
    """Return the path to ``model``, downloading it unless it is already the right file.

    A file whose digest does not match is removed before the download starts: nothing
    downstream hashes the model again, so a stale copy surviving a failed refresh is
    what a later build would embed.
    """
    destination = destination if destination is not None else default_destination(model)
    if destination.is_file():
        if _digest(destination) == model.sha256:
            return destination
        destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".part")
    fetch(model.url, staging, model.sha256, client=client)
    os.replace(staging, destination)
    return destination


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify the bundled ONNX model.")
    parser.add_argument(
        "--destination",
        type=Path,
        default=None,
        help="where to place the model (default: src/soundboard/effects/models/)",
    )
    args = parser.parse_args(argv)

    path = ensure_model(DPDFNET, args.destination)
    print(f"{DPDFNET.filename} verified at {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
