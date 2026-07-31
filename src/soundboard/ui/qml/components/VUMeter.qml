import QtQuick
import ".."

Item {
    id: root
    property real level: 0.0

    implicitWidth: 120
    implicitHeight: 8

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.padBg
    }

    Item {
        clip: true
        width: root.width * Math.min(1, root.level)
        height: root.height

        Rectangle {
            width: root.width
            height: parent.height
            radius: height / 2
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.meterGreen }
                GradientStop { position: 0.75; color: Theme.meterAmber }
                GradientStop { position: 1; color: Theme.meterRed }
            }
        }
    }
}
