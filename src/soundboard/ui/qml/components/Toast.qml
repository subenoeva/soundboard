import QtQuick
import ".."

Rectangle {
    id: root
    radius: Theme.radiusControl
    color: Theme.surface
    border.color: Theme.accent
    opacity: 0

    implicitWidth: label.implicitWidth + Theme.pad * 4
    implicitHeight: label.implicitHeight + Theme.pad * 2

    Behavior on opacity { NumberAnimation { duration: 200 } }

    function show(text) {
        label.text = text
        opacity = 1
        hideTimer.restart()
    }

    Text {
        id: label
        anchors.centerIn: parent
        color: Theme.textPrimary
        font.pixelSize: 12
    }

    Timer {
        id: hideTimer
        interval: 4000
        onTriggered: parent.opacity = 0
    }
}
