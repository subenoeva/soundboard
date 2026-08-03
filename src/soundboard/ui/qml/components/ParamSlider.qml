import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Item {
    id: root
    property string paramName: ""
    property string label: ""
    property real minimum: 0.0
    property real maximum: 1.0
    property real currentValue: 0.0
    property string unit: ""
    signal edited(string name, real value)

    implicitWidth: 220
    implicitHeight: 54

    ColumnLayout {
        anchors.fill: parent
        spacing: 2

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: root.label
                color: Theme.textSecondary
                elide: Text.ElideRight
                font.pixelSize: 11
            }
            Text {
                text: Number(root.currentValue).toLocaleString(Qt.locale(), "f", 1)
                      + (root.unit === "" ? "" : " " + root.unit)
                color: Theme.textPrimary
                font.pixelSize: 11
            }
        }

        Slider {
            Layout.fillWidth: true
            from: root.minimum
            to: root.maximum
            value: root.currentValue
            onMoved: root.edited(root.paramName, value)
        }
    }
}
