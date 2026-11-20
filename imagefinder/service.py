from __future__ import annotations

"""API programmatique : recherche + telechargement, resultat structure.

Utilisee par le serveur MCP (pour l'IA) et par l'option --json du CLI.
Aucune dependance a argparse ou a la console.
"""

import contextlib
import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .downloader import download_candidates, finalize_selection, pick_best
from .fileutil import safe_dirname, slugify
from .quality import PIL_AVAILABLE
from .report import write_gallery, write_manifest
from .sources import search_images
from .textutil import clean_query, matches_orientation, split_folder

DEFAULT_LIMIT = 10
MAX_LIMIT = 60
DEFAULT_SOURCE = "all"
ALLOWED_SOURCES = ("all", "yandex", "commons", "ddg", "openverse")
ALLOWED_ORIENTATIONS = ("any", "landscape", "portrait", "square")

# Tout reste dans le dossier du programme (voir TOOL_ROOT).
TOOL_ROOT = Path(__file__).resolve().parent.parent

ProgressCallback = Callable[[dict], None]


def _emit(callback: ProgressCallback | None, **event) -> None:
    """Signale un evenement de progression sans jamais interrompre le travail."""
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        pass


def default_base_dir() -> Path:
    """Dossier de base des sorties (surchargeable par IMAGE_FINDER_HOME)."""
    configured = os.environ.get("IMAGE_FINDER_HOME")
    if configured:
        return Path(configured).expanduser()
    return TOOL_ROOT


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def resolve_destination(
    request: str,
    output: str | Path | None = None,
) -> tuple[str, Path, str | None]:
    """Nettoie la demande et determine le dossier de destination."""
    text, folder = split_folder(request)
    query = clean_query(text)
    base = default_base_dir()

    if output:
        destination = Path(output).expanduser()
        if not destination.is_absolute():
            destination = base / destination
    elif folder:
        candidate = Path(folder).expanduser()
        destination = candidate if candidate.is_absolute() else base / safe_dirname(folder)
    else:
        destination = base / "images" / slugify(query)

    return query, destination, folder


def _candidate_payload(candidate) -> dict:
    return {
        "title": candidate.title,
        "provider": candidate.provider,
        "width": candidate.width,
        "height": candidate.height,
        "image_url": candidate.image_url,
        "page_url": candidate.source_page,
        "license": candidate.license,
        "score": round(candidate.meta_score, 4),
    }


def _image_payload(item) -> dict:
    width = item.quality.width if item.quality else item.width
    height = item.quality.height if item.quality else item.height
    candidate = item.candidate
    return {
        "file": item.path.name if item.path else "",
        "title": candidate.title,
        "provider": candidate.provider,
        "page_url": candidate.source_page,
        "image_url": item.used_url,
        "width": width,
        "height": height,
        "bytes": item.bytes,
        "score": round(item.final_score, 4),
        "license": candidate.license,
        "license_url": candidate.license_url,
        "creator": candidate.creator,
    }


def run_download(
    request: str,
    *,
    output: str | Path | None = None,
    limit: int = DEFAULT_LIMIT,
    source: str = DEFAULT_SOURCE,
    orientation: str = "any",
    min_side: int = 700,
    max_mb: float = 25.0,
    workers: int = 6,
    gallery: bool = True,
    dry_run: bool = False,
    progress: ProgressCallback | None = None,
) -> dict:
    """Cherche des images et telecharge les meilleures.

    Renvoie un dictionnaire serialisable en JSON. Leve ValueError pour une
    demande invalide et RuntimeError quand aucune image exploitable n'est trouvee.
    """
    request = (request or "").strip()
    if not request:
        raise ValueError("demande vide : precisez un sujet (ex. : voiture de sport)")

    if source not in ALLOWED_SOURCES:
        raise ValueError(
            f"source inconnue : {source} (valeurs acceptees : {', '.join(ALLOWED_SOURCES)})"
        )
    if orientation not in ALLOWED_ORIENTATIONS:
        raise ValueError(
            "orientation inconnue : "
            f"{orientation} (valeurs acceptees : {', '.join(ALLOWED_ORIENTATIONS)})"
        )

    limit = _clamp(int(limit), 1, MAX_LIMIT)
    workers = _clamp(int(workers), 1, 32)
    min_side = max(0, int(min_side))
    if max_mb <= 0:
        max_mb = 25.0

    query, destination, folder = resolve_destination(request, output)

    if destination.exists() and not destination.is_dir():
        raise RuntimeError(f"{destination} existe mais n'est pas un dossier")

    log_buffer = io.StringIO()
    _emit(
        progress,
        stage="search",
        message="Recherche des meilleures images...",
        progress=4,
    )
    with contextlib.redirect_stdout(log_buffer):
        candidates = search_images(query, source, limit)
        _emit(
            progress,
            stage="search",
            message=f"{len(candidates)} image(s) trouvee(s)",
            progress=16,
        )

        filtered = []
        for candidate in candidates:
            if candidate.width and candidate.height:
                if min_side and min(candidate.width, candidate.height) < min_side:
                    continue
                if not matches_orientation(
                    candidate.width, candidate.height, orientation
                ):
                    continue
            filtered.append(candidate)

        if not filtered:
            raise RuntimeError(
                "aucune image trouvee. Essayez une autre formulation ou une autre source."
            )

        selected: list = []
        downloads: list = []
        if not dry_run:
            selected, downloads = _download(
                query, request, destination, filtered, limit, source,
                orientation, min_side, max_mb, workers, gallery, progress,
            )

    log = [line for line in log_buffer.getvalue().splitlines() if line.strip()]

    if dry_run:
        _emit(
            progress,
            stage="done",
            message="Apercu termine",
            progress=100,
        )
        return {
            "ok": True,
            "dry_run": True,
            "query": query,
            "request": request,
            "source": source,
            "orientation": orientation,
            "count": min(len(filtered), limit),
            "candidates": [_candidate_payload(item) for item in filtered[:limit]],
            "folder_detected": folder,
            "log": log,
        }

    manifest = destination / "manifest.json"
    gallery_file = destination / "index.html" if gallery else None

    return {
        "ok": True,
        "query": query,
        "request": request,
        "source": source,
        "orientation": orientation,
        "output_dir": str(destination.resolve()),
        "count": len(selected),
        "requested": limit,
        "downloaded": len(downloads),
        "rejected": sum(1 for item in downloads if item.error),
        "files": [item.path.name for item in selected if item.path],
        "images": [_image_payload(item) for item in selected],
        "manifest": str(manifest.resolve()),
        "gallery": str(gallery_file.resolve()) if gallery_file else "",
        "folder_detected": folder,
        "log": log,
    }


def _download(
    query: str,
    request: str,
    destination: Path,
    filtered: list,
    limit: int,
    source: str,
    orientation: str,
    min_side: int,
    max_mb: float,
    workers: int,
    gallery: bool,
    progress: ProgressCallback | None = None,
) -> tuple[list, list]:
    destination.mkdir(parents=True, exist_ok=True)

    max_bytes = int(max_mb * 1024 * 1024)
    pool_size = min(len(filtered), min(60, max(limit * 2, limit + 6)))
    pool = filtered[:pool_size]
    print(f"Telechargement de {len(pool)} candidate(s) pour en garder {limit}...")
    _emit(
        progress,
        stage="download",
        message=f"Telechargement de {len(pool)} image(s)...",
        progress=20,
        done=0,
        total=len(pool),
    )

    def report(done: int, total: int) -> None:
        ratio = done / total if total else 1.0
        _emit(
            progress,
            stage="download",
            message=f"Telechargement {done}/{total}",
            progress=20 + int(65 * ratio),
            done=done,
            total=total,
        )

    def report_extra(done: int, total: int) -> None:
        _emit(
            progress,
            stage="download",
            message=f"Complement {done}/{total}",
            progress=85,
            done=done,
            total=total,
        )

    staging = Path(tempfile.mkdtemp(prefix=".staging_", dir=str(destination)))
    try:
        downloads = download_candidates(
            pool, staging, max_bytes, workers, progress=report
        )
        selected, _ = pick_best(downloads, limit, min_side, orientation)

        if len(selected) < limit and len(filtered) > len(pool):
            extra_count = min(60 - len(pool), max(limit, 6))
            if extra_count > 0:
                extra = filtered[len(pool): len(pool) + extra_count]
                downloads.extend(
                    download_candidates(
                        extra, staging, max_bytes, workers, progress=report_extra
                    )
                )
                selected, _ = pick_best(
                    downloads, limit, min_side, orientation
                )

        _emit(
            progress,
            stage="select",
            message="Classement, doublons et qualite...",
            progress=88,
        )

        if not selected:
            reasons = [item.error for item in downloads if item.error]
            detail = f" ({'; '.join(reasons[:3])})" if reasons else ""
            raise RuntimeError(f"aucune image valide n'a ete telechargee{detail}")

        _emit(
            progress,
            stage="save",
            message="Enregistrement des images...",
            progress=94,
        )
        finalize_selection(selected, destination, slugify(query))
        write_manifest(destination, query, request, source, selected, downloads)
        if gallery:
            write_gallery(destination, query, selected)

        return selected, downloads
    finally:
        shutil.rmtree(staging, ignore_errors=True)
