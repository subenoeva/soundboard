import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Rectangle {
    id: root
    objectName: "headerBar"
    property string userEmail: ""
    property string micName: ""
    property string outName: ""
    // False for a source checkout or a pip install, where there is no single file to
    // replace — the entry is hidden rather than offering an action that can only fail.
    property bool canCheckForUpdates: false
    signal settingsClicked()
    signal stopAllClicked()
    signal logOutClicked()
    signal checkForUpdatesClicked()

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
            objectName: "checkUpdatesButton"
            text: "Buscar actualizaciones"
            visible: root.canCheckForUpdates
            onClicked: root.checkForUpdatesClicked()
        }

        Button {
            text: "Ajustes"
            onClicked: root.settingsClicked()
        }

        Button {
            text: "Cerrar sesión"
            onClicked: root.logOutClicked()
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
