from __future__ import annotations

import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .fileutil import (
    guess_extension,
    reserve_unique_path,
    safe_filename,
    unique_path,
    validate_url,
)
from .quality import Quality, analyze_quality, hamming, inspect_image, perceptual_hash
from .sources import Candidate
from .textutil import matches_orientation, resolution_score

CHUNK_SIZE = 64 * 1024
TIMEOUT = (10, 30)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


@dataclass
class DirectResult:
    url: str
    path: Path | None = None
    error: str | None = None


@dataclass
class Downloaded:
    candidate: Candidate
    path: Path | None
    used_url: str = ""
    used_thumbnail: bool = False
    bytes: int = 0
    width: int = 0
    height: int = 0
    quality: Quality | None = None
    phash: int | None = None
    final_score: float = 0.0
    resolution_score: float = 0.0
    error: str | None = None


def _download_once(
    url: str,
    destination: Path,
    referer: str,
    max_bytes: int,
) -> tuple[str, int]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer

    with requests.Session() as session:
        with session.get(
            url,
            stream=True,
            timeout=TIMEOUT,
            headers=headers,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            content_type = (
                response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            )
            allowed = (
                not content_type
                or content_type.startswith("image/")
                or content_type in {"application/octet-stream", "binary/octet-stream"}
            )
            if not allowed:
                raise ValueError(f"le contenu n'est pas une image ({content_type})")

            announced = int(response.headers.get("Content-Length") or 0)
            if announced > max_bytes:
                raise ValueError("image trop volumineuse (Content-Length)")

            temporary = destination.with_name(destination.name + ".part")
            written = 0
            try:
                with temporary.open("wb") as file:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise ValueError("image trop volumineuse")
                        file.write(chunk)
                if written == 0:
                    raise ValueError("fichier vide")
                temporary.replace(destination)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise

    return content_type, written


def download_candidate(
    candidate: Candidate,
    staging_dir: Path,
    max_bytes: int,
    index: int,
) -> Downloaded:
    digest = hashlib.sha1(candidate.image_url.encode("utf-8")).hexdigest()[:10]
    destination = staging_dir / f"{index:03d}_{digest}{guess_extension(candidate.image_url)}"
    used_url = candidate.image_url
    used_thumbnail = False

    try:
        content_type, size = _download_once(
            candidate.image_url, destination, candidate.source_page, max_bytes
        )
    except Exception as first_error:
        thumbnail = candidate.thumbnail
        if not thumbnail or thumbnail == candidate.image_url:
            return Downloaded(candidate=candidate, path=None, error=str(first_error))
        digest = hashlib.sha1(thumbnail.encode("utf-8")).hexdigest()[:10]
        destination = staging_dir / f"{index:03d}_{digest}{guess_extension(thumbnail)}"
        try:
            content_type, size = _download_once(
                thumbnail, destination, candidate.source_page, max_bytes
            )
            used_url = thumbnail
            used_thumbnail = True
        except Exception as second_error:
            return Downloaded(
                candidate=candidate,
                path=None,
                error=f"{first_error} | miniature: {second_error}",
            )

    try:
        width, height, actual_extension = inspect_image(destination, content_type)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return Downloaded(candidate=candidate, path=None, error=str(exc))

    if actual_extension and actual_extension != destination.suffix.lower():
        renamed = unique_path(staging_dir, destination.stem + actual_extension)
        destination.replace(renamed)
        destination = renamed

    quality = analyze_quality(destination)
    if quality:
        width, height = quality.width, quality.height

    return Downloaded(
        candidate=candidate,
        path=destination,
        used_url=used_url,
        used_thumbnail=used_thumbnail,
        bytes=size,
        width=width,
        height=height,
        quality=quality,
        phash=perceptual_hash(destination),
    )


def download_candidates(
    candidates: list[Candidate],
    staging_dir: Path,
    max_bytes: int,
    workers: int,
    progress: Callable[[int, int], None] | None = None,
) -> list[Downloaded]:
    """Telecharge les candidats et signale l'avancement (faits, total)."""
    total = len(candidates)
    results: list[Downloaded] = []
    done = 0
    if progress is not None:
        try:
            progress(0, total)
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(download_candidate, candidate, staging_dir, max_bytes, index)
            for index, candidate in enumerate(candidates)
        ]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                print(f"  erreur de telechargement : {exc}")
            done += 1
            if progress is not None:
                try:
                    progress(done, total)
                except Exception:
                    pass
    return results


def download_direct(url: str, save_dir: Path, max_bytes: int) -> DirectResult:
    destination = None
    try:
        url = validate_url(url)
        save_dir.mkdir(parents=True, exist_ok=True)
        destination = reserve_unique_path(save_dir, safe_filename(url))
        content_type, _ = _download_once(url, destination, "", max_bytes)
        _, _, actual_extension = inspect_image(destination, content_type)
        if actual_extension and actual_extension != destination.suffix.lower():
            renamed = reserve_unique_path(save_dir, destination.stem + actual_extension)
            try:
                destination.replace(renamed)
            except Exception:
                renamed.unlink(missing_ok=True)
                raise
            destination = renamed
        return DirectResult(url=url, path=destination)
    except Exception as exc:
        if destination is not None:
            destination.unlink(missing_ok=True)
        return DirectResult(url=url, error=str(exc))


def pick_best(
    downloads: list[Downloaded],
    limit: int,
    min_side: int,
    orientation: str,
) -> tuple[list[Downloaded], list[Downloaded]]:
    valid: list[Downloaded] = []
    for item in downloads:
        if not item.path or item.error:
            continue
        width = item.quality.width if item.quality else item.width
        height = item.quality.height if item.quality else item.height
        if width and height:
            if min_side and min(width, height) < min_side:
                item.error = f"resolution trop faible ({width}x{height})"
                continue
            if not matches_orientation(width, height, orientation):
                item.error = f"orientation incompatible ({width}x{height})"
                continue
        item.resolution_score = resolution_score(width, height, min_side)
        if item.quality:
            item.final_score = (
                0.45 * item.candidate.meta_score
                + 0.25 * item.resolution_score
                + 0.30 * item.quality.score
            )
        else:
            item.final_score = (
                0.60 * item.candidate.meta_score
                + 0.40 * item.resolution_score
            )
        if item.used_thumbnail:
            item.final_score *= 0.85
        valid.append(item)

    valid.sort(key=lambda item: item.final_score, reverse=True)
    selected: list[Downloaded] = []
    hashes: list[int] = []
    for item in valid:
        if item.phash is not None:
            if any(hamming(item.phash, known) <= 4 for known in hashes):
                item.error = "doublon visuel"
                continue
            hashes.append(item.phash)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected, valid


def finalize_selection(selected: list[Downloaded], output_dir: Path, slug: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for rank, item in enumerate(selected, 1):
        if not item.path:
            continue
        width = item.quality.width if item.quality else item.width
        height = item.quality.height if item.quality else item.height
        dimensions = f"{width}x{height}" if width and height else "image"
        destination = unique_path(output_dir, f"{rank:02d}_{slug[:50]}_{dimensions}.webp")
        try:
            from PIL import Image
            with Image.open(item.path) as image:
                if image.mode in ("RGBA", "LA", "P"):
                    image = image.convert("RGB")
                image.save(destination, "WEBP", quality=85, method=6)
            item.path.unlink(missing_ok=True)
        except Exception:
            # Fallback : garde le format original si la conversion echoue
            extension = item.path.suffix.lower() or ".jpg"
            destination = unique_path(output_dir, f"{rank:02d}_{slug[:50]}_{dimensions}{extension}")
            shutil.move(str(item.path), str(destination))
        item.path = destination
