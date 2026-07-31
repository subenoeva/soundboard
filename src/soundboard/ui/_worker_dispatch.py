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
    on_finished: Callable[[int, Worker, Any], None],
    on_failed: Callable[[int, Worker, str], None],
) -> None:
    """Track ``worker``, bind its signals to ``index``, and submit it to the pool.

    QThreadPool does not keep Python's refcount alive across the thread hop; without
    ``active_workers`` holding a reference, the worker (and its signals) can be
    garbage collected before ``run()`` finishes, silently dropping the result.
    """
    active_workers.add(worker)
    worker.signals.finished.connect(
        lambda result, i=index, w=worker: on_finished(i, w, result)
    )
    worker.signals.failed.connect(
        lambda message, i=index, w=worker: on_failed(i, w, message)
    )
    QThreadPool.globalInstance().start(worker)
