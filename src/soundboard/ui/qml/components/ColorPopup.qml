import QtQuick
import QtQuick.Controls.Basic
import ".."

Popup {
    id: root
    property int cellIndex: -1

    readonly property var presets: ["#e5484d", "#f5a524", "#3dd68c", "#29a383",
                                     "#0091ff", "#7c5cff", "#d6409f", "#f76b15"]

    signal picked(int cellIndex, string color)

    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    padding: Theme.pad * 2

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusPad
    }

    function openFor(index) {
        cellIndex = index
        open()
    }

    contentItem: Column {
        spacing: Theme.pad

        Grid {
            columns: 4
            rows: 2
            spacing: Theme.pad

            Repeater {
                model: root.presets

                Rectangle {
                    width: 32
                    height: 32
                    radius: Theme.radiusControl
                    color: modelData

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            root.picked(root.cellIndex, modelData)
                            root.close()
                        }
                    }
                }
            }
        }

        Button {
            width: parent.width
            text: "Sin color"
            onClicked: {
                root.picked(root.cellIndex, "")
                root.close()
            }
        }
    }
}
