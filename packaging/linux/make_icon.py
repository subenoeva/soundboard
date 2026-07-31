"""Generates a flat-color placeholder PNG icon for the AppImage.

No custom icon design is in scope — this only needs to exist so appimagetool has
something to point ``Icon=`` at. Uses only the standard library so the release
workflow doesn't need an extra system package (e.g. ImageMagick) or Python
dependency (e.g. Pillow) just to draw one flat-color square.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

_COLOR = (0x2D, 0x2D, 0x2D)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def make_icon(path: Path, size: int = 256) -> None:
    row = bytes([0]) + bytes(_COLOR) * size  # filter-type byte + RGB pixels
    raw = row * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit depth, RGB
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args(argv)
    make_icon(args.output, args.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
