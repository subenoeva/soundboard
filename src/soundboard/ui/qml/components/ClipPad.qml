import QtQuick
import QtQuick.Controls.Basic
import ".."

Rectangle {
    id: root
    property string name: ""
    property string shortcut: ""
    property string cellColor: ""
    property string cellState: "empty"
    property real progress: 0.0
    signal clicked()
    signal rightClicked()
    signal fileDropped(string url)

    radius: Theme.radiusPad
    color: cellState === "empty" ? Theme.padBg
         : cellColor !== "" ? Qt.darker(cellColor, 2.8) : Theme.surface
    border.width: 2
    border.color: cellState === "playing" ? Theme.accent : "transparent"
    Behavior on border.color { ColorAnimation { duration: 150 } }

    onCellStateChanged: if (cellState === "playing") playPulse.restart()

    // Deliberately a border pulse and not a blurred halo: a real glow needs
    // MultiEffect / Qt5Compat.GraphicalEffects, which the frozen builds would have to
    // carry as an extra hidden import for one decorative frame.
    SequentialAnimation {
        id: playPulse
        objectName: "playPulse"
        NumberAnimation {
            target: root; property: "border.width"
            from: 2; to: 6; duration: 90; easing.type: Easing.OutQuad
        }
        NumberAnimation {
            target: root; property: "border.width"
            to: 2; duration: 240; easing.type: Easing.InQuad
        }
    }

    Rectangle {
        visible: root.cellColor !== ""
        color: root.cellColor
        height: 4
        radius: 2
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 6 }
    }

    Column {
        anchors.centerIn: parent
        spacing: 4
        width: parent.width - 16
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.name
            color: Theme.textPrimary
            elide: Text.ElideRight
            font.pixelSize: 13
            font.bold: true
        }
        Rectangle {
            objectName: "shortcutBadge"
            visible: root.shortcut !== ""
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width, shortcutLabel.implicitWidth + 12)
            height: shortcutLabel.implicitHeight + 4
            radius: Theme.radiusControl
            color: Theme.padBg
            Text {
                id: shortcutLabel
                objectName: "shortcutLabel"
                anchors { fill: parent; leftMargin: 6; rightMargin: 6 }
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: root.shortcut
                color: Theme.textSecondary
                elide: Text.ElideMiddle
                font.pixelSize: 10
            }
        }
    }

    BusyIndicator {
        visible: root.cellState === "loading"
        running: visible
        anchors.centerIn: parent
        width: 28; height: 28
    }

    Rectangle {
        visible: root.cellState === "playing"
        anchors { bottom: parent.bottom; left: parent.left; margins: 6 }
        width: (parent.width - 12) * Math.min(1, root.progress)
        height: 3
        radius: 1.5
        color: Theme.accent
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: (mouse) => {
            if (mouse.button === Qt.RightButton)
                root.rightClicked()
            else
                root.clicked()
        }
    }

    DropArea {
        anchors.fill: parent
        enabled: root.cellState === "empty"
        onDropped: (drop) => {
            if (drop.hasUrls)
                root.fileDropped(drop.urls[0])
        }
    }
}
