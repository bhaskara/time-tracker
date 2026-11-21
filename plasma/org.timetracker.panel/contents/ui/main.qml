// Time Tracker panel widget: polls the local server and shows the current
// session as one line of text, coloured by state. Click opens the web page.
import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.plasmoid 2.0
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents3

import "../code/format.js" as Format

Item {
    id: root

    // Address of the tracker server (tt-server binds to loopback only).
    readonly property string serverUrl: "http://127.0.0.1:8765"
    readonly property int pollMs: 5000
    // Longest panel text before the label is elided, in characters.
    readonly property int maxWidthChars: 44

    // The web page's hues, lightened so small text stands out on a dark panel.
    readonly property var colors: ({
        "work": "#93c4ee",
        "break": "#a3d6ae",
        "distraction": "#e6a590",
        "overrun": "#efc67f",
        "idle": "#efc67f",
        "signedoff": "#aab1bc",
        "offline": "#aab1bc"
    })
    // Text size relative to the panel's default font.
    readonly property real fontScale: 1.15

    property var status: null
    property double fetchedAt: 0
    property string kind: "offline"
    property string text: "tracker offline"
    property string tooltip: "Cannot reach " + serverUrl

    function render() {
        if (status === null) {
            kind = "offline";
            text = "tracker offline";
            tooltip = "Cannot reach " + serverUrl;
            return;
        }
        var view = Format.describe(status, (Date.now() - fetchedAt) / 1000);
        kind = view.kind;
        text = view.text;
        tooltip = view.tooltip;
    }

    function refresh() {
        var request = new XMLHttpRequest();
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE) return;
            if (request.status === 200) {
                status = JSON.parse(request.responseText);
                fetchedAt = Date.now();
            } else {
                status = null;
            }
            render();
        };
        request.open("GET", serverUrl + "/api/status");
        request.send();
    }

    Plasmoid.preferredRepresentation: Plasmoid.fullRepresentation
    Plasmoid.toolTipMainText: "Time Tracker"
    Plasmoid.toolTipSubText: root.tooltip

    Plasmoid.fullRepresentation: Item {
        Layout.minimumWidth: label.width + PlasmaCore.Units.smallSpacing * 4
        Layout.preferredWidth: Layout.minimumWidth
        Layout.maximumWidth: Layout.minimumWidth
        Layout.minimumHeight: label.implicitHeight

        PlasmaComponents3.Label {
            id: label
            anchors.centerIn: parent
            width: Math.min(implicitWidth, metrics.averageCharacterWidth * root.maxWidthChars)
            text: root.text
            color: root.colors[root.kind]
            font.pointSize: PlasmaCore.Theme.defaultFont.pointSize * root.fontScale
            elide: Text.ElideRight
            maximumLineCount: 1
        }

        FontMetrics {
            id: metrics
            font: label.font
        }

        MouseArea {
            anchors.fill: parent
            onClicked: Qt.openUrlExternally("http://localhost:8765")
        }
    }

    Timer {
        interval: root.pollMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }
}
