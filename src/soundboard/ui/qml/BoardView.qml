import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."
import "components"

Item {
    HeaderBar {
        id: header
        anchors { top: parent.top; left: parent.left; right: parent.right }
        userEmail: App.userEmail
        micName: App.micName
        outName: App.outName
        canCheckForUpdates: App.updateModel.supported
        onSettingsClicked: App.open_settings()
        onStopAllClicked: App.stop_all()
        onLogOutClicked: App.log_out()
        onCheckForUpdatesClicked: App.updateModel.check(true)
    }

    UpdateBanner {
        id: updateBanner
        anchors { top: header.bottom; left: parent.left; right: parent.right }
        updateState: App.updateModel.state
        version: App.updateModel.version
        progress: App.updateModel.progress
        onDownloadClicked: App.updateModel.download()
        onRestartClicked: App.updateModel.restart()
    }

    TabBar {
        id: tabs
        objectName: "boardTabs"
        anchors { top: updateBanner.bottom; left: parent.left; right: parent.right }
        height: 42
        background: Rectangle { color: Theme.surface }

        TabButton {
            objectName: "soundsTab"
            text: "Sonidos"
        }
        TabButton {
            objectName: "effectsTab"
            text: "Efectos"
        }
    }

    StackLayout {
        anchors { top: tabs.bottom; left: parent.left; right: parent.right;
                  bottom: parent.bottom }
        currentIndex: tabs.currentIndex

        GridPage {}
        EffectsPage {}
    }
}
