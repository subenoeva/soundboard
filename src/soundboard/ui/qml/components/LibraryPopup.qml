import QtQuick
import QtQuick.Controls.Basic
import ".."

Popup {
    id: root
    property var model: null
    property int cellIndex: -1

    property string _selSoundId: ""
    property string _selName: ""

    signal picked(int cellIndex, string soundId, string name)

    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: 360
    height: 420
    padding: Theme.pad * 2

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusPad
    }

    function openFor(index) {
        cellIndex = index
        _selSoundId = ""
        _selName = ""
        if (root.model !== null)
            root.model.reload()
        open()
    }

    contentItem: Column {
        spacing: Theme.pad

        TextField {
            id: filterField
            width: parent.width
            placeholderText: "Filtrar…"
            onTextChanged: {
                if (root.model !== null)
                    root.model.filterText = text
            }
        }

        Item {
            width: parent.width
            height: 260

            ListView {
                id: listView
                anchors.fill: parent
                clip: true
                model: root.model
                visible: count > 0

                delegate: Rectangle {
                    id: delegateRoot
                    width: listView.width
                    height: 36
                    property bool hovered: false
                    color: hovered ? Theme.accent : "transparent"

                    Text {
                        anchors { left: parent.left; right: parent.right;
                                  verticalCenter: parent.verticalCenter; margins: Theme.pad }
                        text: model.name + " — " + model.owner
                        color: Theme.textPrimary
                        elide: Text.ElideRight
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        onEntered: delegateRoot.hovered = true
                        onExited: delegateRoot.hovered = false
                        onClicked: {
                            root._selSoundId = model.soundId
                            root._selName = model.name
                        }
                        onDoubleClicked: {
                            root.picked(root.cellIndex, model.soundId, model.name)
                            root.close()
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                width: parent.width - Theme.pad * 2
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                visible: root.model !== null && listView.count === 0
                         && !root.model.loading && root.model.errorText === ""
                text: "No hay sonidos compartidos todavía"
                color: Theme.textSecondary
            }

            BusyIndicator {
                anchors.centerIn: parent
                running: root.model !== null && root.model.loading
                visible: running
            }
        }

        Text {
            width: parent.width
            visible: root.model !== null && root.model.errorText !== ""
            text: root.model !== null ? root.model.errorText : ""
            color: Theme.danger
            wrapMode: Text.Wrap
        }

        Row {
            width: parent.width
            spacing: Theme.pad

            Button {
                text: "Reintentar"
                visible: root.model !== null && root.model.errorText !== ""
                onClicked: root.model.reload()
            }
        }

        Row {
            width: parent.width
            spacing: Theme.pad
            layoutDirection: Qt.RightToLeft

            Button {
                text: "Cancelar"
                onClicked: root.close()
            }
            Button {
                text: "Asignar"
                enabled: root._selSoundId !== ""
                onClicked: {
                    root.picked(root.cellIndex, root._selSoundId, root._selName)
                    root.close()
                }
            }
        }
    }
}
