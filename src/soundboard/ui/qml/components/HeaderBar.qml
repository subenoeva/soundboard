import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Rectangle {
    id: root
    property string userEmail: ""
    property string micName: ""
    property string outName: ""
    signal settingsClicked()
    signal stopAllClicked()

    height: 48
    color: Theme.surface

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.pad * 2
        anchors.rightMargin: Theme.pad * 2
        spacing: Theme.pad

        Text {
            text: "Soundboard"
            color: Theme.textPrimary
            font.bold: true
            font.pixelSize: 15
        }

        Item { Layout.fillWidth: true }

        ColumnLayout {
            spacing: 0
            Text {
                Layout.alignment: Qt.AlignRight
                text: root.userEmail
                color: Theme.textSecondary
                font.pixelSize: 11
            }
            Text {
                Layout.alignment: Qt.AlignRight
                text: root.micName + " → " + root.outName
                color: Theme.textSecondary
                font.pixelSize: 11
            }
        }

        Button {
            text: "Ajustes"
            onClicked: root.settingsClicked()
        }

        Button {
            text: "Detener todo"
            onClicked: root.stopAllClicked()
            contentItem: Text {
                text: "Detener todo"
                color: "white"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: Theme.radiusControl
                color: Theme.danger
            }
        }
    }
}
