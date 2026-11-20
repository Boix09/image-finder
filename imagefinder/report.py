from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .downloader import Downloaded


def _dimensions(item: Downloaded) -> tuple[int, int]:
    if item.quality:
        return item.quality.width, item.quality.height
    return item.width, item.height


def write_manifest(
    output_dir: Path,
    query: str,
    request_text: str,
    source: str,
    selected: list[Downloaded],
    downloads: list[Downloaded],
) -> None:
    images = []
    for item in selected:
        candidate = item.candidate
        width, height = _dimensions(item)
        images.append({
            "file": item.path.name if item.path else "",
            "title": candidate.title,
            "provider": candidate.provider,
            "page_url": candidate.source_page,
            "image_url": item.used_url,
            "original_image_url": candidate.image_url,
            "thumbnail_used": item.used_thumbnail,
            "width": width,
            "height": height,
            "bytes": item.bytes,
            "score": round(item.final_score, 4),
            "metadata_score": round(candidate.meta_score, 4),
            "resolution_score": round(item.resolution_score, 4),
            "quality": asdict(item.quality) if item.quality else None,
            "license": candidate.license,
            "license_url": candidate.license_url,
            "creator": candidate.creator,
        })

    errors = [
        {
            "url": item.candidate.image_url,
            "title": item.candidate.title,
            "provider": item.candidate.provider,
            "error": item.error,
        }
        for item in downloads
        if item.error
    ]

    payload = {
        "version": 2,
        "query": query,
        "request": request_text,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(images),
        "images": images,
        "errors": errors[:100],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_gallery(output_dir: Path, query: str, selected: list[Downloaded]) -> None:
    cards = []
    for rank, item in enumerate(selected, 1):
        candidate = item.candidate
        width, height = _dimensions(item)
        dimensions = f"{width} x {height}" if width and height else "dimensions inconnues"
        source_url = candidate.source_page or item.used_url
        license_text = html.escape(candidate.license or "inconnue")
        if candidate.license_url:
            license_text = (
                f'<a href="{html.escape(candidate.license_url, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{license_text}</a>'
            )
        creator = (
            f"<br>Par {html.escape(candidate.creator)}" if candidate.creator else ""
        )
        cards.append(f"""
        <figure>
          <a href="{html.escape(item.path.name, quote=True)}" target="_blank">
            <img src="{html.escape(item.path.name, quote=True)}" alt="{html.escape(candidate.title, quote=True)}" loading="lazy">
          </a>
          <figcaption>
            <strong>{rank}. {html.escape(candidate.title)}</strong><br>
            {dimensions} - {html.escape(candidate.provider)}<br>
            Licence : {license_text}{creator}<br>
            <a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener noreferrer">Page source</a>
          </figcaption>
        </figure>""")

    document = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Images - {html.escape(query)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f4f4f5; color: #18181b; }}
  h1 {{ font-size: 1.4rem; }}
  .warning {{ background: #fef3c7; padding: 10px 14px; border-radius: 8px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }}
  figure {{ margin: 0; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px #0002; }}
  img {{ width: 100%; height: 220px; object-fit: cover; display: block; }}
  figcaption {{ padding: 10px 12px; font-size: 0.82rem; line-height: 1.45; }}
  a {{ color: #1d4ed8; }}
</style>
</head>
<body>
<h1>Images pour « {html.escape(query)} »</h1>
<p class="warning">Images trouvees sur Internet. Verifiez la licence et les droits avant toute reutilisation.</p>
<div class="grid">{''.join(cards)}
</div>
</body>
</html>
"""
    (output_dir / "index.html").write_text(document, encoding="utf-8")
