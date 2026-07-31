import QtQuick
import QtQuick.Controls.Basic
import "."

Item {
    anchors.fill: parent

    Rectangle {
        anchors.centerIn: parent
        width: 360
        radius: Theme.radiusPad
        color: Theme.surface
        height: column.implicitHeight + Theme.pad * 4

        Column {
            id: column
            anchors.centerIn: parent
            width: parent.width - Theme.pad * 4
            spacing: Theme.pad

            Text {
                width: parent.width
                text: "Dispositivos y grilla"
                color: Theme.textPrimary
                font.pixelSize: 18
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }

            Text {
                text: "Micrófono"
                color: Theme.textSecondary
                font.pixelSize: 11
            }
            ComboBox {
                id: micCombo
                width: parent.width
                model: App.inputDevices
                currentIndex: App.inputDevices.indexOf(App.micName)
            }

            Text {
                text: "Salida"
                color: Theme.textSecondary
                font.pixelSize: 11
            }
            ComboBox {
                id: outCombo
                width: parent.width
                model: App.outputDevices
                currentIndex: App.outputDevices.indexOf(App.outName)
            }

            Row {
                width: parent.width
                spacing: Theme.pad

                Column {
                    width: (parent.width - Theme.pad) / 2
                    spacing: 4
                    Text {
                        text: "Filas"
                        color: Theme.textSecondary
                        font.pixelSize: 11
                    }
                    SpinBox {
                        id: rowsSpin
                        width: parent.width
                        from: 1
                        to: 12
                        value: App.gridRows
                    }
                }

                Column {
                    width: (parent.width - Theme.pad) / 2
                    spacing: 4
                    Text {
                        text: "Columnas"
                        color: Theme.textSecondary
                        font.pixelSize: 11
                    }
                    SpinBox {
                        id: colsSpin
                        width: parent.width
                        from: 1
                        to: 12
                        value: App.gridCols
                    }
                }
            }

            Text {
                width: parent.width
                text: App.setupError
                color: Theme.danger
                visible: text !== ""
                wrapMode: Text.Wrap
            }

            Button {
                width: parent.width
                text: "Aplicar"
                onClicked: App.apply_devices(micCombo.currentText, outCombo.currentText,
                                              rowsSpin.value, colsSpin.value)
            }

            Button {
                width: parent.width
                text: "Cancelar"
                visible: App.gridModel !== null
                onClicked: App.cancel_settings()
            }
        }
    }
}
