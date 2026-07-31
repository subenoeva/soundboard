import QtQuick
import QtQuick.Controls.Basic
import "."
import "components"

Item {
    HeaderBar {
        id: header
        anchors { top: parent.top; left: parent.left; right: parent.right }
        userEmail: App.userEmail
        micName: App.micName
        outName: App.outName
        onSettingsClicked: App.open_settings()
        onStopAllClicked: App.stop_all()
        onLogOutClicked: App.log_out()
    }

    GridView {
        id: grid
        anchors { top: header.bottom; left: parent.left; right: parent.right;
                  bottom: footer.top; margins: Theme.pad }
        model: App.gridModel
        interactive: false
        cellWidth: Math.floor(width / App.gridCols)
        cellHeight: Math.floor(height / App.gridRows)
        delegate: Item {
            width: grid.cellWidth
            height: grid.cellHeight
            ClipPad {
                anchors { fill: parent; margins: Theme.pad / 2 }
                name: model.name
                shortcut: model.shortcut
                cellColor: model.cellColor
                cellState: model.cellState
                progress: model.progress
                onClicked: App.gridModel.play(index)
                onRightClicked: contextMenu.openFor(index, model.cellState, model.shortcut)
                onFileDropped: (url) => App.gridModel.assign_local(index, url)
            }
        }
    }

    Rectangle {
        id: footer
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: 36
        color: Theme.surface
        Row {
            anchors { fill: parent; margins: Theme.pad }
            spacing: Theme.pad * 2
            VUMeter {
                width: 180; height: parent.height
                level: App.bridge !== null ? App.bridge.peak : 0
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: App.bridge !== null ? App.bridge.metricsText : ""
                color: Theme.textSecondary
                font.pixelSize: 11
            }
        }
    }

    Menu {
        id: contextMenu
        property int cellIndex: -1
        property string cellState: "empty"
        property string cellShortcut: ""
        function openFor(index, state, shortcut) {
            cellIndex = index; cellState = state; cellShortcut = shortcut || ""; popup()
        }
        MenuItem {
            text: "Asignar desde biblioteca"
            enabled: contextMenu.cellState === "empty"
            onTriggered: libraryPopup.openFor(contextMenu.cellIndex)
        }
        MenuItem {
            text: "Asignar atajo"
            enabled: contextMenu.cellState !== "empty"
            onTriggered: {
                shortcutPopup.currentShortcut = contextMenu.cellShortcut
                shortcutPopup.openFor(contextMenu.cellIndex)
            }
        }
        MenuItem {
            text: "Color"
            enabled: contextMenu.cellState !== "empty"
            onTriggered: colorPopup.openFor(contextMenu.cellIndex)
        }
        MenuItem {
            text: "Vaciar celda"
            enabled: contextMenu.cellState !== "empty"
            onTriggered: App.gridModel.clear_cell(contextMenu.cellIndex)
        }
    }

    LibraryPopup {
        id: libraryPopup
        model: App.libraryModel
        onPicked: (cellIndex, soundId, name) =>
            App.gridModel.assign_remote(cellIndex, soundId, name)
    }
    ShortcutPopup {
        id: shortcutPopup
        onAccepted: (cellIndex, combo) => App.gridModel.set_shortcut(cellIndex, combo)
    }
    ColorPopup {
        id: colorPopup
        onPicked: (cellIndex, color) => App.gridModel.set_color(cellIndex, color)
    }
}
