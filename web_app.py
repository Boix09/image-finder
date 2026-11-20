#!/usr/bin/env python3
"""Interface web Image Finder.

Lancement local :
    python web_app.py

Sur un serveur (accessible de l'exterieur) :
    python web_app.py --host 0.0.0.0 --port 8420 --password "mon-secret"
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from imagefinder import __version__  # noqa: E402


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interface web pour chercher, organiser et supprimer des images."
    )
    parser.add_argument("--host", default="127.0.0.1", help="adresse d'ecoute (defaut : 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8420, help="port d'ecoute (defaut : 8420)")
    parser.add_argument("--root", help="repertoire racine de la bibliotheque")
    parser.add_argument("--config", help="fichier de configuration (defaut : web_config.json)")
    parser.add_argument(
        "--password",
        default=os.environ.get("IMAGE_FINDER_WEB_PASSWORD"),
        help="mot de passe HTTP Basic (obligatoire hors de 127.0.0.1)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="autoriser l'ecoute publique sans mot de passe (deconseille)",
    )
    parser.add_argument("--threads", type=int, default=8, help="threads du serveur (defaut : 8)")
    parser.add_argument("--open", action="store_true", help="ouvrir le navigateur au demarrage")
    parser.add_argument("--debug", action="store_true", help="serveur de developpement Flask")
    parser.add_argument("--version", action="version", version=f"Image Finder {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)

    try:
        import flask  # noqa: F401
        import waitress  # noqa: F401
    except ImportError as exc:
        print(f"Dependance manquante : {exc.name}")
        print("Lancez : python -m pip install -r requirements.txt")
        return 1

    if not (0 < args.port < 65536):
        print("Erreur : le port doit etre compris entre 1 et 65535")
        return 1

    local_hosts = {"127.0.0.1", "localhost", "::1"}
    password = (args.password or "").strip() or None
    if args.host not in local_hosts and not password and not args.insecure:
        print("Erreur : l'interface serait accessible sans mot de passe.")
        print('Relancez avec --password "un-secret" ou, en connaissance de cause, --insecure.')
        return 1
    if args.insecure and not password:
        print("[ATTENTION] Interface publique sans mot de passe (--insecure).")

    from webui.server import create_app

    try:
        app = create_app(root=args.root, config_path=args.config, password=password)
    except Exception as exc:
        print(f"Erreur au demarrage : {exc}")
        return 1

    root = app.config.get("IMAGE_FINDER_ROOT") or ""

    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{args.port}/"

    print()
    print("  Image Finder " + __version__)
    print("  " + "-" * 48)
    print(f"  Interface : {url}")
    print(f"  Bibliotheque : {root}")
    print(f"  Mot de passe : {'oui' if password else 'non (local)'}")
    if args.host in {"0.0.0.0", "::"}:
        print(f"  Depuis l'exterieur : http://<ip-du-serveur>:{args.port}/")
    print("  Arret : Ctrl+C")
    print()

    if args.open:
        threading.Timer(0.9, lambda: webbrowser.open(url)).start()

    try:
        if args.debug:
            app.run(host=args.host, port=args.port, debug=True, use_reloader=False)
        else:
            from waitress import serve

            serve(
                app,
                host=args.host,
                port=args.port,
                threads=max(2, min(32, args.threads)),
                ident="Image Finder",
            )
    except KeyboardInterrupt:
        print("\nArret de l'interface.")
    except OSError as exc:
        print(f"Erreur reseau : {exc}")
        print("Le port est peut-etre deja utilise. Essayez --port 8421.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
