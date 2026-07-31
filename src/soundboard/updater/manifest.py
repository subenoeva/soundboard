"""Parsing of the signed ``SHA256SUMS`` release manifest.

Format, produced by the ``sign`` job of the release workflow::

    version v0.4.0
    9f86d081...  soundboard-v0.4.0-windows.exe
    2c26b46b...  soundboard-v0.4.0-linux-x86_64.AppImage

The explicit ``version`` line costs compatibility with ``sha256sum -c`` (recover it with
``tail -n +2 SHA256SUMS | sha256sum -c``) and buys an unambiguous parse: deriving the
version from the asset filenames instead would need a second regex and a tie-break for
the case where the two disagree.

Parsing is strict throughout. Every rejection here is a manifest the release pipeline
could not have produced, which means something is wrong upstream — being permissive
would only push the confusion to the point where a binary gets swapped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from soundboard.updater.errors import ManifestError

WINDOWS_ASSET = "soundboard-{tag}-windows.exe"
LINUX_ASSET = "soundboard-{tag}-linux-x86_64.AppImage"

_VERSION_LINE = re.compile(r"^version (v(\d+)\.(\d+)\.(\d+))$")
# Two spaces between digest and name: the separator sha256sum emits in binary mode.
_DIGEST_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse ``v1.2.3`` or ``1.2.3``. Pre-release suffixes are rejected rather than
    ordered — this project's release automation never produces them, and guessing at a
    precedence rule for a tag that cannot exist is how downgrades slip through."""
    match = _VERSION.match(text.strip())
    if match is None:
        raise ManifestError(f"not a release version: {text!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def expected_asset_names(tag: str) -> tuple[str, str]:
    """The asset filenames a manifest for ``tag`` must list, in manifest order."""
    return WINDOWS_ASSET.format(tag=tag), LINUX_ASSET.format(tag=tag)


@dataclass(frozen=True)
class Manifest:
    tag: str
    version: tuple[int, int, int]
    digests: Mapping[str, str]

    def digest_for(self, asset_name: str) -> str:
        try:
            return self.digests[asset_name]
        except KeyError:
            raise ManifestError(f"manifest {self.tag} lists no asset {asset_name!r}") from None

    def is_newer_than(self, running_version: str) -> bool:
        return self.version > parse_version(running_version)


def parse(text: str) -> Manifest:
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ManifestError("release manifest is empty")

    version_match = _VERSION_LINE.match(lines[0])
    if version_match is None:
        raise ManifestError(f"first manifest line is not a version: {lines[0]!r}")
    tag, major, minor, patch = version_match.groups()

    digests: dict[str, str] = {}
    for line in lines[1:]:
        digest_match = _DIGEST_LINE.match(line)
        if digest_match is None:
            raise ManifestError(f"malformed digest line: {line!r}")
        digest, name = digest_match.groups()
        digests[name] = digest

    # Names carry the tag, so a manifest mixing releases would otherwise let a download
    # for one version be validated against the digest published for another.
    missing = [name for name in expected_asset_names(tag) if name not in digests]
    if missing:
        raise ManifestError(f"manifest {tag} is missing assets: {', '.join(missing)}")

    return Manifest(
        tag=tag,
        version=(int(major), int(minor), int(patch)),
        digests=MappingProxyType(digests),
    )
