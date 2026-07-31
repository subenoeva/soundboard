import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Never references App: that is what lets the smoke test instantiate it standalone
// with no context property in scope.
Rectangle {
    id: root
    objectName: "updateBanner"

    // updateState, not state: Item.state already exists, the same collision cellState
    // and cellColor avoid in GridModel.
    property string updateState: "idle"   // idle | checking | available | downloading | ready | failed
    property string version: ""
    property real progress: 0
    signal downloadClicked()
    signal restartClicked()

    readonly property bool showing: updateState === "available"
                                 || updateState === "downloading"
                                 || updateState === "ready"

    visible: showing
    height: showing ? 40 : 0
    color: Theme.surface

    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 1
        color: Theme.accent
    }

    // Sits behind the row rather than replacing it, so the version stays readable while
    // the ~100MB download runs.
    Rectangle {
        objectName: "progressFill"
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: root.updateState === "downloading"
                 ? parent.width * Math.max(0, Math.min(1, root.progress))
                 : 0
        // No Behavior on width: progress lands once per 64KB chunk, so the binding is
        // already smooth and an easing curve would only trail the real figure.
        color: Theme.accent
        opacity: 0.25
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.pad * 2
        anchors.rightMargin: Theme.pad * 2
        spacing: Theme.pad

        Text {
            objectName: "updateLabel"
            Layout.fillWidth: true
            elide: Text.ElideRight
            color: Theme.textPrimary
            font.pixelSize: 12
            text: root.updateState === "downloading"
                    ? "Descargando la versión " + root.version + "…"
                : root.updateState === "ready"
                    ? "La versión " + root.version + " está lista"
                : "Hay una versión nueva disponible: " + root.version
        }

        Button {
            objectName: "updateAction"
            text: root.updateState === "ready" ? "Reiniciar ahora" : "Actualizar"
            enabled: root.updateState !== "downloading"
            onClicked: root.updateState === "ready" ? root.restartClicked()
                                                    : root.downloadClicked()
        }
    }
}
