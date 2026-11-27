import Quickshell
import Quickshell.Hyprland

// Enregistre chaque raccourci sous "ano-shell:<name>" et sous l'alias
// "caelestia:<name>" pour compatibilité directe avec les configs Hyprland/HyprLua existantes.
Scope {
    id: root

    required property string name
    property string description: ""

    signal pressed()
    signal released()

    // qmllint disable unresolved-type
    GlobalShortcut {
        // qmllint enable unresolved-type
        appid: "ano-shell"
        name: root.name
        description: root.description
        onPressed: root.pressed()
        onReleased: root.released()
    }

    // qmllint disable unresolved-type
    GlobalShortcut {
        // qmllint enable unresolved-type
        appid: "caelestia"
        name: root.name
        description: root.description
        onPressed: root.pressed()
        onReleased: root.released()
    }
}
