"""First-run (and settings) dialog: pick the mic/out devices and the grid size."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from soundboard.audio.backend import AudioBackend
from soundboard.ui.layout_store import GridLayout


class DeviceSettingsDialog(QDialog):
    def __init__(
        self,
        backend: AudioBackend,
        current: GridLayout | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        devices = backend.list_devices()

        self._mic = QComboBox()
        self._mic.addItems([d.name for d in devices if d.max_input_channels > 0])
        self._out = QComboBox()
        self._out.addItems([d.name for d in devices if d.max_output_channels > 0])

        self._rows = QSpinBox()
        self._rows.setRange(1, 12)
        self._rows.setValue(current.rows if current else 4)
        self._cols = QSpinBox()
        self._cols.setRange(1, 12)
        self._cols.setValue(current.cols if current else 6)

        if current is not None:
            self._select(self._mic, current.mic)
            self._select(self._out, current.out)

        form = QFormLayout()
        form.addRow("Micrófono", self._mic)
        form.addRow("Cable virtual", self._out)
        form.addRow("Filas", self._rows)
        form.addRow("Columnas", self._cols)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _select(combo: QComboBox, name: str) -> None:
        index = combo.findText(name)
        if index >= 0:
            combo.setCurrentIndex(index)

    def selected_mic(self) -> str:
        return self._mic.currentText()

    def selected_out(self) -> str:
        return self._out.currentText()

    def selected_rows(self) -> int:
        return self._rows.value()

    def selected_cols(self) -> int:
        return self._cols.value()
