from typing import Any

from PySide6.QtCore import QThreadPool

from soundboard.remote.models import Sound
from soundboard.ui.upload_worker import UploadWorker

_SOUND = Sound(
    id="sound-1",
    owner_id="owner-1",
    category_id=None,
    name="airhorn",
    sha256="deadbeef",
    storage_path="deadbeef.f32",
    source_filename="airhorn.wav",
    duration_frames=480,
    orig_samplerate=48_000,
    orig_channels=1,
    gain_db=0.0,
    trim_start_frames=0,
    trim_end_frames=None,
    loop=False,
    color=None,
)


def test_upload_worker_emits_finished_with_the_uploaded_sound(qtbot: Any) -> None:
    worker = UploadWorker(lambda: _SOUND)

    with qtbot.waitSignal(worker.signals.finished, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert blocker.args[0] is _SOUND


def test_upload_worker_emits_failed_with_the_exception_message(qtbot: Any) -> None:
    def _raise() -> Sound:
        raise RuntimeError("no network")

    worker = UploadWorker(_raise)

    with qtbot.waitSignal(worker.signals.failed, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert blocker.args[0] == "no network"
