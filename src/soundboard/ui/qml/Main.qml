import QtQuick
import QtQuick.Controls.Basic
import "."
import "components"

ApplicationWindow {
    id: root
    visible: true
    width: 960
    height: 640
    minimumWidth: 640
    minimumHeight: 420
    title: "Soundboard"
    color: Theme.windowBg

    onClosing: (close) => {
        if (App.view === "login") {
            Qt.quit()          // no session, so nothing worth keeping in the tray
        } else {
            close.accepted = false
            root.hide()        // the tray keeps the audio engine alive
        }
    }

    Loader {
        anchors.fill: parent
        source: App.view === "login" ? "LoginView.qml"
              : App.view === "setup" ? "DeviceSetupView.qml"
              : "BoardView.qml"
    }

    Toast {
        id: toast
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom;
                  bottomMargin: 24 }
        width: Math.min(parent.width - 48, 480)
        height: 40
    }

    Connections {
        target: App
        function onToast(message) { toast.show(message) }
    }
}
