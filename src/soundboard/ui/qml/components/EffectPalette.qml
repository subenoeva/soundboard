import QtQuick
import QtQuick.Controls.Basic
import ".."

Rectangle {
    id: root
    objectName: "effectPalette"
    property var catalog: []
    signal effectPicked(string kind)
    signal vstRequested()

    implicitHeight: 62
    radius: Theme.radiusPad
    color: Theme.surface

    Text {
        id: paletteLabel
        anchors { left: parent.left; leftMargin: Theme.pad;
                  verticalCenter: parent.verticalCenter }
        text: "Añadir"
        color: Theme.textSecondary
        font.bold: true
        font.pixelSize: 11
    }

    Flickable {
        id: scroller
        objectName: "paletteScroller"
        anchors { left: paletteLabel.right; right: parent.right;
                  top: parent.top; bottom: parent.bottom;
                  leftMargin: Theme.pad; rightMargin: Theme.pad }
        contentWidth: paletteRow.implicitWidth
        contentHeight: height
        clip: true

        Row {
            id: paletteRow
            height: parent.height
            spacing: Theme.pad

            Repeater {
                model: root.catalog
                Button {
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label || ""
                    onClicked: root.effectPicked(modelData.kind || "")
                }
            }

            Button {
                objectName: "effectVstButton"
                anchors.verticalCenter: parent.verticalCenter
                text: "VST3…"
                onClicked: root.vstRequested()
            }
        }
    }
}
