from __future__ import annotations

"""Generation et cache de miniatures pour la galerie."""

import hashlib
import mimetypes
import os
import tempfile
import threading
from pathlib import Path

from imagefinder.quality import PIL_AVAILABLE, RESAMPLE
from imagefinder.service import TOOL_ROOT

CACHE_VERSION = 3
DEFAULT_WIDTH = 640
MIN_WIDTH = 160
MAX_WIDTH = 1600

_cache_root: Path | None = None
_cache_lock = threading.Lock()


def _cache_dir() -> Path:
    global _cache_root
    with _cache_lock:
        if _cache_root is not None:
            return _cache_root
        candidates = [
            TOOL_ROOT / ".webcache" / "thumbs",
            Path(tempfile.gettempdir()) / "image-finder-thumbs",
        ]
        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                _cache_root = candidate
                return candidate
            except OSError:
                continue
        _cache_root = Path(tempfile.gettempdir())
        return _cache_root


def _mimetype(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


class Thumbnailer:
    def __init__(self, library) -> None:
        self.library = library

    def get(self, relative: str, width: int = DEFAULT_WIDTH) -> tuple[Path, str]:
        source = self.library.image_path(relative)
        width = max(MIN_WIDTH, min(MAX_WIDTH, int(width or DEFAULT_WIDTH)))

        if source.suffix.lower() == ".svg":
            return source, "image/svg+xml"

        try:
            stat = source.stat()
        except OSError as exc:
            raise FileNotFoundError(str(source)) from exc

        cache = _cache_dir()
        digest = hashlib.sha1(
            f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{width}|v{CACHE_VERSION}".encode(
                "utf-8"
            )
        ).hexdigest()
        folder = cache / digest[:2]
        target = folder / f"{digest[2:]}.webp"
        if target.is_file():
            return target, "image/webp"

        if not PIL_AVAILABLE:
            return source, _mimetype(source)

        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f".{digest[2:]}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            from PIL import Image, ImageOps

            with Image.open(source) as image:
                try:
                    image.draft("RGB", (width * 2, width * 2))
                except Exception:
                    pass
                image = ImageOps.exif_transpose(image)
                if getattr(image, "is_animated", False):
                    image.seek(0)
                image.thumbnail((width, width * 2), RESAMPLE or Image.LANCZOS)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGB")
                try:
                    image.save(temporary, "WEBP", quality=82, method=4)
                except Exception:
                    fallback = temporary.with_suffix(".jpg")
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(fallback, "JPEG", quality=84, optimize=True)
                    os.replace(fallback, target)
                    return target, "image/jpeg"
            os.replace(temporary, target)
            return target, "image/webp"
        except Exception:
            return source, _mimetype(source)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
