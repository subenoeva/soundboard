#!/usr/bin/env bash
# Fail the build when the bundle needs a library from the host beyond the handful every
# desktop already has.
#
# PyInstaller collects host libraries by looking at what the build machine has installed,
# so the contents of the bundle depend on the build machine's package list. A runner
# missing libxcb-shape0 silently produces an AppImage that cannot open a window, and
# nothing says so until Qt fails to load its platform plugin at run time — which is how
# three releases in a row each surfaced exactly one more missing library.
#
# This looks at DT_NEEDED rather than at what fails to resolve here, so it reports the
# whole set at once and gives the same answer on any machine.
#
# Usage: check_bundle_deps.sh <path to the _internal directory>
set -euo pipefail

root="${1:?usage: check_bundle_deps.sh <bundle _internal dir>}"
[[ -d "$root" ]] || { echo "not a directory: $root" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

find "$root" -name '*.so*' -type f -printf '%f\n' | sort -u >"${work}/shipped"

find "$root" \( -name '*.so*' -o -type f -perm -u+x \) -type f -print0 |
    xargs -0 -r -n1 readelf -d 2>/dev/null |
    sed -n 's/.*NEEDED.*\[\(.*\)\]/\1/p' | sort -u >"${work}/needed"

# The C runtime and the toolchain: always present, and bundling them breaks more than it
# fixes. Below that, the graphics and display stack, which has to come from the host
# because it is tied to the driver and to the running compositor.
cat >"${work}/allowed" <<'EOF'
ld-linux-x86-64.so.2
libEGL.so.1
libGL.so.1
libc.so.6
libdl.so.2
libdrm.so.2
libgcc_s.so.1
libm.so.6
libmvec.so.1
libpthread.so.0
libresolv.so.2
librt.so.1
libstdc++.so.6
libutil.so.1
libwayland-client.so.0
libwayland-cursor.so.0
libwayland-egl.so.1
libxcb.so.1
EOF
sort -u "${work}/allowed" -o "${work}/allowed"

comm -23 "${work}/needed" "${work}/shipped" |
    comm -23 - "${work}/allowed" >"${work}/unexpected"

if [[ -s "${work}/unexpected" ]]; then
    echo "the bundle depends on libraries it does not ship and cannot assume:" >&2
    while read -r lib; do
        users=""
        count=0
        while IFS= read -r candidate; do
            if readelf -d "$candidate" 2>/dev/null | grep -q "\[${lib}\]"; then
                users="${users} $(basename "$candidate")"
                count=$((count + 1))
                if [[ $count -ge 3 ]]; then
                    break
                fi
            fi
        done < <(find "$root" -name '*.so*' -type f)
        printf '  %-32s needed by:%s\n' "$lib" "${users:- unknown}" >&2
    done <"${work}/unexpected"
    echo >&2
    echo "either install the package that provides each one on the build machine, so" >&2
    echo "PyInstaller collects it, or prune whatever pulls it in." >&2
    exit 1
fi

echo "bundle needs only the host libraries every desktop has:"
grep -vE 'lib(c|m|dl|rt|util|pthread|resolv|gcc_s|stdc\+\+|mvec)\.so|ld-linux' \
    "${work}/allowed" | sed 's/^/  /'
