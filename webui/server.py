from __future__ import annotations

"""Application Flask de l'interface web."""

import gzip
import hmac
import secrets
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

from imagefinder import __version__
from imagefinder.fileutil import slugify
from imagefinder.service import (
    ALLOWED_ORIENTATIONS,
    ALLOWED_SOURCES,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    TOOL_ROOT,
)
from imagefinder.textutil import clean_query, split_folder

from .config import WebConfig
from .jobs import JobConflict, JobManager
from .library import Library, LibraryError
from .thumbs import Thumbnailer

VERSION = __version__


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def create_app(
    *,
    root: str | Path | None = None,
    config_path: str | Path | None = None,
    password: str | None = None,
) -> Flask:
    config = WebConfig(config_path, root=root)
    library = Library(config)
    thumbnails = Thumbnailer(library)
    jobs = JobManager()
    csrf_token = secrets.token_urlsafe(28)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config["IMAGE_FINDER_PASSWORD"] = password or ""
    app.config["IMAGE_FINDER_ROOT"] = str(library.root)
    app.config["IMAGE_FINDER_CONFIG_PATH"] = str(config.path)

    def state_payload() -> dict:
        summary = library.summary()
        try:
            cache = library.cache_stats()
        except Exception:
            cache = {"count": 0, "bytes": 0, "path": ""}
        return {
            "ok": True,
            "version": VERSION,
            "root": str(library.root),
            "root_name": library.root.name or str(library.root),
            "tool_root": str(TOOL_ROOT),
            "config_path": str(config.path),
            "folders": summary["folders"],
            "totals": {
                "images": summary["images"],
                "bytes": summary["bytes"],
                "folders": len(summary["folders"]),
            },
            "cache": cache,
            "csrf": csrf_token,
            "active_job": jobs.active(),
            "password_protected": bool(app.config["IMAGE_FINDER_PASSWORD"]),
            "inbox_mode": library.config.inbox_mode,
            "inbox_folder": library.config.inbox_folder,
            "unsplash_key_configured": bool(library.config.unsplash_access_key),
        }

    def json_payload() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ApiError("requete JSON invalide")
        return data

    @app.before_request
    def guard():
        if request.path == "/healthz":
            return None

        expected = app.config["IMAGE_FINDER_PASSWORD"]
        if expected:
            auth = request.authorization
            valid = (
                auth is not None
                and auth.type == "basic"
                and hmac.compare_digest(auth.username or "", "imagefinder")
                and hmac.compare_digest(auth.password or "", expected)
            )
            if not valid:
                return Response(
                    "Authentification requise.",
                    status=401,
                    headers={"WWW-Authenticate": 'Basic realm="Image Finder"'},
                )

        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.path.startswith("/api/")
        ):
            provided = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(provided, csrf_token):
                return (
                    jsonify(
                        ok=False,
                        error="Jeton de securite invalide. Rechargez la page.",
                    ),
                    403,
                )
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")

        # Compression gzip pour les réponses JSON/HTML textuelles
        if (
            response.status_code == 200
            and response.content_type
            and (
                "application/json" in response.content_type
                or "text/html" in response.content_type
                or "text/css" in response.content_type
                or "application/javascript" in response.content_type
            )
            and not response.content_encoding
        ):
            try:
                data = response.get_data()
                if len(data) > 512:
                    compressed = gzip.compress(data, compresslevel=6)
                    response.set_data(compressed)
                    response.headers["Content-Encoding"] = "gzip"
                    response.headers["Content-Length"] = str(len(compressed))
                    response.headers.add("Vary", "Accept-Encoding")
            except Exception:
                pass

        if request.path == "/" or request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif request.path.startswith("/api/thumb"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif request.path.startswith("/api/image"):
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
        return response

    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        return jsonify(ok=False, error=str(exc)), exc.status

    @app.errorhandler(LibraryError)
    def handle_library_error(exc: LibraryError):
        return jsonify(ok=False, error=str(exc)), 400

    @app.errorhandler(JobConflict)
    def handle_job_conflict(exc: JobConflict):
        return jsonify(ok=False, error=str(exc)), 409

    @app.errorhandler(FileNotFoundError)
    def handle_missing(exc: FileNotFoundError):
        return jsonify(ok=False, error="fichier introuvable"), 404

    @app.errorhandler(KeyError)
    def handle_key_error(exc: KeyError):
        return jsonify(ok=False, error="tache introuvable"), 404

    @app.errorhandler(404)
    def handle_not_found(_exc):
        if request.path.startswith("/api/"):
            return jsonify(ok=False, error="route inconnue"), 404
        return render_template("index.html", version=VERSION), 404

    @app.errorhandler(413)
    def handle_too_large(_exc):
        return jsonify(ok=False, error="requete trop volumineuse"), 413

    @app.errorhandler(500)
    def handle_server_error(_exc):
        return jsonify(ok=False, error="erreur interne du serveur"), 500

    @app.get("/")
    def index():
        return render_template("index.html", version=VERSION)

    @app.get("/healthz")
    def health():
        return jsonify(ok=True, app="image-finder", version=VERSION)

    @app.get("/api/state")
    def api_state():
        return jsonify(state_payload())

    @app.get("/api/images")
    def api_images():
        folder = (request.args.get("folder") or "").strip()
        page = _as_int(request.args.get("page"), 1)
        page_size = _as_int(request.args.get("page_size"), 50)
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 200:
            page_size = 50

        total = library.images_count(folder)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages

        images = library.images(folder, page=page, page_size=page_size)
        return jsonify(
            ok=True,
            folder=folder,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
            count=len(images),
            bytes=sum(item["size"] for item in images),
            images=images,
        )

    @app.get("/api/cache/stats")
    def api_cache_stats():
        return jsonify(ok=True, **library.cache_stats())

    @app.post("/api/cache/clear")
    def api_cache_clear():
        if jobs.active():
            raise JobConflict("attendez la fin de la recherche avant de vider le cache")
        try:
            result = library.cache_clear()
        except Exception as exc:
            raise ApiError(f"impossible de vider le cache : {exc}") from exc
        library._invalidate()
        return jsonify(ok=True, **result)

    @app.get("/api/thumb")
    def api_thumb():
        relative = request.args.get("path") or ""
        width = _as_int(request.args.get("w"), 640)
        path, mimetype = thumbnails.get(relative, width)
        return send_file(
            path,
            mimetype=mimetype,
            conditional=True,
            max_age=31536000,
        )

    def _image_response(relative: str, *, attachment: bool):
        path = library.image_path(relative)
        response = send_file(
            path,
            as_attachment=attachment,
            download_name=path.name if attachment else None,
            conditional=True,
            max_age=3600,
        )
        if path.suffix.lower() == ".svg":
            response.headers["Content-Security-Policy"] = (
                "sandbox; default-src 'none'; style-src 'unsafe-inline'"
            )
        return response

    @app.get("/api/image")
    def api_image():
        return _image_response(request.args.get("path") or "", attachment=False)

    @app.get("/api/download")
    def api_download():
        return _image_response(request.args.get("path") or "", attachment=True)

    @app.post("/api/download-selection")
    def api_download_selection():
        if jobs.active():
            raise JobConflict(
                "attendez la fin de la recherche avant de telecharger une selection"
            )
        payload = json_payload()
        paths = payload.get("paths") or []
        destination = payload.get("destination") or "browser"
        folder_name = payload.get("folder_name") or None

        if not isinstance(paths, list) or not paths:
            raise ApiError("aucune image selectionnee")

        if destination == "folder":
            try:
                result = library.copy_selection_to_folder(paths, folder_name)
            except LibraryError as exc:
                raise ApiError(str(exc)) from exc
            return jsonify(
                ok=True,
                destination="folder",
                subfolder=result["subfolder"],
                path=result["path"],
                copied=result["copied"],
                files=result["files"],
                manifest=result["manifest"],
            )
        elif destination == "browser":
            return jsonify(
                ok=True,
                destination="browser",
                count=len(paths),
                urls=[
                    f"/api/download?path={__import__('urllib.parse').quote(p)}"
                    for p in paths
                ],
            )
        else:
            raise ApiError(f"destination invalide : {destination}")

    @app.post("/api/move-selection")
    def api_move_selection():
        if jobs.active():
            raise JobConflict(
                "attendez la fin de la recherche avant de deplacer une selection"
            )
        if not library.config.inbox_mode:
            raise ApiError("le mode inbox n'est pas active")
        payload = json_payload()
        paths = payload.get("paths") or []
        folder_name = payload.get("folder_name") or ""

        if not isinstance(paths, list) or not paths:
            raise ApiError("aucune image selectionnee")
        if not folder_name.strip():
            raise ApiError("indiquez un nom de dossier de destination")

        try:
            result = library.move_selection_to_folder(paths, folder_name)
        except LibraryError as exc:
            raise ApiError(str(exc)) from exc
        return jsonify(
            ok=True,
            destination="folder",
            folder=result["folder"],
            path=result["path"],
            moved=result["moved"],
            files=result["files"],
            manifest=result["manifest"],
        )

    @app.post("/api/delete-selection")
    def api_delete_selection():
        if jobs.active():
            raise JobConflict(
                "attendez la fin de la recherche avant de supprimer une selection"
            )
        payload = json_payload()
        paths = payload.get("paths") or []

        if not isinstance(paths, list) or not paths:
            raise ApiError("aucune image selectionnee")

        try:
            result = library.delete_selection(paths)
        except LibraryError as exc:
            raise ApiError(str(exc)) from exc
        return jsonify(
            ok=True,
            destination="delete",
            deleted=result["deleted"],
            freed=result["freed"],
            errors=result["errors"],
        )

    @app.post("/api/config/inbox")
    def api_config_inbox():
        payload = json_payload()
        inbox_mode = payload.get("inbox_mode")
        if not isinstance(inbox_mode, bool):
            raise ApiError("parametre inbox_mode requis (true/false)")
        library.config.set_inbox_mode(inbox_mode)
        return jsonify(
            ok=True,
            inbox_mode=library.config.inbox_mode,
            inbox_folder=library.config.inbox_folder,
        )

    @app.get("/api/config/unsplash")
    def api_config_unsplash_get():
        return jsonify(
            ok=True,
            configured=bool(library.config.unsplash_access_key),
        )

    @app.post("/api/config/unsplash")
    def api_config_unsplash():
        payload = json_payload()
        key = payload.get("unsplash_access_key") or ""
        library.config.set_unsplash_access_key(key)
        return jsonify(
            ok=True,
            configured=bool(library.config.unsplash_access_key),
        )

    @app.post("/api/root")
    def api_root():
        if jobs.active():
            raise JobConflict(
                "attendez la fin de la recherche avant de changer de repertoire"
            )
        payload = json_payload()
        try:
            library.config.set_root(payload.get("path") or "")
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        except OSError as exc:
            raise ApiError(f"impossible d'enregistrer la configuration : {exc}") from exc
        library._invalidate()
        return jsonify(state_payload())

    @app.post("/api/folders")
    def api_create_folder():
        payload = json_payload()
        name = library.create_folder(payload.get("name") or "")
        return jsonify(ok=True, folder=name)

    @app.delete("/api/folders")
    def api_delete_folder():
        if jobs.active():
            raise JobConflict(
                "attendez la fin de la recherche avant de supprimer un dossier"
            )
        payload = json_payload()
        target = payload.get("path") or payload.get("name") or ""
        if payload.get("confirm") is not True:
            raise ApiError("confirmation manquante")
        result = library.delete_folder(target)
        return jsonify(ok=True, **result)

    @app.delete("/api/images")
    def api_delete_image():
        payload = json_payload()
        if payload.get("confirm") is not True:
            raise ApiError("confirmation manquante")
        result = library.delete_image(payload.get("path") or "")
        return jsonify(ok=True, **result)

    @app.post("/api/search")
    def api_search():
        payload = json_payload()
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ApiError("decrirez ce que vous cherchez")
        if len(query) > 500:
            raise ApiError("la recherche est trop longue (500 caracteres max)")

        if jobs.active():
            raise JobConflict(
                "une recherche est deja en cours, attendez la fin avant d'en lancer une autre"
            )

        raw_source = payload.get("source") or "all"
        if isinstance(raw_source, list):
            sources = [str(s).strip().lower() for s in raw_source if str(s).strip()]
        else:
            sources = [str(raw_source).strip().lower()]
        if not sources:
            sources = ["all"]
        for s in sources:
            if s not in ALLOWED_SOURCES:
                raise ApiError(f"source inconnue : {s}")
        source = sources
        orientation = str(payload.get("orientation") or "any").strip().lower()
        if orientation not in ALLOWED_ORIENTATIONS:
            raise ApiError("orientation inconnue")

        limit = max(1, min(MAX_LIMIT, _as_int(payload.get("limit"), DEFAULT_LIMIT)))
        min_side = max(0, min(10_000, _as_int(payload.get("min_side"), 700)))

        text, detected = split_folder(query)
        try:
            cleaned = clean_query(text)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

        requested_folder = str(payload.get("folder") or "").strip()
        folder = requested_folder or detected or slugify(cleaned)
        folder = library.validate_folder_name(folder)

        inbox_mode = bool(library.config.inbox_mode)
        inbox_folder = library.config.inbox_folder

        if inbox_mode:
            output_dir = str(library.root / inbox_folder / slugify(cleaned))
        else:
            library.ensure_folder(folder)
            output_dir = str(library.root / folder)

        job = jobs.submit(
            request=query,
            folder=folder,
            output_dir=output_dir,
            limit=limit,
            source=source,
            orientation=orientation,
            min_side=min_side,
            inbox_mode=inbox_mode,
            inbox_folder=inbox_folder,
        )
        return jsonify(ok=True, job=job), 202

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify(ok=True, active=jobs.active())

    @app.get("/api/jobs/<job_id>")
    def api_job(job_id: str):
        return jsonify(ok=True, job=jobs.get(job_id))

    @app.post("/api/jobs/<job_id>/cancel")
    def api_job_cancel(job_id: str):
        try:
            jobs.cancel(job_id)
        except KeyError:
            raise ApiError("tache introuvable", 404)
        return jsonify(ok=True, cancelled=True)

    return app
