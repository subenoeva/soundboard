import QtQuick
import ".."

Rectangle {
    id: root
    objectName: "paramPanel"
    property string effectLabel: ""
    property var parameters: []
    signal paramEdited(string name, real value)

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
        delegate: ParamSlider {
            width: 220
            height: ListView.view.height
            paramName: modelData.name || ""
            label: modelData.label || ""
            minimum: modelData.minimum === undefined ? 0.0 : modelData.minimum
            maximum: modelData.maximum === undefined ? 1.0 : modelData.maximum
            currentValue: modelData.value === undefined ? 0.0 : modelData.value
            unit: modelData.unit || ""
            onEdited: (name, value) => root.paramEdited(name, value)
        }
    }
}
