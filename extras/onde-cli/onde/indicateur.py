"""Icône persistante : rouvrir Onde après fermeture de sa fenêtre Chrome."""
import fcntl
import os
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def demarrer() -> None:
    port = int(os.getenv("PORT", "5070"))
    dossier = Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "onde"
    dossier.mkdir(parents=True, exist_ok=True)
    with (dossier / f"indicateur-{port}.lock").open("w") as verrou:
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return

        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3, Gtk

        indicateur = AppIndicator3.Indicator.new(
            f"onde-{port}", str(RACINE / "static/icone.svg"),
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        indicateur.set_title("Onde")
        indicateur.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        menu = Gtk.Menu()
        ouvrir = Gtk.MenuItem(label="Ouvrir Onde")

        def ouvrir_fenetre(_item):
            subprocess.Popen(
                [str(RACINE / "onde-app"), "--fenetre"], cwd=RACINE,
                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

        ouvrir.connect("activate", ouvrir_fenetre)
        menu.append(ouvrir)
        menu.append(Gtk.SeparatorMenuItem())
        etat = Gtk.MenuItem(label="Onde en arrière-plan")
        etat.set_sensitive(False)
        menu.append(etat)
        menu.show_all()
        indicateur.set_menu(menu)
        indicateur.set_secondary_activate_target(ouvrir)
        Gtk.main()


if __name__ == "__main__":
    demarrer()
