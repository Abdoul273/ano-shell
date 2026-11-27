import Quickshell
import Quickshell.Wayland
import AnoShell.Config

// qmllint disable uncreatable-type
PanelWindow {
    // qmllint enable uncreatable-type
    required property string name

    WlrLayershell.namespace: `ano-shell-${name}`
    color: "transparent"

    contentItem.Config.screen: screen.name
    contentItem.Tokens.screen: screen.name
}
