#!/usr/bin/env python3
"""Installation portable d'Image Finder pour OpenCode (serveur MCP + skill).

Utilisation :
  python install.py                # global : disponible dans tous les projets
  python install.py --project      # projet courant uniquement
  python install.py --check        # verifier sans rien modifier
  python install.py --dry-run      # afficher les actions prevues
  python install.py --skip-deps    # ne pas installer requests/Pillow

Fonctionne sous Windows, macOS et Linux.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVER = BASE_DIR / "mcp_server.py"
TEMPLATE = BASE_DIR / "skills" / "image-downloader" / "SKILL.md.template"
REQUIREMENTS = BASE_DIR / "requirements.txt"
SERVER_NAME = "image-finder"
SKILL_ID = "image-downloader"


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _ok(label: str, detail: str = "") -> None:
    suffix = f" : {detail}" if detail else ""
    print(f"[OK]      {label}{suffix}")


def _warn(label: str, detail: str = "") -> None:
    suffix = f" : {detail}" if detail else ""
    print(f"[ATTENTION] {label}{suffix}")


def _missing(label: str, detail: str = "") -> None:
    suffix = f" : {detail}" if detail else ""
    print(f"[MANQUANT] {label}{suffix}")


def _strip_jsonc(text: str) -> str:
    """Retire commentaires et virgules finales d'un fichier JSONC."""
    output: list[str] = []
    index = 0
    length = len(text)
    in_string = False
    escaped = False

    while index < length:
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < length:
            following = text[index + 1]
            if following == "/":
                index += 2
                while index < length and text[index] not in "\r\n":
                    index += 1
                continue
            if following == "*":
                index += 2
                while index + 1 < length and not (
                    text[index] == "*" and text[index + 1] == "/"
                ):
                    index += 1
                index += 2
                continue
        output.append(char)
        index += 1

    cleaned = "".join(output)
    return _remove_trailing_commas(cleaned)


def _remove_trailing_commas(text: str) -> str:
    """Supprime les virgules finales hors des chaines de caracteres."""
    output: list[str] = []
    index = 0
    length = len(text)
    in_string = False
    escaped = False

    while index < length:
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            following = index + 1
            while following < length and text[following] in " \t\r\n":
                following += 1
            if following < length and text[following] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {"$schema": "https://opencode.ai/config.json"}
    text = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(_strip_jsonc(text))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Erreur : {path} n'est pas un JSON/JSONC valide ({exc})")
    if not isinstance(data, dict):
        raise SystemExit(f"Erreur : {path} ne contient pas un objet JSON")
    return data


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if args.project:
        project_dir = (
            Path(args.project_dir).expanduser().resolve()
            if args.project_dir
            else Path.cwd().resolve()
        )
        config_candidates = [project_dir / "opencode.jsonc", project_dir / "opencode.json"]
        config_path = next(
            (path for path in config_candidates if path.exists()),
            project_dir / "opencode.json",
        )
        skills_root = (
            Path(args.skills_dir).expanduser().resolve()
            if args.skills_dir
            else project_dir / ".opencode" / "skills"
        )
        return project_dir, config_path, skills_root

    config_dir = (
        Path(args.config_dir).expanduser().resolve()
        if args.config_dir
        else Path.home() / ".config" / "opencode"
    )
    config_candidates = [config_dir / "opencode.jsonc", config_dir / "opencode.json"]
    config_path = next(
        (path for path in config_candidates if path.exists()),
        config_dir / "opencode.jsonc",
    )
    skills_root = (
        Path(args.skills_dir).expanduser().resolve()
        if args.skills_dir
        else config_dir / "skills"
    )
    return config_dir, config_path, skills_root


def _server_entry() -> dict:
    return {
        "type": "local",
        "command": [sys.executable, str(SERVER)],
        "cwd": str(BASE_DIR),
        "environment": {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    }


def _render_skill() -> str:
    if not TEMPLATE.is_file():
        raise SystemExit(f"Erreur : modele de skill introuvable : {TEMPLATE}")
    text = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "{{IMAGE_FINDER_DIR}}": BASE_DIR.as_posix(),
        "{{PYTHON}}": Path(sys.executable).as_posix(),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def _dependencies_ok() -> bool:
    result = subprocess.run(
        [sys.executable, "-c", "import requests, PIL"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _install_dependencies() -> bool:
    print("Installation des dependances (requests, Pillow)...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    )
    return result.returncode == 0


def _server_check() -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(SERVER), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "echec").strip()
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "sortie de verification illisible"
    if not payload.get("ok"):
        return False, str(payload)
    return True, f"version {payload.get('version')}"


def _config_has_server(config_path: Path) -> tuple[bool, str]:
    try:
        data = _load_config(config_path)
    except SystemExit as exc:
        return False, str(exc)
    entry = (data.get("mcp") or {}).get("servers", {}).get(SERVER_NAME)
    if not isinstance(entry, dict):
        return False, f"aucune entree '{SERVER_NAME}'"
    command = [str(item) for item in entry.get("command") or []]
    if str(SERVER) not in command:
        return False, "entree presente mais pointe vers un autre dossier"
    return True, str(config_path)


def _skill_path(skills_root: Path) -> Path:
    return skills_root / SKILL_ID / "SKILL.md"


def _skill_is_current(skill_path: Path) -> bool:
    if not skill_path.is_file():
        return False
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return BASE_DIR.as_posix() in text and "{{" not in text


def run_check(config_path: Path, skills_root: Path) -> int:
    print("Verification de l'installation Image Finder\n")
    success = True

    if sys.version_info >= (3, 10):
        _ok("Python", sys.version.split()[0])
    else:
        _missing("Python", "3.10 ou plus requis")
        success = False

    if _dependencies_ok():
        _ok("Dependances", "requests et Pillow")
    else:
        _missing("Dependances", "lancez : python -m pip install -r requirements.txt")
        success = False

    server_ok, server_detail = _server_check()
    if server_ok:
        _ok("Serveur MCP", server_detail)
    else:
        _missing("Serveur MCP", server_detail)
        success = False

    config_ok, config_detail = _config_has_server(config_path)
    if config_ok:
        _ok("Configuration OpenCode", config_detail)
    else:
        _missing("Configuration OpenCode", config_detail)
        success = False

    skill = _skill_path(skills_root)
    if _skill_is_current(skill):
        _ok("Skill image-downloader", str(skill))
    else:
        _missing("Skill image-downloader", f"installez avec : python install.py")
        success = False

    print()
    if success:
        print("Tout est pret. Redemarrez OpenCode si ce n'est pas deja fait.")
        print('Test : "telecharge 2 belles images de voiture de sport dans le dossier voitures"')
        return 0
    print("Installation incomplete : lancez python install.py")
    return 1


def run_install(args: argparse.Namespace, config_path: Path, skills_root: Path) -> int:
    if not SERVER.is_file():
        raise SystemExit(f"Erreur : serveur introuvable : {SERVER}")
    if sys.version_info < (3, 10):
        raise SystemExit("Erreur : Python 3.10 ou plus est requis")

    scope = "projet" if args.project else "global"
    print(f"Installation Image Finder ({scope})\n")

    if not _dependencies_ok():
        if args.skip_deps:
            _warn("Dependances manquantes", "relancez sans --skip-deps")
        elif args.dry_run:
            print(f"[PREVU]  installer les dependances : {REQUIREMENTS}")
        elif not _install_dependencies():
            raise SystemExit(
                "Erreur : installation des dependances impossible. "
                "Lancez : python -m pip install -r requirements.txt"
            )
        elif not _dependencies_ok():
            raise SystemExit("Erreur : requests/Pillow toujours indisponibles")
        else:
            _ok("Dependances installees")
    else:
        _ok("Dependances", "deja presentes")

    skill = _skill_path(skills_root)

    if args.dry_run:
        print(f"[PREVU]  configurer {config_path}")
        print(f"[PREVU]  installer la skill {skill}")
        print(f"[PREVU]  commande : {sys.executable} {SERVER}")
        return 0

    data = _load_config(config_path)
    data.setdefault("$schema", "https://opencode.ai/config.json")
    mcp = data.setdefault("mcp", {})
    servers = mcp.setdefault("servers", {})
    servers[SERVER_NAME] = _server_entry()

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        backup = _backup(config_path)
        print(f"[INFO]    sauvegarde : {backup}")
    config_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _ok("Configuration OpenCode", str(config_path))

    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(_render_skill(), encoding="utf-8")
    _ok("Skill image-downloader", str(skill))

    server_ok, server_detail = _server_check()
    if not server_ok:
        _missing("Serveur MCP", server_detail)
        return 1
    _ok("Serveur MCP", server_detail)

    print("\nInstallation terminee.")
    print("1. Redemarrez OpenCode.")
    print("2. Demandez simplement :")
    print('   "telecharge 2 belles images de voiture de sport dans le dossier voitures"')
    print("\nVerification a tout moment : python install.py --check")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Installe le serveur MCP Image Finder et sa skill pour OpenCode. "
            "Par defaut l'installation est globale (tous les projets)."
        )
    )
    parser.add_argument(
        "--project",
        action="store_true",
        help="installer pour le projet courant seulement (opencode.json + .opencode)",
    )
    parser.add_argument(
        "--project-dir",
        help="dossier du projet (avec --project ; defaut : dossier courant)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verifier l'installation sans rien modifier",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="afficher les actions sans rien modifier",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="ne pas installer requests/Pillow",
    )
    parser.add_argument("--config-dir", help=argparse.SUPPRESS)
    parser.add_argument("--skills-dir", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    _, config_path, skills_root = _resolve_paths(args)

    if args.check:
        return run_check(config_path, skills_root)
    return run_install(args, config_path, skills_root)


if __name__ == "__main__":
    raise SystemExit(main())
