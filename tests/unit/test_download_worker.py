from typing import Any

import numpy as np
from PySide6.QtCore import QThreadPool

from soundboard.ui.download_worker import DownloadWorker


def test_download_worker_emits_finished_with_the_resolved_pcm(qtbot: Any) -> None:
    pcm = np.full(10, 0.5, dtype=np.float32)
    worker = DownloadWorker(lambda: pcm)

    with qtbot.waitSignal(worker.signals.finished, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert np.array_equal(blocker.args[0], pcm)


def test_download_worker_emits_failed_with_the_exception_message(qtbot: Any) -> None:
    def _raise() -> np.ndarray:
        raise RuntimeError("no network")

    worker = DownloadWorker(_raise)

    with qtbot.waitSignal(worker.signals.failed, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert blocker.args[0] == "no network"
