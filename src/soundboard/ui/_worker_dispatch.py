"""Private glue for GridModel: submits a background worker and wires its signals.

Split out of grid_model.py purely to keep that file under its line budget — this
module has no independent API surface, it's boilerplate shared by the download
(remote playback) and upload (local file assignment) paths.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThreadPool

from soundboard.ui.download_worker import DownloadWorker
from soundboard.ui.upload_worker import UploadWorker

Worker = DownloadWorker | UploadWorker


def dispatch_worker(
    active_workers: set[Worker],
    worker: Worker,
    index: int,
    on_finished: Callable[[int, Any], None],
    on_failed: Callable[[int, str], None],
    *,
    is_live: Callable[[], bool] = lambda: True,
) -> None:
    """Track ``worker``, bind its signals to ``index``, and submit it to the pool.

    QThreadPool does not keep Python's refcount alive across the thread hop; without
    ``active_workers`` holding a reference, the worker (and its signals) can be
    garbage collected before ``run()`` finishes, silently dropping the result.

    ``is_live`` is re-checked when the result lands, never at dispatch time: a model
    retired while the worker was running (a device hot-swap rebuilds the whole model
    stack) must not act on the result — see ``GridModel.detach``. The check is pure
    Python on purpose, so it still answers after the retired model's C++ half is gone.
    """
    active_workers.add(worker)

    def deliver(callback: Callable[[int, Any], None], payload: Any) -> None:
        active_workers.discard(worker)
        if is_live():
            callback(index, payload)

    worker.signals.finished.connect(lambda result: deliver(on_finished, result))
    worker.signals.failed.connect(lambda message: deliver(on_failed, message))
    QThreadPool.globalInstance().start(worker)
