import QtQuick
import ".."

Item {
    id: root
    property real level: 0.0
    // Highest level seen recently: jumps up instantly, comes down only through the
    // decay animation below, so a transient stays readable after the bar has fallen.
    property real peak: 0.0

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

    Rectangle {
        objectName: "peakMarker"
        width: 2
        height: root.height
        radius: 1
        color: Theme.textPrimary
        opacity: 0.85
        visible: root.peak > 0.01
        // Never below the bar itself: the decay runs all the way to 0, so without the
        // max() the marker would sink into a level that is still sounding.
        x: (root.width - width) * Math.min(1, Math.max(root.peak, root.level))
    }

    onLevelChanged: {
        if (level >= peak) {
            decay.stop()
            hold.restart()
            peak = level
        }
    }

    Timer {
        id: hold
        interval: 900
        onTriggered: decay.start()
    }

    NumberAnimation {
        id: decay
        target: root
        property: "peak"
        to: 0
        duration: 700
        easing.type: Easing.InQuad
    }
}
