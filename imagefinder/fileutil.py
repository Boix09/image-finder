from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif", ".webp",
    ".bmp", ".svg", ".avif", ".ico", ".tif", ".tiff",
}

MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/svg+xml": ".svg",
}

TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}


def validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("l'URL doit commencer par http:// ou https://")
    if not parsed.netloc:
        raise ValueError("l'URL n'a pas de nom de domaine")
    return url


def is_url(text: str) -> bool:
    try:
        validate_url(text)
        return True
    except ValueError:
        return False


def to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def normalize_image_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        return "https:" + url
    return url


def _url_extension(url: str) -> str:
    try:
        suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    except ValueError:
        return ""
    return suffix if suffix in IMAGE_EXTENSIONS else ""


def guess_extension(url: str, content_type: str = "") -> str:
    extension = _url_extension(url)
    if extension:
        return extension
    mime = (content_type or "").split(";")[0].strip().lower()
    return MIME_EXT.get(mime, ".jpg")


def _ascii_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def safe_filename(url: str, content_type: str = "") -> str:
    try:
        name = unquote(Path(urlparse(url).path).name)
    except ValueError:
        name = ""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", _ascii_text(name)).strip("._")
    if not name:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        return f"image_{digest}{guess_extension(url, content_type)}"
    if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
        name += guess_extension(url, content_type)
    return name


def unique_path(directory: Path, filename: str) -> Path:
    path = directory / filename
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def reserve_unique_path(directory: Path, filename: str) -> Path:
    """Reserve un nom de fichier de facon atomique (sur pour les threads)."""
    path = directory / filename
    stem, suffix = path.stem, path.suffix
    counter = 0
    while True:
        candidate = path if counter == 0 else directory / f"{stem}_{counter}{suffix}"
        try:
            descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descriptor)
            return candidate
        except FileExistsError:
            counter += 1


def canonical_url(url: str) -> str:
    url = normalize_image_url(url)
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), "")
    )


def slugify(text: str, max_length: int = 60) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", _ascii_text(text)).strip("-").lower()
    return text[:max_length].strip("-") or "images"


def safe_dirname(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")
    return text[:80] or "images"
