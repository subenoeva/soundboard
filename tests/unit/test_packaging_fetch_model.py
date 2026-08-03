import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from soundboard.effects.neural import default_model_path
from soundboard.updater.errors import DigestMismatch, FeedUnavailable


def _load_fetch_model() -> ModuleType:
    """Loaded by path: the repo's packaging/ directory is shadowed on sys.path by the
    installed `packaging` distribution, so a plain import resolves to the wrong one.

    Registered in sys.modules before it executes because @dataclass resolves the
    module's namespace by name to tell a real annotation from a string one.
    """
    spec = importlib.util.spec_from_file_location(
        "soundboard_fetch_model", Path("packaging/fetch_model.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fetch_model = _load_fetch_model()
DPDFNET = fetch_model.DPDFNET
PinnedModel = fetch_model.PinnedModel
default_destination = fetch_model.default_destination
ensure_model = fetch_model.ensure_model
main = fetch_model.main

PAYLOAD = b"an ONNX graph, near enough" * 64
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
PINNED = PinnedModel(
    filename="fake_model.onnx",
    url="https://example.invalid/resolve/abc/fake_model.onnx",
    sha256=DIGEST,
)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _serving(content: bytes, status: int = 200) -> httpx.Client:
    return _client(lambda request: httpx.Response(status, content=content))


def _offline() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"the build went to the network for {request.url}")

    return _client(refuse)


def test_the_pinned_model_names_an_immutable_revision_not_a_branch() -> None:
    """dpdfnet's own downloader defaults to the mutable `main` ref and checks nothing,
    which would leave the model as the one unverified blob inside a signed release."""
    assert fetch_model.HF_REVISION != "main"
    assert re.fullmatch(r"[0-9a-f]{40}", fetch_model.HF_REVISION)
    assert re.fullmatch(r"[0-9a-f]{64}", DPDFNET.sha256)
    assert DPDFNET.url == (
        f"https://huggingface.co/{fetch_model.HF_REPO}/resolve/"
        f"{fetch_model.HF_REVISION}/{fetch_model.HF_PATH}"
    )
    assert DPDFNET.filename == "dpdfnet2_48khz_hr.onnx"


def test_the_default_destination_is_where_the_app_looks_for_the_model() -> None:
    assert default_destination() == default_model_path()


def test_a_missing_model_is_downloaded_and_verified(tmp_path: Path) -> None:
    destination = tmp_path / "models" / "fake_model.onnx"

    returned = ensure_model(PINNED, destination, client=_serving(PAYLOAD))

    assert returned == destination
    assert destination.read_bytes() == PAYLOAD


def test_the_download_requests_the_pinned_revision_url(tmp_path: Path) -> None:
    requested: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=PAYLOAD)

    ensure_model(PINNED, tmp_path / "fake_model.onnx", client=_client(record))

    assert requested == [PINNED.url]


def test_the_real_model_is_fetched_from_the_pinned_hugging_face_revision(tmp_path: Path) -> None:
    """The pinned URL and digest are the behaviour, not documentation: a build served
    anything other than those exact bytes must not produce a bundle."""
    requested: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=b"whatever main serves today")

    destination = tmp_path / "dpdfnet2_48khz_hr.onnx"
    with pytest.raises(DigestMismatch):
        ensure_model(destination=destination, client=_client(record))

    assert requested == [DPDFNET.url]
    assert fetch_model.HF_REVISION in requested[0]
    assert not destination.exists()


def test_an_already_verified_model_is_reused_without_touching_the_network(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "fake_model.onnx"
    destination.write_bytes(PAYLOAD)

    returned = ensure_model(PINNED, destination, client=_offline())

    assert returned == destination
    assert destination.read_bytes() == PAYLOAD


def test_a_file_with_the_wrong_digest_is_replaced_rather_than_trusted(tmp_path: Path) -> None:
    destination = tmp_path / "fake_model.onnx"
    destination.write_bytes(b"a model from some other revision")

    ensure_model(PINNED, destination, client=_serving(PAYLOAD))

    assert destination.read_bytes() == PAYLOAD


def test_a_failed_download_leaves_no_model_behind(tmp_path: Path) -> None:
    destination = tmp_path / "fake_model.onnx"

    with pytest.raises(FeedUnavailable):
        ensure_model(PINNED, destination, client=_serving(b"", status=500))

    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


def test_a_failed_download_does_not_leave_the_stale_file_in_place(tmp_path: Path) -> None:
    """A wrong-digest file that survives a failed refresh is worse than none: the next
    build would embed it, since nothing downstream hashes the model again."""
    destination = tmp_path / "fake_model.onnx"
    destination.write_bytes(b"a model from some other revision")

    with pytest.raises(FeedUnavailable):
        ensure_model(PINNED, destination, client=_serving(b"", status=500))

    assert not destination.exists()


def test_a_served_body_with_the_wrong_digest_is_rejected(tmp_path: Path) -> None:
    destination = tmp_path / "fake_model.onnx"

    with pytest.raises(DigestMismatch):
        ensure_model(PINNED, destination, client=_serving(b"not the pinned bytes"))

    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


def test_it_runs_as_a_script_against_an_explicit_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "models" / "dpdfnet2_48khz_hr.onnx"
    calls: list[tuple[Any, Path]] = []

    def record(model: Any, dest: Path | None = None, *, client: Any = None) -> Path:
        calls.append((model, dest if dest is not None else default_destination()))
        return destination

    monkeypatch.setattr(fetch_model, "ensure_model", record)

    assert main(["--destination", str(destination)]) == 0
    assert calls == [(DPDFNET, destination)]
