import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."
import "components"

Item {
    id: root
    property int selectedIndex: -1
    property string selectedLabel: ""
    property var selectedParameters: []

    function selectEffect(index, label) {
        selectedIndex = index
        selectedLabel = label
        refreshParameters()
    }

    function refreshParameters() {
        selectedParameters = App.effectsModel !== null && selectedIndex >= 0
                ? App.effectsModel.param_specs(selectedIndex) : []
    }

    function moveEffect(source, destination) {
        if (App.effectsModel === null || source === destination)
            return
        App.effectsModel.move(source, destination)
        if (selectedIndex === source)
            selectedIndex = destination
        else if (source < selectedIndex && destination >= selectedIndex)
            selectedIndex -= 1
        else if (source > selectedIndex && destination <= selectedIndex)
            selectedIndex += 1
        refreshParameters()
    }

    Column {
        id: pageColumn
        anchors { fill: parent; margins: Theme.pad * 2 }
        spacing: Theme.pad

        Item {
            id: rackHeader
            width: parent.width
            height: Math.max(rackTitle.implicitHeight, rackMetrics.implicitHeight)
            Text {
                id: rackTitle
                anchors { left: parent.left; verticalCenter: parent.verticalCenter }
                text: "Cadena del micrófono"
                color: Theme.textPrimary
                font.bold: true
                font.pixelSize: 15
            }
            Text {
                id: rackMetrics
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                text: App.bridge !== null
                      ? "Latencia " + App.bridge.chainLatencyMs.toFixed(1) + " ms"
                        + "  ·  Coste p99 " + App.bridge.chainCostMs.toFixed(2) + " ms"
                      : ""
                color: Theme.textSecondary
                font.pixelSize: 11
            }
        }

        Item {
            id: rackRow
            width: parent.width
            height: Math.max(120, pageColumn.height - rackHeader.height
                             - parameterPanel.height - palette.height
                             - pageColumn.spacing * 3)

            Rectangle {
                id: micCard
                objectName: "micCard"
                anchors { left: parent.left; verticalCenter: parent.verticalCenter }
                width: 116
                height: Math.min(parent.height, 142)
                radius: Theme.radiusPad
                color: Theme.surface
                border.width: 1
                border.color: Theme.accent

                ColumnLayout {
                    anchors { fill: parent; margins: Theme.pad }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "MIC"
                        color: Theme.textPrimary
                        font.bold: true
                        font.pixelSize: 13
                    }
                    Item { Layout.fillHeight: true }
                    VUMeter {
                        Layout.fillWidth: true
                        height: 10
                        level: App.bridge !== null ? App.bridge.inputPeak : 0
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "Entrada"
                        color: Theme.textSecondary
                        font.pixelSize: 10
                    }
                }
            }

            ListView {
                id: rack
                objectName: "effectsRack"
                anchors { left: micCard.right; right: outCard.left;
                          top: parent.top; bottom: parent.bottom;
                          leftMargin: Theme.pad; rightMargin: Theme.pad }
                orientation: ListView.Horizontal
                spacing: Theme.pad
                clip: true
                model: App.effectsModel

                delegate: DropArea {
                    width: 166
                    height: rack.height
                    keys: ["effect-block"]
                    onEntered: (drag) => {
                        if (drag.source !== null)
                            root.moveEffect(drag.source.rackIndex, index)
                    }

                    Item {
                        width: parent.width
                        height: Math.min(parent.height, 142)
                        y: Math.max(0, (parent.height - height) / 2)

                        EffectBlock {
                            width: parent.width
                            height: parent.height
                            rackIndex: index
                            effectLabel: model.label
                            summary: model.summary
                            effectEnabled: model.enabled
                            latencyMs: model.latencyMs
                            errorText: model.errorText
                            loading: model.loading
                            selected: root.selectedIndex === index
                            onSelectedRequested: root.selectEffect(index, model.label)
                            onToggleRequested: (on) => App.effectsModel.set_enabled(index, on)
                            onRemoveRequested: {
                                App.effectsModel.remove(index)
                                root.selectedIndex = -1
                                root.selectedLabel = ""
                                root.selectedParameters = []
                            }
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    visible: rack.count === 0
                    text: "Añade un efecto desde la paleta"
                    color: Theme.textSecondary
                    font.pixelSize: 12
                }
            }

            Rectangle {
                id: outCard
                objectName: "outCard"
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: 116
                height: Math.min(parent.height, 142)
                radius: Theme.radiusPad
                color: Theme.surface
                border.width: 1
                border.color: Theme.accent

                ColumnLayout {
                    anchors { fill: parent; margins: Theme.pad }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "OUT"
                        color: Theme.textPrimary
                        font.bold: true
                        font.pixelSize: 13
                    }
                    Item { Layout.fillHeight: true }
                    VUMeter {
                        Layout.fillWidth: true
                        height: 10
                        level: App.bridge !== null ? App.bridge.chainPeak : 0
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "Salida"
                        color: Theme.textSecondary
                        font.pixelSize: 10
                    }
                }
            }
        }

        ParamPanel {
            id: parameterPanel
            width: parent.width
            height: implicitHeight
            effectLabel: root.selectedLabel
            parameters: root.selectedParameters
            onParamEdited: (name, value) => {
                if (App.effectsModel !== null && root.selectedIndex >= 0) {
                    App.effectsModel.set_param(root.selectedIndex, name, value)
                    root.refreshParameters()
                }
            }
        }

        EffectPalette {
            id: palette
            width: parent.width
            height: implicitHeight
            catalog: App.effectsModel !== null ? App.effectsModel.catalog() : []
            onEffectPicked: (kind) => {
                if (App.effectsModel === null)
                    return
                App.effectsModel.add(kind)
                Qt.callLater(function() {
                    if (rack.count > 0) {
                        let row = rack.count - 1
                        let item = rack.itemAtIndex(row)
                        root.selectEffect(row, item === null ? "" : item.children[0].effectLabel)
                    }
                })
            }
        }
    }
}
