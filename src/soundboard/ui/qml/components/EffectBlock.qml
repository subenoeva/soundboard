import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Rectangle {
    id: root
    objectName: "effectBlock"
    property int rackIndex: -1
    property string kind: ""
    property string effectLabel: ""
    property string summary: ""
    property bool effectEnabled: true
    property real latencyMs: 0.0
    property string errorText: ""
    property bool loading: false
    property bool editorOpen: false
    property bool selected: false
    signal selectedRequested()
    signal toggleRequested(bool on)
    signal removeRequested()
    signal editorRequested()

    implicitWidth: 166
    implicitHeight: 142
    radius: Theme.radiusPad
    color: root.effectEnabled ? Theme.surface : Theme.padBg
    border.width: root.selected ? 2 : 1
    border.color: root.errorText !== "" ? Theme.danger
                  : root.selected ? Theme.accent : Theme.padBg

    Drag.active: dragArea.drag.active
    Drag.source: root
    Drag.keys: ["effect-block"]
    Drag.hotSpot.x: width / 2
    Drag.hotSpot.y: height / 2

    ColumnLayout {
        anchors { fill: parent; margins: Theme.pad }
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: root.effectLabel
                color: Theme.textPrimary
                font.bold: true
                font.pixelSize: 13
                elide: Text.ElideRight
            }
            Switch {
                id: bypass
                objectName: "effectBypass"
                checked: root.effectEnabled
                enabled: !root.loading && root.errorText === ""
                onClicked: root.toggleRequested(checked)
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.loading ? "Cargando…"
                  : root.errorText !== "" ? root.errorText : root.summary
            color: root.errorText !== "" ? Theme.danger : Theme.textSecondary
            font.pixelSize: 10
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            maximumLineCount: 3
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: root.latencyMs > 0 ? root.latencyMs.toFixed(1) + " ms" : "Sin latencia"
            color: Theme.textSecondary
            font.pixelSize: 10
        }

        RowLayout {
            Layout.fillWidth: true
            Button {
                id: reorderButton
                objectName: "effectReorderButton"
                Layout.preferredWidth: 36
                text: "✥"
                leftPadding: 4
                rightPadding: 4
                implicitHeight: 26
                hoverEnabled: true
                Accessible.name: "Mover"
                ToolTip.visible: hovered
                ToolTip.text: "Mover"

                MouseArea {
                    id: dragArea
                    objectName: "effectDragHandle"
                    anchors.fill: parent
                    cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    drag.target: root
                    onPressed: root.selectedRequested()
                    onReleased: {
                        root.Drag.drop()
                        root.x = 0
                        root.y = 0
                    }
                }
            }
            Button {
                id: editorButton
                objectName: "effectEditorButton"
                // Only a VST3 brings a window of its own; the built-in blocks are
                // drawn from their descriptors and have nothing else to show.
                visible: root.kind === "vst3"
                enabled: !root.loading && root.errorText === "" && !root.editorOpen
                Layout.preferredWidth: 36
                text: "🎛"
                leftPadding: 4
                rightPadding: 4
                implicitHeight: 26
                hoverEnabled: true
                Accessible.name: "Abrir la ventana del plugin"
                ToolTip.visible: hovered
                ToolTip.text: root.editorOpen
                              ? "La ventana del plugin ya está abierta"
                              : "Abrir la ventana del plugin"
                onClicked: root.editorRequested()
            }
            Button {
                Layout.fillWidth: true
                text: "Quitar"
                onClicked: root.removeRequested()
            }
        }
    }

}
