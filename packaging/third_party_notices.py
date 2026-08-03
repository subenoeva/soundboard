"""Generates the THIRD-PARTY-NOTICES file the frozen builds ship beside the binary.

The distribution obligations, not licence compatibility, are what needed closing here:
the bundles redistribute PySide6 (LGPL-3), pedalboard (GPL-3.0), onnxruntime (MIT) and
the rest of the closure, plus CEVA's Apache-2.0 model and the streaming loop vendored
from it. Apache-2.0 §4, GPL-3 §4 and LGPL-3 §4(b) all want their licence text shipped
rather than cited, so all three travel with the binary — a module docstring does not
discharge any of them.

The header ``render()`` writes carries the other half, which only a onefile build makes
sharp: see the comment on HEADER.

Entries are read from the metadata of what is actually installed, so a dependency bump
cannot leave the notices describing the previous version's terms. The one hand-written
entry is DPDFNet, which is not a distribution: it reaches users as a vendored loop and
a model file.

Both PyInstaller specs call ``write_notices()`` and add what it returns to ``datas``.
"""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

from soundboard.updater.feed import DEFAULT_REPO

NOTICES_NAME = "THIRD-PARTY-NOTICES"
APACHE_NAME = "LICENSE-Apache-2.0.txt"
GPL_NAME = "LICENSE-GPL-3.0.txt"
LGPL_NAME = "LICENSE-LGPL-3.0.txt"

_LICENSES = Path(__file__).resolve().parent / "licenses"
APACHE_SOURCE = _LICENSES / APACHE_NAME
LGPL_SOURCE = _LICENSES / LGPL_NAME
# The repository's own LICENSE, not a fourth copy of the GPL: the text the binary is
# accompanied by is then the text the project is licensed under, by construction.
GPL_SOURCE = Path(__file__).resolve().parents[1] / "LICENSE"

LICENCE_FILES: tuple[tuple[Path, str], ...] = (
    (GPL_SOURCE, GPL_NAME),
    (LGPL_SOURCE, LGPL_NAME),
    (APACHE_SOURCE, APACHE_NAME),
)

# The runtime dependency closure is what the bundle carries; anything only the build
# needs — PyInstaller, pytest, mypy — is outside it and stays out of the file. The roots
# are read from pyproject.toml rather than from the installed `soundboard` metadata,
# which goes stale in an editable install: it still listed no onnxruntime after the
# dependency was added, and the notices would have shipped without it.
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

_NAME_END = re.compile(r"[\s\[(<>=!~;]")

SOURCE_URL = f"https://github.com/{DEFAULT_REPO}"

# Why the file opens with this rather than with the first component: the Windows build is
# --onefile, so the Qt libraries PySide6 carries are inside the executable and a user
# cannot swap one for a build of their own. LGPL-3 §4(d)(1), the shared-library route the
# Linux COLLECT build takes for free, is therefore not available there, and §4(d)(0) is —
# but only if the corresponding application code is reachable and relinking is actually
# possible. Both hold here for the same reason: the whole program is GPL-3.0-or-later and
# its source, including the specs that produce these binaries, is public. Saying so is the
# part that was missing, and a reader of the binary is the one who needs to be told.
HEADER = f"""THIRD-PARTY NOTICES

Soundboard is free software under the GNU General Public License v3.0 or later.
The full text ships beside this file as {GPL_NAME}, and the complete
corresponding source for this binary is at
{SOURCE_URL}.

PySide6 and the Qt libraries it carries are used under LGPL-3.0-only
({LGPL_NAME}). The Windows build is a single self-extracting executable,
so those libraries are inside it rather than beside it: modifying Qt means
rebuilding rather than replacing a DLL.
That is LGPL-3 §4(d)(0), and the source above is the corresponding application code it
asks for. Nothing needed to relink is withheld, and the rebuild is:

    uv sync --group packaging
    uv run pyinstaller packaging/windows/soundboard.spec
    uv run pyinstaller packaging/linux/soundboard.spec

The components below are bundled with the application. Each remains under its own
licence.
"""


@dataclass(frozen=True)
class Notice:
    """One redistributed component, as it appears in the notices file."""

    name: str
    version: str
    license: str
    url: str = ""
    detail: str = ""


DPDFNET = Notice(
    name="DPDFNet",
    version="model dpdfnet2_48khz_hr.onnx",
    license="Apache-2.0",
    url="https://github.com/ceva-ip/DPDFNet",
    detail=(
        "Copyright 2025 CEVA\n"
        "soundboard/effects/neural.py adapts DPDFNet's streaming enhancer (the STFT\n"
        "loop, the Vorbis window, the overlap-add and the ONNX session construction).\n"
        "soundboard/effects/models/dpdfnet2_48khz_hr.onnx is redistributed unmodified,\n"
        "fetched from https://huggingface.co/Ceva-IP/DPDFNet at the revision pinned in\n"
        f"packaging/fetch_model.py. The full licence ships beside this file as {APACHE_NAME}."
    ),
)


@dataclass
class _Walk:
    seen: set[str] = field(default_factory=set)
    found: list[Notice] = field(default_factory=list)


def root_requirements(pyproject: Path = PYPROJECT) -> list[str]:
    """The distribution names in ``[project].dependencies``."""
    data: dict[str, Any] = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    requirements: list[str] = data["project"]["dependencies"]
    return [name for name in map(_requirement_name, requirements) if name]


def installed_notices(roots: Iterable[str] | None = None) -> list[Notice]:
    """Every installed distribution the app depends on, directly or transitively."""
    walk = _Walk()
    for root in root_requirements() if roots is None else roots:
        _visit(root, walk)
    return sorted(walk.found, key=lambda notice: notice.name.lower())


def collect() -> list[Notice]:
    """The installed closure plus the components that are not distributions."""
    return sorted([*installed_notices(), DPDFNET], key=lambda notice: notice.name.lower())


def render(entries: Iterable[Notice]) -> str:
    """The notices file text. Deterministic, so two builds of a tag produce one file."""
    lines = HEADER.splitlines()
    for entry in entries:
        heading = f"{entry.name} {entry.version}".strip()
        lines.append(heading)
        lines.append("-" * len(heading))
        lines.append(f"Licence: {entry.license}")
        if entry.url:
            lines.append(f"Source: {entry.url}")
        if entry.detail:
            lines.append("")
            lines.extend(entry.detail.splitlines())
        lines.append("")
    return "\n".join(lines)


def write_notices(out_dir: Path) -> list[tuple[str, str]]:
    """Write the notices and every licence text into ``out_dir``, as ``datas`` pairs.

    The destination is the bundle root, which is where a user looking for the licence
    of something they were shipped would expect to find it.
    """
    # Read before mkdir: a licence text that is missing fails the build with nothing
    # written, rather than leaving a notices directory the spec would happily ship.
    texts = [(name, source.read_bytes()) for source, name in LICENCE_FILES]
    out_dir.mkdir(parents=True, exist_ok=True)
    notices = out_dir / NOTICES_NAME
    notices.write_text(render(collect()), encoding="utf-8")
    written = [(str(notices), ".")]
    for name, text in texts:
        licence = out_dir / name
        licence.write_bytes(text)
        written.append((str(licence), "."))
    return written


def _visit(name: str, walk: _Walk) -> None:
    key = _canonical(name)
    if key in walk.seen:
        return
    walk.seen.add(key)
    try:
        dist = distribution(name)
    except PackageNotFoundError:
        # A requirement whose marker excludes this platform is simply not installed,
        # and nothing that is not installed can be inside the bundle.
        return
    metadata = dist.metadata
    walk.found.append(
        Notice(
            name=_field(metadata, "Name") or name,
            version=dist.version,
            license=_license(metadata),
            url=_url(metadata),
        )
    )
    for requirement in dist.requires or []:
        dependency = _requirement_name(requirement)
        if dependency:
            _visit(dependency, walk)


def _requirement_name(requirement: str) -> str | None:
    """The distribution name in a Requires-Dist line, or None if it is an extra.

    Extras are skipped rather than resolved: an optional dependency the environment
    does not have is not in the bundle either, and one it happens to have is reached
    through some other edge of the closure.
    """
    specifier, _, marker = requirement.partition(";")
    if "extra ==" in marker:
        return None
    match = _NAME_END.search(specifier.strip())
    name = specifier.strip()[: match.start()] if match else specifier.strip()
    return name or None


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _field(metadata: Any, name: str) -> str:
    """One header, or "". Read through ``get`` so an absent one is not a KeyError."""
    value = metadata.get(name)
    return str(value).strip() if value else ""


def _fields(metadata: Any, name: str) -> list[str]:
    values: list[str] = metadata.get_all(name) or []
    return [str(value).strip() for value in values]


def _license(metadata: Any) -> str:
    expression = _field(metadata, "License-Expression")
    if expression:
        return expression
    classifiers = [
        value.split(" :: ")[-1]
        for value in _fields(metadata, "Classifier")
        if value.startswith("License ::") and value != "License :: OSI Approved"
    ]
    if classifiers:
        return "; ".join(dict.fromkeys(classifiers))
    declared = _field(metadata, "License")
    if declared:
        # Some distributions paste their whole licence into the field; the notices file
        # names the terms and the full text belongs with the component itself.
        first = declared.splitlines()[0].strip()
        if first:
            return first
    return "see the component's own distribution"


def _url(metadata: Any) -> str:
    home = _field(metadata, "Home-page")
    if home:
        return home
    for entry in _fields(metadata, "Project-URL"):
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "source", "repository", "home"):
            return url.strip()
    return ""


def main(argv: list[str] | None = None) -> int:
    out_dir = Path(argv[0]) if argv else Path("build") / "notices"
    for source, _ in write_notices(out_dir):
        print(source)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
