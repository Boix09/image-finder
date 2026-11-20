from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageStat

    PIL_AVAILABLE = True
    Image.MAX_IMAGE_PIXELS = 120_000_000
    try:
        RESAMPLE = Image.Resampling.LANCZOS
    except AttributeError:
        RESAMPLE = Image.LANCZOS
except ImportError:
    PIL_AVAILABLE = False
    RESAMPLE = None

FORMAT_EXT = {
    "JPEG": ".jpg",
    "MPO": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "AVIF": ".avif",
    "ICO": ".ico",
}


@dataclass
class Quality:
    sharpness: float
    contrast: float
    colorfulness: float
    exposure: float
    score: float
    width: int
    height: int


def _looks_like_image(head: bytes) -> bool:
    return (
        head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith((b"GIF87a", b"GIF89a"))
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
        or head.startswith(b"BM")
        or head.startswith((b"II*\x00", b"MM\x00*"))
        or b"ftypavif" in head
        or b"ftypheic" in head
    )


def inspect_image(path: Path, content_type: str = "") -> tuple[int, int, str]:
    """Verifie le fichier et renvoie (largeur, hauteur, extension reelle)."""
    if "svg" in (content_type or "").lower():
        return 0, 0, ".svg"

    if PIL_AVAILABLE:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                extension = FORMAT_EXT.get((image.format or "").upper(), "")
                return width, height, extension or path.suffix.lower()
        except Exception as exc:
            raise ValueError(f"image invalide ({exc})") from exc

    head = path.read_bytes()[:32]
    if not _looks_like_image(head):
        raise ValueError("contenu non reconnu comme image")
    return 0, 0, path.suffix.lower()


def analyze_quality(path: Path) -> Quality | None:
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            rgb = image.convert("RGB")
            rgb.thumbnail((640, 640), RESAMPLE)
            gray = rgb.convert("L")
            gray_stat = ImageStat.Stat(gray)
            contrast = min(1.0, gray_stat.stddev[0] / 70.0)
            edges = gray.filter(ImageFilter.FIND_EDGES)
            sharpness = min(1.0, ImageStat.Stat(edges).stddev[0] / 45.0)
            color_stat = ImageStat.Stat(rgb)
            colorfulness = min(
                1.0,
                math.sqrt(sum(channel * channel for channel in color_stat.stddev)) / 150.0,
            )
            mean = gray_stat.mean[0]
            exposure = 1.0 - min(1.0, abs(mean - 128.0) / 128.0)
            score = (
                0.50 * sharpness
                + 0.25 * contrast
                + 0.15 * colorfulness
                + 0.10 * exposure
            )
            return Quality(
                sharpness=round(sharpness, 4),
                contrast=round(contrast, 4),
                colorfulness=round(colorfulness, 4),
                exposure=round(exposure, 4),
                score=round(score, 4),
                width=width,
                height=height,
            )
    except Exception:
        return None


def perceptual_hash(path: Path) -> int | None:
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as image:
            small = image.convert("L").resize((9, 8), RESAMPLE)
            pixels = small.tobytes()
        bits = 0
        for row in range(8):
            for column in range(8):
                left = pixels[row * 9 + column]
                right = pixels[row * 9 + column + 1]
                bits = (bits << 1) | (1 if left > right else 0)
        return bits
    except Exception:
        return None


def hamming(first: int, second: int) -> int:
    return bin(first ^ second).count("1")
