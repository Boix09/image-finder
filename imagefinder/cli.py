from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .downloader import (
    DirectResult,
    download_candidates,
    download_direct,
    finalize_selection,
    pick_best,
)
from .fileutil import is_url, safe_dirname, slugify
from .quality import PIL_AVAILABLE
from .report import write_gallery, write_manifest
from .service import run_download
from .sources import search_images
from .textutil import clean_query, matches_orientation, split_folder

SOURCE_LABELS = {
    "all": "Yandex Images + Wikimedia Commons",
    "yandex": "Yandex Images",
    "commons": "Wikimedia Commons",
    "ddg": "DuckDuckGo (experimental)",
    "openverse": "Openverse (jeton requis)",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cherche sur Internet les meilleures images correspondant a une demande "
            "et les telecharge dans un dossier."
        ),
        epilog=(
            "Exemples :\n"
            "  python image_finder.py \"voiture de sport\" -o voitures -n 10\n"
            "  python image_finder.py \"telecharge les plus belles images de chat\"\n"
            "  python image_finder.py https://exemple.com/photo.jpg -o images\n"
            "  python image_finder.py --file urls.txt -o images"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("request", nargs="*", help="requete en francais ou URL(s) directe(s)")
    parser.add_argument("-f", "--file", help="fichier texte d'URLs (une par ligne)")
    parser.add_argument("-o", "--output", help="dossier de destination")
    parser.add_argument("-n", "--limit", type=int, default=10, help="nombre d'images a garder (defaut : 10, max : 60)")
    parser.add_argument(
        "-s", "--source",
        choices=["all", "yandex", "commons", "ddg", "openverse"], default="all",
        help="source(s) d'images (defaut : all = Yandex + Commons)",
    )
    parser.add_argument("-j", "--workers", type=int, default=6, help="telechargements simultanes (defaut : 6)")
    parser.add_argument("--min-side", type=int, default=700, help="petit cote minimum en pixels (defaut : 700, 0 = desactive)")
    parser.add_argument("--max-mb", type=float, default=25.0, help="taille maximale par image en Mo (defaut : 25)")
    parser.add_argument(
        "--orientation", choices=["any", "landscape", "portrait", "square"], default="any",
        help="orientation souhaitee (defaut : any)",
    )
    parser.add_argument("--dry-run", action="store_true", help="afficher les resultats sans rien telecharger")
    parser.add_argument("--json", action="store_true", help="sortie JSON structuree (pour les integrations IA)")
    parser.add_argument("--no-gallery", action="store_true", help="ne pas creer index.html")
    parser.add_argument("--raw", action="store_true", help="ne pas nettoyer la requete")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def read_urls(positional: list[str], filename: str | None) -> list[str]:
    collected = list(positional)
    if filename:
        text = Path(filename).read_text(encoding="utf-8-sig")
        collected.extend(
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return list(dict.fromkeys(url.strip() for url in collected if url.strip()))


def choose_output(raw_request: str, args) -> tuple[str, Path, str | None]:
    text, folder = split_folder(raw_request)
    query = text.strip() if args.raw else clean_query(text)
    if args.output:
        output = Path(args.output)
    elif folder:
        if re.search(r"[\\/]|^[A-Za-z]:", folder):
            output = Path(folder)
        else:
            output = Path(safe_dirname(folder))
    else:
        output = Path("images") / slugify(query)
    return query, output, folder


def run_direct(urls: list[str], output: Path, max_bytes: int, workers: int) -> int:
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Erreur : impossible de creer le dossier {output} ({exc})", file=sys.stderr)
        return 1
    if not output.is_dir():
        print(f"Erreur : {output} n'est pas un dossier", file=sys.stderr)
        return 1

    successes = 0
    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_direct, url, output, max_bytes): url for url in urls
        }
        for future in as_completed(futures):
            result: DirectResult = future.result()
            if result.path:
                successes += 1
                print(f"[OK]    {result.path}")
            else:
                failures += 1
                print(f"[ECHEC] {result.url} : {result.error}", file=sys.stderr)

    print(f"\nTermine : {successes} reussite(s), {failures} echec(s).")
    return 1 if failures else 0


def run_search(raw_request: str, args, parser: argparse.ArgumentParser) -> int:
    try:
        query, output, folder = choose_output(raw_request, args)
    except ValueError as exc:
        parser.error(str(exc))

    if not query:
        parser.error("precisez un sujet, par exemple : voiture de sport")
    if output.exists() and not output.is_dir():
        print(f"Erreur : {output} existe mais n'est pas un dossier", file=sys.stderr)
        return 2

    print(f'Recherche : "{query}"')
    print(f"Dossier   : {output.resolve()}")
    if folder and not args.output:
        print(f"Dossier detecte dans la demande : {folder}")
    print(f"Sources   : {SOURCE_LABELS[args.source]}")
    if not PIL_AVAILABLE:
        print("Note      : Pillow absent, classement base sur les metadonnees seulement.")

    candidates = search_images(query, args.source, args.limit)
    filtered = []
    for candidate in candidates:
        if candidate.width and candidate.height:
            if args.min_side and min(candidate.width, candidate.height) < args.min_side:
                continue
            if not matches_orientation(candidate.width, candidate.height, args.orientation):
                continue
        filtered.append(candidate)

    if not filtered:
        print("Aucune image trouvee. Essayez une autre formulation ou une autre source.", file=sys.stderr)
        return 2

    if args.dry_run:
        print("\nMeilleurs resultats (aucun telechargement) :")
        for index, candidate in enumerate(filtered[: args.limit], 1):
            dimensions = (
                f"{candidate.width}x{candidate.height}"
                if candidate.width and candidate.height else "?x?"
            )
            print(f"{index:2d}. [{candidate.provider}] {dimensions}  {candidate.title[:80]}")
            print(f"    {candidate.image_url}")
        return 0

    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Erreur : impossible de creer le dossier {output} ({exc})", file=sys.stderr)
        return 1

    max_bytes = int(args.max_mb * 1024 * 1024)
    pool_size = min(len(filtered), min(60, max(args.limit * 2, args.limit + 6)))
    pool = filtered[:pool_size]
    print(f"\nTelechargement de {len(pool)} candidate(s) pour en garder {args.limit}...")

    staging = Path(tempfile.mkdtemp(prefix=".staging_", dir=str(output)))
    downloads = []
    try:
        downloads = download_candidates(pool, staging, max_bytes, args.workers)
        selected, valid = pick_best(downloads, args.limit, args.min_side, args.orientation)

        if len(selected) < args.limit and len(filtered) > len(pool):
            extra_count = min(60 - len(pool), max(args.limit, 6))
            if extra_count > 0:
                extra = filtered[len(pool): len(pool) + extra_count]
                print(f"Complement : {len(extra)} candidate(s)...")
                downloads.extend(
                    download_candidates(extra, staging, max_bytes, args.workers)
                )
                selected, valid = pick_best(
                    downloads, args.limit, args.min_side, args.orientation
                )

        if not selected:
            print("\nAucune image valide n'a ete telechargee.", file=sys.stderr)
            for item in downloads:
                if item.error:
                    print(f"  - {item.error}", file=sys.stderr)
            return 2

        finalize_selection(selected, output, slugify(query))
        write_manifest(output, query, raw_request, args.source, selected, downloads)
        if not args.no_gallery:
            write_gallery(output, query, selected)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    failures = sum(1 for item in downloads if item.error)
    print(
        f"\n{len(selected)} image(s) retenue(s) sur {len(downloads)} telechargee(s), "
        f"{failures} rejet(s)."
    )
    for index, item in enumerate(selected, 1):
        width = item.quality.width if item.quality else item.width
        height = item.quality.height if item.quality else item.height
        dimensions = f"{width}x{height}" if width and height else "?x?"
        print(
            f"{index:2d}. {dimensions:>10}  score {item.final_score:.3f}  "
            f"[{item.candidate.provider}]  {item.candidate.title[:65]}"
        )

    print(f"\nDossier  : {output.resolve()}")
    print(f"Manifeste: {(output / 'manifest.json').resolve()}")
    if not args.no_gallery:
        print(f"Galerie  : {(output / 'index.html').resolve()}")
    if len(selected) < args.limit:
        print(
            f"Note : seulement {len(selected)} image(s) valide(s) sur "
            f"{args.limit} demandee(s)."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit < 1 or args.limit > 60:
        parser.error("--limit doit etre compris entre 1 et 60")
    if args.workers < 1 or args.workers > 32:
        parser.error("--workers doit etre compris entre 1 et 32")
    if args.min_side < 0:
        parser.error("--min-side doit etre positif ou nul")
    if args.max_mb <= 0:
        parser.error("--max-mb doit etre superieur a 0")

    max_bytes = int(args.max_mb * 1024 * 1024)

    if args.file:
        try:
            urls = read_urls(args.request, args.file)
        except OSError as exc:
            parser.error(f"impossible de lire {args.file} ({exc})")
        if not urls:
            parser.error("le fichier ne contient aucune URL")
        invalid = [url for url in urls if not is_url(url)]
        if invalid:
            parser.error(f"URL invalide : {invalid[0]}")
        if args.dry_run:
            print("URLs qui seraient telechargees :")
            for url in urls:
                print(url)
            return 0
        return run_direct(urls, Path(args.output or "downloads"), max_bytes, args.workers)

    if args.request:
        url_count = sum(1 for item in args.request if is_url(item))
        if url_count and url_count != len(args.request):
            parser.error("ne melangez pas des URLs et une requete de recherche")
        if url_count:
            if args.dry_run:
                print("URLs qui seraient telechargees :")
                for url in args.request:
                    print(url)
                return 0
            return run_direct(
                list(args.request), Path(args.output or "downloads"), max_bytes, args.workers
            )

    if not args.request:
        parser.error(
            "indiquez une recherche (ex. : \"voiture de sport\") ou une URL, "
            "ou utilisez --file"
        )

    raw_request = " ".join(args.request).strip()

    if args.json:
        try:
            result = run_download(
                raw_request,
                output=args.output,
                limit=args.limit,
                source=args.source,
                orientation=args.orientation,
                min_side=args.min_side,
                max_mb=args.max_mb,
                workers=args.workers,
                gallery=not args.no_gallery,
                dry_run=args.dry_run,
            )
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
            return 2

    try:
        return run_search(raw_request, args, parser)
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        return 130
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\nErreur : {exc}", file=sys.stderr)
        return 1
