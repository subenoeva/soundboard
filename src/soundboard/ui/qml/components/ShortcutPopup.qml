import QtQuick
import QtQuick.Controls.Basic
import ".."

Popup {
    id: root
    property int cellIndex: -1
    property string currentShortcut: ""

    signal accepted(int cellIndex, string combo)

    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: 320
    padding: Theme.pad * 2

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusPad
    }

    function openFor(index) {
        cellIndex = index
        field.text = currentShortcut
        open()
    }

    contentItem: Column {
        spacing: Theme.pad

        TextField {
            id: field
            width: parent.width
            text: root.currentShortcut
            placeholderText: "<ctrl>+<alt>+1"
        }

        Text {
            width: parent.width
            text: "Formato pynput. Vacío = quitar atajo"
            color: Theme.textSecondary
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }

        Row {
            width: parent.width
            spacing: Theme.pad
            layoutDirection: Qt.RightToLeft

            Button {
                text: "Cancelar"
                onClicked: root.close()
            }
            Button {
                text: "Guardar"
                onClicked: {
                    root.accepted(root.cellIndex, field.text)
                    root.close()
                }
            }
        }
    }
}
