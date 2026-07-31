"""The Ed25519 public key release manifests are signed with.

Deliberately hardcoded here rather than baked in at build time the way
``_baked_defaults.py`` carries the Supabase config: public keys are public, and keeping
this one in the source tree means it cannot be swapped by whoever controls the CI
secrets, and that rotating it costs a reviewable commit. The private half lives only in
the SOUNDBOARD_UPDATE_SIGNING_KEY repository secret.
"""

from __future__ import annotations

UPDATE_PUBLIC_KEY = bytes.fromhex(
    "af770598c946119dd681a58c0204c2fc0a6bec7a82bc846b15e626c9c38a5c9f"
)
