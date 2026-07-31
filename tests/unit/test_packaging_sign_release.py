import base64
import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from soundboard.updater.feed import HttpReleaseFeed
from soundboard.updater.manifest import parse

TAG = "v0.4.0"


def _load_sign_release() -> ModuleType:
    """Loaded by path: the repo's packaging/ directory is shadowed on sys.path by the
    installed `packaging` distribution, so a plain import resolves to the wrong one."""
    spec = importlib.util.spec_from_file_location(
        "soundboard_sign_release", Path("packaging/sign_release.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sign_release = _load_sign_release()
MANIFEST_NAME = sign_release.MANIFEST_NAME
SIGNATURE_NAME = sign_release.SIGNATURE_NAME
build_manifest = sign_release.build_manifest
main = sign_release.main
public_key_hex = sign_release.public_key_hex
write_release_files = sign_release.write_release_files


@pytest.fixture
def secret_key() -> str:
    seed = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    return base64.b64encode(seed).decode()


@pytest.fixture
def assets(tmp_path: Path) -> list[Path]:
    windows = tmp_path / f"soundboard-{TAG}-windows.exe"
    linux = tmp_path / f"soundboard-{TAG}-linux-x86_64.AppImage"
    windows.write_bytes(b"windows build")
    linux.write_bytes(b"linux build")
    return [windows, linux]


def test_the_manifest_is_what_the_updater_parses(assets: list[Path]) -> None:
    manifest = parse(build_manifest(TAG, assets))

    assert manifest.tag == TAG
    assert manifest.digest_for(assets[0].name) == hashlib.sha256(b"windows build").hexdigest()
    assert manifest.digest_for(assets[1].name) == hashlib.sha256(b"linux build").hexdigest()


def test_the_signed_release_verifies_end_to_end(
    tmp_path: Path, assets: list[Path], secret_key: str
) -> None:
    """The one test that ties the CI producer to the shipped consumer: if either side
    changes format, key handling or line endings, this fails."""
    write_release_files(TAG, assets, secret_key, tmp_path)
    routes = {
        MANIFEST_NAME: (tmp_path / MANIFEST_NAME).read_text(),
        SIGNATURE_NAME: (tmp_path / SIGNATURE_NAME).read_text(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, text=routes[name]) if name in routes else httpx.Response(404)

    feed = HttpReleaseFeed(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        public_key=bytes.fromhex(public_key_hex(secret_key)),
    )

    manifest = feed.latest()

    assert manifest is not None
    assert manifest.tag == TAG


def test_manifest_lines_end_with_a_newline_and_nothing_else(
    tmp_path: Path, assets: list[Path], secret_key: str
) -> None:
    """A CRLF here would change the signed bytes on one platform and not the other."""
    write_release_files(TAG, assets, secret_key, tmp_path)

    assert "\r" not in (tmp_path / MANIFEST_NAME).read_text(newline="")


def test_print_public_key_matches_the_signing_key(
    secret_key: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rotating the key means replacing the constant in updater/keys.py; deriving it by
    hand is how a typo gets shipped."""
    main(["v0.0.0", "--secret-key", secret_key, "--print-public-key"])

    assert capsys.readouterr().out.strip() == public_key_hex(secret_key)


def test_main_refuses_to_sign_a_release_with_a_missing_asset(
    tmp_path: Path, assets: list[Path], secret_key: str
) -> None:
    """Otherwise a failed build job yields a release the updater rejects on that
    platform only, which is the hardest kind of breakage to notice."""
    with pytest.raises(SystemExit):
        main(
            [
                TAG,
                str(assets[0]),
                str(tmp_path / "soundboard-v0.4.0-linux-x86_64.AppImage.missing"),
                "--secret-key",
                secret_key,
                "--out-dir",
                str(tmp_path),
            ]
        )

    assert not (tmp_path / MANIFEST_NAME).exists()
