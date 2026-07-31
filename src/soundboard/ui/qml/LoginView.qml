import QtQuick
import QtQuick.Controls.Basic
import "."

Item {
    anchors.fill: parent

    Rectangle {
        anchors.centerIn: parent
        width: 320
        radius: Theme.radiusPad
        color: Theme.surface
        height: column.implicitHeight + Theme.pad * 4

        Column {
            id: column
            anchors.centerIn: parent
            width: parent.width - Theme.pad * 4
            spacing: Theme.pad

            Text {
                width: parent.width
                text: "Soundboard"
                color: Theme.textPrimary
                font.pixelSize: 18
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }

            TextField {
                id: emailField
                width: parent.width
                placeholderText: "Email"
            }

            TextField {
                id: passwordField
                width: parent.width
                placeholderText: "Contraseña"
                echoMode: TextInput.Password
            }

            Text {
                width: parent.width
                text: App.loginError
                color: Theme.danger
                visible: text !== ""
                wrapMode: Text.Wrap
            }

            Button {
                width: parent.width
                text: "Ingresar"
                onClicked: App.log_in(emailField.text, passwordField.text)
            }

            Button {
                width: parent.width
                text: "Crear cuenta"
                onClicked: App.sign_up(emailField.text, passwordField.text)
            }
        }
    }
}
