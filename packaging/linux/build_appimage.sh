#!/usr/bin/env bash
# Assembles the PyInstaller onedir build produced by packaging/linux/soundboard.spec
# into a single-file AppImage. Run from the repo root with one argument: the output
# .AppImage path (e.g. soundboard-v1.2.3-linux-x86_64.AppImage).
#
# See docs/superpowers/specs/2026-07-30-standalone-executables-design.md.
set -euo pipefail

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

output="$1"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
appdir="${work_dir}/AppDir"

mkdir -p "${appdir}/usr/bin"
cp -r dist/soundboard "${appdir}/usr/bin/soundboard"

# sounddevice's Linux wheel does not bundle PortAudio (ci.yml installs it via apt to
# run the tests) — bundle the system copy so the AppImage needs no runtime dependency
# beyond ALSA, present on practically any Linux distro with audio.
# `|| true`: under `set -e`, find exits non-zero when it hits an unreadable directory
# before -quit, which would abort here instead of printing the message below.
portaudio_so="$(find /usr -name 'libportaudio.so.2' -print -quit 2>/dev/null || true)"
if [[ -z "${portaudio_so}" ]]; then
    echo "libportaudio.so.2 not found — install libportaudio2 before building" >&2
    exit 1
fi
cp "${portaudio_so}" "${appdir}/usr/bin/soundboard/_internal/"

cp "${script_dir}/AppRun" "${appdir}/AppRun"
chmod +x "${appdir}/AppRun"
cp "${script_dir}/soundboard.desktop" "${appdir}/soundboard.desktop"
python3 "${script_dir}/make_icon.py" "${appdir}/soundboard.png"

appimagetool="${work_dir}/appimagetool-x86_64.AppImage"
curl -sL -o "${appimagetool}" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x "${appimagetool}"

# GitHub Actions runners have no FUSE; extract-and-run avoids needing to mount the tool.
APPIMAGE_EXTRACT_AND_RUN=1 "${appimagetool}" "${appdir}" "${output}"
