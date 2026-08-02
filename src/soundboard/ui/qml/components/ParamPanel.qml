import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Rectangle {
    id: root
    objectName: "paramPanel"
    property string effectLabel: ""
    property var parameters: []
    signal paramEdited(string name, var value)

    implicitHeight: parameters.length > 0 ? 88 : 64
    radius: Theme.radiusPad
    color: Theme.surface
    border.width: 1
    border.color: Theme.padBg

    Text {
        id: panelTitle
        anchors { top: parent.top; left: parent.left; right: parent.right;
                  topMargin: Theme.pad; leftMargin: Theme.pad; rightMargin: Theme.pad }
        text: root.effectLabel === "" ? "Selecciona un efecto" : root.effectLabel
        color: Theme.textPrimary
        font.bold: true
        font.pixelSize: 12
    }

    Text {
        anchors { top: panelTitle.bottom; left: parent.left; right: parent.right;
                  topMargin: 4; leftMargin: Theme.pad; rightMargin: Theme.pad }
        visible: root.parameters.length === 0
        text: root.effectLabel === ""
                ? "Elige un bloque para ajustar sus parámetros"
                : "Este efecto no tiene parámetros configurables"
        color: Theme.textSecondary
        font.pixelSize: 11
    }

    ListView {
        id: parameterList
        objectName: "parameterList"
        anchors { top: panelTitle.bottom; left: parent.left; right: parent.right;
                  bottom: parent.bottom; topMargin: 4; leftMargin: Theme.pad;
                  rightMargin: Theme.pad; bottomMargin: Theme.pad }
        visible: root.parameters.length > 0
        orientation: ListView.Horizontal
        spacing: Theme.pad * 2
        clip: true
        model: root.parameters
        delegate: Loader {
            id: paramLoader
            width: 220
            height: ListView.view.height
            property var spec: modelData
            sourceComponent: spec.type === "bool" ? boolControl
                             : spec.type === "choice" ? choiceControl : floatControl
            onLoaded: item.spec = spec
        }
    }

    Component {
        id: floatControl
        ParamSlider {
            property var spec: ({})
            paramName: spec.name || ""
            label: spec.label || ""
            minimum: spec.minimum === undefined ? 0.0 : spec.minimum
            maximum: spec.maximum === undefined ? 1.0 : spec.maximum
            currentValue: spec.value === undefined ? 0.0 : spec.value
            unit: spec.unit || ""
            onEdited: (name, value) => root.paramEdited(name, value)
        }
    }

    Component {
        id: boolControl
        Item {
            objectName: "boolParamControl"
            property var spec: ({})
            RowLayout {
                anchors.fill: parent
                Text {
                    Layout.fillWidth: true
                    text: spec.label || ""
                    color: Theme.textSecondary
                    font.pixelSize: 11
                }
                Switch {
                    checked: Boolean(spec.value)
                    onClicked: root.paramEdited(spec.name || "", checked)
                }
            }
        }
    }

    Component {
        id: choiceControl
        Item {
            objectName: "choiceParamControl"
            property var spec: ({})
            RowLayout {
                anchors.fill: parent
                Text {
                    Layout.fillWidth: true
                    text: spec.label || ""
                    color: Theme.textSecondary
                    font.pixelSize: 11
                }
                ComboBox {
                    Layout.preferredWidth: 130
                    model: spec.choices || []
                    currentIndex: Math.max(0, model.indexOf(spec.value))
                    onActivated: root.paramEdited(
                        spec.name || "", currentText
                    )
                }
            }
        }
    }
}
