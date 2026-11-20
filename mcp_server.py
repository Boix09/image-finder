#!/usr/bin/env python3
"""Serveur MCP local pour Image Finder (transport stdio, JSON-RPC 2.0).

Expose un outil `download_images` : une IA peut chercher et telecharger des
images existantes sur Internet a partir d'une demande en langage naturel.

Test rapide : python mcp_server.py --check
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from imagefinder.service import (  # noqa: E402
    ALLOWED_ORIENTATIONS,
    ALLOWED_SOURCES,
    MAX_LIMIT,
    run_download,
)

SERVER_NAME = "image-finder"
SERVER_VERSION = "3.0.0"
DEFAULT_PROTOCOL = "2024-11-05"

INSTRUCTIONS = (
    "Image Finder recherche des images EXISTANTES sur Internet (popularite, "
    "pertinence, resolution, qualite visuelle) et telecharge les meilleures. "
    "Utilise TOUJOURS l'outil download_images quand l'utilisateur demande de "
    "chercher, trouver, recuperer, telecharger, montrer ou obtenir des images, "
    "photos, visuels, illustrations ou captures, quelque soit la formulation "
    "et meme si la demande est longue, detaillee ou precise. Ne genere JAMAIS "
    "d'image par IA quand la demande porte sur des images reelles : utilise cet "
    "outil. Passe la demande complete dans `request` : le sujet, le nombre et "
    "le dossier sont deduits automatiquement. Cet outil ne genere pas d'images "
    "par IA. Reponds ensuite a l'utilisateur avec le dossier, les fichiers et "
    "la galerie index.html."
)

TOOLS = [
    {
        "name": "download_images",
        "title": "Download images from the internet",
        "description": (
            "Search the internet for the most popular, relevant and best-looking "
            "images matching a request, rank them (relevance, resolution, "
            "sharpness, contrast, colors), remove visual duplicates, and save the "
            "best ones into a folder with manifest.json and an index.html gallery. "
            "Use this whenever the user asks to find, download, retrieve, show or "
            "get images, photos, visuals, illustrations or captures, in any form "
            "including long, detailed or specific requests. Existing images only: "
            "this does not generate images by AI. If the user wants real images, "
            "use this tool instead of an image generator. "
            "(e.g. 'telecharge 5 belles images de voiture de sport dans le dossier "
            "voitures'). Returns JSON with the output folder, selected files and gallery path."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "request": {
                    "type": "string",
                    "description": (
                        "Demande en langage naturel, de preference la phrase "
                        "complete de l'utilisateur. Exemple : 'telecharge 5 belles "
                        "images de voiture de sport dans le dossier voitures'."
                    ),
                },
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Dossier de destination optionnel. Absolu, ou relatif au "
                        "dossier du programme. "
                        "Si absent, le dossier est deduit de la demande."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LIMIT,
                    "default": 10,
                    "description": "Nombre d'images a garder.",
                },
                "source": {
                    "type": "string",
                    "enum": list(ALLOWED_SOURCES),
                    "default": "all",
                    "description": (
                        "all = Yandex Images + Wikimedia Commons (recommande). "
                        "commons = licences explicites uniquement."
                    ),
                },
                "orientation": {
                    "type": "string",
                    "enum": list(ALLOWED_ORIENTATIONS),
                    "default": "any",
                    "description": "Orientation souhaitee.",
                },
                "min_side": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 700,
                    "description": "Petit cote minimum en pixels (0 = desactive).",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Si true, affiche seulement les meilleurs resultats sans "
                        "rien telecharger."
                    ),
                },
            },
            "required": ["request"],
        },
        "annotations": {
            "title": "Download images from the internet",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    }
]


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "oui", "on"}


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _tool_payload(result: dict, is_error: bool = False) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": result,
        "isError": is_error,
    }


def _call_tool(name: str, arguments: dict) -> dict:
    if name != "download_images":
        return _tool_payload(
            {"ok": False, "error": f"outil inconnu : {name}"}, is_error=True
        )

    if not isinstance(arguments, dict):
        return _tool_payload(
            {"ok": False, "error": "arguments invalides"}, is_error=True
        )

    request = str(arguments.get("request") or "").strip()
    if not request:
        return _tool_payload(
            {"ok": False, "error": "le champ 'request' est obligatoire"}, is_error=True
        )

    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            result = run_download(
                request,
                output=arguments.get("output_dir") or arguments.get("output"),
                limit=_as_int(arguments.get("limit"), 10),
                source=str(arguments.get("source") or "all"),
                orientation=str(arguments.get("orientation") or "any"),
                min_side=_as_int(arguments.get("min_side"), 700),
                max_mb=_as_float(arguments.get("max_mb"), 25.0),
                workers=_as_int(arguments.get("workers"), 6),
                gallery=_as_bool(arguments.get("gallery"), True),
                dry_run=_as_bool(arguments.get("dry_run"), False),
            )
        return _tool_payload(result)
    except Exception as exc:
        return _tool_payload({"ok": False, "error": str(exc)}, is_error=True)


def dispatch(method: str, params: dict) -> dict | None:
    if method == "initialize":
        requested = str((params or {}).get("protocolVersion") or DEFAULT_PROTOCOL)
        return {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = str((params or {}).get("name") or "")
        arguments = (params or {}).get("arguments") or {}
        return _call_tool(name, arguments)
    if method == "resources/list":
        return {"resources": []}
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "prompts/list":
        return {"prompts": []}
    if method == "logging/setLevel":
        return {}
    if method.startswith("notifications/"):
        return None
    raise RpcError(-32601, f"methode non prise en charge : {method}")


def _write(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error_response(message_id, code: int, text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": text},
    }


def serve() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(_error_response(None, -32700, "JSON invalide"))
            continue
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            _write(_error_response(None, -32600, "requete JSON-RPC invalide"))
            continue

        message_id = message.get("id")
        method = str(message.get("method") or "")
        params = message.get("params") or {}

        try:
            result = dispatch(method, params)
        except RpcError as exc:
            if message_id is not None:
                _write(_error_response(message_id, exc.code, exc.message))
            continue
        except Exception as exc:  # pragma: no cover - garde-fou
            traceback.print_exc(file=sys.stderr)
            if message_id is not None:
                _write(_error_response(message_id, -32603, str(exc)))
            continue

        if message_id is None:
            continue
        if result is None:
            result = {}
        _write({"jsonrpc": "2.0", "id": message_id, "result": result})

    return 0


def check() -> int:
    """Verification locale sans client MCP (utilise par les tests CMD)."""
    try:
        from imagefinder.service import TOOL_ROOT
    except Exception:  # pragma: no cover
        TOOL_ROOT = Path(__file__).resolve().parent
    print(json.dumps({
        "ok": True,
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "transport": "stdio",
        "tool_root": str(TOOL_ROOT),
        "tools": [tool["name"] for tool in TOOLS],
        "python": sys.version.split()[0],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--check", "--version"):
        raise SystemExit(check())
    raise SystemExit(serve())
