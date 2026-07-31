"""Update wiring for AppController: model construction, launch check, restart.

Split out of controller.py to keep it inside its line budget, the same reason
session_actions.py and engine_factory.py live next to it.

The restart lives here rather than in UpdateModel because it has to bring the engine
stack down first: an audio engine, a poll timer or a global keyboard hook that outlives
the process would keep the device claimed and the hook installed while the new instance
tries to take both.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from soundboard.ui.update_model import UpdateModel
from soundboard.updater.service import UpdateService, automatic_check_enabled, relaunch

if TYPE_CHECKING:
    from soundboard.ui.controller import AppController


def build_model(controller: AppController, service: UpdateService | None = None) -> UpdateModel:
    model = UpdateModel(service or UpdateService(), parent=controller)
    model.toast.connect(controller.toast)
    model.restartRequested.connect(lambda binary: restart(controller, binary))
    return model


def start_launch_check(model: UpdateModel) -> None:
    """Kick off the silent check a launch performs, unless it has been turned off."""
    if automatic_check_enabled():
        model.check()


def restart(controller: AppController, binary: str) -> None:
    controller.shutdown()
    relaunch(Path(binary))
    QCoreApplication.quit()
