from __future__ import annotations

import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

from .fileutil import canonical_url, normalize_image_url, to_int
from .textutil import metadata_score, strip_html

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
COMMONS_UA = "ImageFinder/2.0 (personal image search and download tool)"
TIMEOUT = (10, 30)


@dataclass
class Candidate:
    image_url: str
    title: str
    provider: str
    source_page: str = ""
    width: int = 0
    height: int = 0
    rank: int = 999
    license: str = "unknown"
    license_url: str = ""
    creator: str = ""
    thumbnail: str = ""
    meta_score: float = 0.0


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    })
    return session


def _make_candidate(
    item: dict,
    provider: str,
    rank: int,
    *,
    image_key: str = "image_url",
    title_key: str = "title",
) -> Candidate | None:
    image_url = normalize_image_url(str(item.get(image_key) or ""))
    if not image_url:
        return None
    return Candidate(
        image_url=image_url,
        title=strip_html(str(item.get(title_key) or "")) or "Sans titre",
        provider=provider,
        source_page=str(item.get("source_page") or ""),
        width=to_int(item.get("width")),
        height=to_int(item.get("height")),
        rank=rank,
        license=str(item.get("license") or "unknown"),
        license_url=str(item.get("license_url") or ""),
        creator=strip_html(str(item.get("creator") or "")),
        thumbnail=normalize_image_url(str(item.get("thumbnail") or "")),
    )


YANDEX_PATTERN = re.compile(
    r'"alt":"(?P<alt>(?:[^"\\]|\\.)*)",'
    r'"width":(?P<width>\d+),"height":(?P<height>\d+),'
    r'"origWidth":(?P<orig_width>\d+),"origHeight":(?P<orig_height>\d+),'
    r'"origUrl":"(?P<url>(?:[^"\\]|\\.)*)",'
    r'"snippet":\{"title":"(?P<title>(?:[^"\\]|\\.)*)",'
    r'"domain":"(?P<domain>(?:[^"\\]|\\.)*)",'
    r'"url":"(?P<page>(?:[^"\\]|\\.)*)"'
)


def _json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return value.replace('\\"', '"').replace("\\/", "/")


def search_yandex(query: str, limit: int) -> list[Candidate]:
    response = requests.get(
        "https://yandex.com/images/search",
        params={"text": query},
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=TIMEOUT,
    )
    if response.status_code == 429:
        raise RuntimeError("Yandex limite les requetes, reessayez plus tard")
    response.raise_for_status()
    text = html.unescape(response.text)
    if '"origUrl"' not in text and "captcha" in text.lower():
        raise RuntimeError("Yandex demande un captcha, reessayez plus tard")

    results: list[Candidate] = []
    for index, match in enumerate(YANDEX_PATTERN.finditer(text)):
        if len(results) >= limit:
            break
        image_url = normalize_image_url(_json_string(match.group("url")))
        if not image_url:
            continue
        prefix = text[max(0, match.start() - 1500): match.start()]
        thumbnails = re.findall(r'"image":"((?:https?:)?//avatars[^"]+)"', prefix)
        thumbnail = (
            normalize_image_url(_json_string(thumbnails[-1])) if thumbnails else ""
        )
        width = to_int(match.group("orig_width")) or to_int(match.group("width"))
        height = to_int(match.group("orig_height")) or to_int(match.group("height"))
        title = _json_string(match.group("title")) or _json_string(match.group("alt"))
        results.append(Candidate(
            image_url=image_url,
            title=strip_html(title) or "Sans titre",
            provider="Yandex Images",
            source_page=_json_string(match.group("page")),
            width=width,
            height=height,
            rank=index + 1,
            thumbnail=thumbnail,
        ))
    return results


def search_duckduckgo(query: str, limit: int) -> list[Candidate]:
    with _session() as session:
        page = session.get(
            "https://duckduckgo.com/",
            params={"q": query, "iax": "images", "ia": "images"},
            timeout=TIMEOUT,
        )
        page.raise_for_status()
        match = re.search(r'vqd=["\']?([\d-]+)', page.text)
        if not match:
            raise RuntimeError("DuckDuckGo a bloque la requete (captcha ou page vide)")

        response = session.get(
            "https://duckduckgo.com/i.js",
            params={
                "l": "fr-fr", "o": "json", "q": query,
                "vqd": match.group(1), "f": ",,,", "p": "1",
            },
            headers={
                "Referer": "https://duckduckgo.com/",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("reponse JSON invalide de DuckDuckGo") from exc

    if response.status_code == 202 or payload.get("challenge"):
        raise RuntimeError("DuckDuckGo impose un challenge anti-robot (source ignoree)")

    results: list[Candidate] = []
    for index, item in enumerate(payload.get("results") or []):
        if len(results) >= limit:
            break
        image_url = normalize_image_url(str(item.get("image") or item.get("thumbnail") or ""))
        if not image_url:
            continue
        results.append(Candidate(
            image_url=image_url,
            title=strip_html(str(item.get("title") or "")) or "Sans titre",
            provider="DuckDuckGo",
            source_page=str(item.get("url") or ""),
            width=to_int(item.get("width")),
            height=to_int(item.get("height")),
            rank=index + 1,
            thumbnail=normalize_image_url(str(item.get("thumbnail") or "")),
        ))
    return results


def search_openverse(query: str, limit: int) -> list[Candidate]:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("OPENVERSE_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        "https://api.openverse.org/v1/images/",
        params={"q": query, "page_size": min(limit, 50), "page": 1},
        headers=headers,
        timeout=TIMEOUT,
    )
    if response.status_code == 429:
        raise RuntimeError("limite de requetes Openverse atteinte, reessayez plus tard")
    if response.status_code in (401, 403):
        raise RuntimeError("acces refuse par Openverse (jeton OPENVERSE_ACCESS_TOKEN requis)")
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("reponse JSON invalide d'Openverse") from exc

    results: list[Candidate] = []
    for index, item in enumerate(payload.get("results") or []):
        if len(results) >= limit:
            break
        if item.get("mature"):
            continue
        image_url = normalize_image_url(str(item.get("url") or item.get("thumbnail") or ""))
        if not image_url:
            continue
        license_name = str(item.get("license") or "unknown")
        version = str(item.get("license_version") or "").strip()
        if version:
            license_name = f"{license_name} {version}"
        results.append(Candidate(
            image_url=image_url,
            title=strip_html(str(item.get("title") or "")) or "Sans titre",
            provider="Openverse",
            source_page=str(item.get("foreign_landing_url") or ""),
            width=to_int(item.get("width")),
            height=to_int(item.get("height")),
            rank=index + 1,
            license=license_name,
            license_url=str(item.get("license_url") or ""),
            creator=strip_html(str(item.get("creator") or "")),
            thumbnail=normalize_image_url(str(item.get("thumbnail") or "")),
        ))
    return results


def _commons_value(metadata: dict, key: str) -> str:
    entry = metadata.get(key) or {}
    return strip_html(str(entry.get("value") or ""))


def search_commons(query: str, limit: int) -> list[Candidate]:
    response = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": min(limit, 50),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1600,
        },
        headers={"User-Agent": COMMONS_UA},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("reponse JSON invalide de Wikimedia Commons") from exc

    pages = (payload.get("query") or {}).get("pages") or {}
    ordered = sorted(pages.values(), key=lambda page: page.get("index", 999))
    allowed_mimes = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    results: list[Candidate] = []

    for index, page in enumerate(ordered):
        if len(results) >= limit:
            break
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in allowed_mimes:
            continue
        image_url = normalize_image_url(str(info.get("thumburl") or info.get("url") or ""))
        if not image_url:
            continue
        metadata = info.get("extmetadata") or {}
        title = re.sub(r"^File:\s*", "", str(page.get("title") or ""), flags=re.IGNORECASE)
        results.append(Candidate(
            image_url=image_url,
            title=strip_html(title.replace("_", " ")) or "Sans titre",
            provider="Wikimedia Commons",
            source_page=str(info.get("descriptionurl") or ""),
            width=to_int(info.get("thumbwidth") or info.get("width")),
            height=to_int(info.get("thumbheight") or info.get("height")),
            rank=index + 1,
            license=_commons_value(metadata, "LicenseShortName") or "unknown",
            license_url=_commons_value(metadata, "LicenseUrl"),
            creator=_commons_value(metadata, "Artist")[:200],
            thumbnail=normalize_image_url(str(info.get("thumburl") or "")),
        ))
    return results


def search_images(query: str, source: str | list[str], limit: int) -> list[Candidate]:
    if isinstance(source, str):
        source_set: set[str] = {source.strip().lower()}
    else:
        source_set = {str(s).strip().lower() for s in source if str(s).strip()}
    if not source_set:
        source_set = {"all"}
    providers = []
    if "all" in source_set or "yandex" in source_set:
        providers.append(("Yandex Images", search_yandex))
    if "all" in source_set or "commons" in source_set:
        providers.append(("Wikimedia Commons", search_commons))
    if "all" in source_set or "unsplash" in source_set:
        providers.append(("Unsplash", search_unsplash))
    if "ddg" in source_set:
        providers.append(("DuckDuckGo", search_duckduckgo))
    if "openverse" in source_set:
        providers.append(("Openverse", search_openverse))

    per_source = min(60, max(30, limit * 4))
    collected: list[Candidate] = []
    errors: dict[str, str] = {}
    print(f"Interrogation de {len(providers)} source(s)...")

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(function, query, per_source): name
            for name, function in providers
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results = future.result()
                print(f"  {name}: {len(results)} resultat(s)")
                collected.extend(results)
            except Exception as exc:
                errors[name] = str(exc)
                print(f"  {name}: erreur ({exc})", file=sys.stderr)

    seen: set[str] = set()
    unique: list[Candidate] = []
    for candidate in collected:
        key = canonical_url(candidate.image_url)
        if not key or key in seen:
            continue
        seen.add(key)
        candidate.meta_score = metadata_score(
            candidate.title, candidate.rank, candidate.provider, query
        )
        unique.append(candidate)

    unique.sort(key=lambda candidate: candidate.meta_score, reverse=True)
    print(f"  Total: {len(unique)} candidate(s) unique(s)")

    if not unique and errors:
        detail = "; ".join(f"{n}: {e}" for n, e in errors.items())
        raise RuntimeError(
            "aucune image trouvee. Erreurs par source : " + detail
        )

    return unique


def search_unsplash(query: str, limit: int) -> list[Candidate]:
    """Recherche des images sur Unsplash via l'API publique.

    Requiert la variable d'environnement UNSPLASH_ACCESS_KEY.
    Respecte les règles d'attribution Unsplash (photographe + lien Unsplash).
    """
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        raise RuntimeError(
            "source Unsplash ignoree : definissez UNSPLASH_ACCESS_KEY "
            "(variable d'environnement) pour utiliser cette source"
        )

    headers = {
        "Authorization": f"Client-ID {access_key}",
        "Accept-Version": "v1",
        "User-Agent": USER_AGENT,
    }
    params = {
        "query": query,
        "per_page": min(limit, 30),
        "page": 1,
        "order_by": "relevant",
    }
    response = requests.get(
        "https://api.unsplash.com/search/photos",
        params=params,
        headers=headers,
        timeout=TIMEOUT,
    )
    if response.status_code == 401 or response.status_code == 403:
        raise RuntimeError(
            "acces refuse par Unsplash (cle UNSPLASH_ACCESS_KEY invalide ou manquante)"
        )
    if response.status_code == 429:
        raise RuntimeError("limite de requetes Unsplash atteinte, reessayez plus tard")
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("reponse JSON invalide d'Unsplash") from exc

    results: list[Candidate] = []
    for index, item in enumerate(payload.get("results") or []):
        if len(results) >= limit:
            break
        urls = item.get("urls") or {}
        image_url = normalize_image_url(
            str(urls.get("full") or urls.get("regular") or urls.get("raw") or "")
        )
        if not image_url:
            continue
        user = item.get("user") or {}
        creator = str(user.get("name") or "")
        user_links = user.get("links") or {}
        user_link = str(user_links.get("html") or "")
        item_links = item.get("links") or {}
        source_page = str(item_links.get("html") or "")
        description = str(item.get("alt_description") or item.get("description") or "")
        results.append(
            Candidate(
                image_url=image_url,
                title=strip_html(description) or "Sans titre",
                provider="Unsplash",
                source_page=source_page,
                width=to_int(item.get("width")),
                height=to_int(item.get("height")),
                rank=index + 1,
                license="unsplash",
                license_url="https://unsplash.com/license",
                creator=creator,
                thumbnail=normalize_image_url(
                    str(urls.get("thumb") or urls.get("small") or "")
                ),
            )
        )
    return results
