from typing import Any

from soundboard.audio.backend import DeviceInfo
from soundboard.audio.fake_backend import FakeBackend
from soundboard.ui.device_dialog import DeviceSettingsDialog
from soundboard.ui.layout_store import GridLayout

DEVICES = [
    DeviceInfo(0, "Realtek Microphone", "MME", 2, 0, 44_100.0),
    DeviceInfo(1, "CABLE Input", "MME", 0, 2, 48_000.0),
    DeviceInfo(2, "CABLE Output", "MME", 2, 0, 48_000.0),
]


def test_dialog_lists_inputs_and_outputs_separately(qtbot: Any) -> None:
    dialog = DeviceSettingsDialog(FakeBackend(DEVICES))
    qtbot.addWidget(dialog)

    mic_names = [dialog._mic.itemText(i) for i in range(dialog._mic.count())]
    out_names = [dialog._out.itemText(i) for i in range(dialog._out.count())]

    assert mic_names == ["Realtek Microphone", "CABLE Output"]
    assert out_names == ["CABLE Input"]


def test_dialog_defaults_to_4x6_when_no_current_layout(qtbot: Any) -> None:
    dialog = DeviceSettingsDialog(FakeBackend(DEVICES))
    qtbot.addWidget(dialog)

    assert dialog.selected_rows() == 4
    assert dialog.selected_cols() == 6


def test_dialog_preselects_the_current_layout(qtbot: Any) -> None:
    current = GridLayout(rows=2, cols=3, mic="Realtek Microphone", out="CABLE Input", blocksize=256)
    dialog = DeviceSettingsDialog(FakeBackend(DEVICES), current=current)
    qtbot.addWidget(dialog)

    assert dialog.selected_mic() == "Realtek Microphone"
    assert dialog.selected_out() == "CABLE Input"
    assert dialog.selected_rows() == 2
    assert dialog.selected_cols() == 3
