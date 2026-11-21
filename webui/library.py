from __future__ import annotations

"""Lecture, organisation et suppression securisee des images de la bibliotheque."""

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from imagefinder.fileutil import IMAGE_EXTENSIONS, slugify, unique_path
from imagefinder.quality import PIL_AVAILABLE

EXCLUDED_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    ".webcache",
    ".trash",
    ".staging",
}

FORBIDDEN_CHARS = set('<>:"/\\|?*')


class LibraryError(Exception):
    """Erreur lisible par l'utilisateur (chemin invalide, dossier absent...)."""


class Library:
    def __init__(self, config) -> None:
        self.config = config
        self._dimensions: dict[str, tuple[int, int, int, int]] = {}
        self._dimension_lock = threading.Lock()
        self._folders_cache: tuple[float, list[dict]] | None = None
        self._summary_cache: tuple[float, dict] | None = None
        self._images_cache: dict[str, tuple[float, list[dict]]] = {}

    @property
    def root(self) -> Path:
        return Path(self.config.root)

    def _root_mtime(self) -> float:
        try:
            return self.root.stat().st_mtime
        except OSError:
            return 0.0

    def _folder_mtime(self, folder: str) -> float:
        try:
            return (self.root / folder).stat().st_mtime
        except OSError:
            return 0.0

    def _invalidate(self) -> None:
        """Invalide les caches de niveau racine (appelé après modification)."""
        self._folders_cache = None
        self._summary_cache = None
        self._images_cache.clear()

    def relative(self, path: Path) -> str:
        try:
            return path.resolve(strict=False).relative_to(self.root).as_posix()
        except ValueError as exc:
            raise LibraryError("chemin hors de la bibliotheque") from exc

    def _visible_parts(self, path: Path) -> tuple[str, ...]:
        try:
            parts = path.relative_to(self.root).parts
        except ValueError as exc:
            raise LibraryError("chemin hors de la bibliotheque") from exc
        if any(part.startswith(".") or part in EXCLUDED_DIRS for part in parts):
            raise LibraryError("ce fichier est protege")
        return parts

    def resolve(self, relative: str | Path, *, must_exist: bool = False) -> Path:
        text = str(relative or "").replace("\\", "/").strip()
        if "\x00" in text:
            raise LibraryError("chemin invalide")
        target = (self.root / text).resolve(strict=False)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise LibraryError("chemin hors de la bibliotheque") from exc
        if must_exist and not target.exists():
            raise LibraryError(f"introuvable : {text or '.'}")
        return target

    def validate_folder_name(self, name: str) -> str:
        cleaned = str(name or "").strip().strip(" .")
        if not cleaned:
            raise LibraryError("indiquez un nom de dossier")
        if cleaned in {".", ".."} or cleaned.startswith("."):
            raise LibraryError("ce nom de dossier est reserve")
        if any(char in FORBIDDEN_CHARS for char in cleaned):
            raise LibraryError('les caracteres / \\ : * ? " < > | sont interdits')
        if any(ord(char) < 32 for char in cleaned):
            raise LibraryError("le nom contient des caracteres invalides")
        if len(cleaned) > 80:
            raise LibraryError("le nom du dossier est trop long (80 caracteres max)")
        return cleaned

    def ensure_folder(self, name: str) -> Path:
        folder = self.validate_folder_name(name)
        target = self.root / folder
        if target.exists() and not target.is_dir():
            raise LibraryError(f"« {folder} » existe deja mais n'est pas un dossier")
        target.mkdir(parents=True, exist_ok=True)
        self._invalidate()
        return target

    def create_folder(self, name: str) -> str:
        folder = self.validate_folder_name(name)
        target = self.root / folder
        if target.exists():
            raise LibraryError(f"le dossier « {folder} » existe deja")
        target.mkdir(parents=True)
        self._invalidate()
        return folder

    def _walk(self, base: Path):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".") and name not in EXCLUDED_DIRS
            ]
            yield Path(dirpath), filenames

    def _scan(self, base: Path) -> tuple[int, int, int, str]:
        count = 0
        total = 0
        latest = 0
        cover = ""
        for directory, filenames in self._walk(base):
            for name in filenames:
                if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                path = directory / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                count += 1
                total += stat.st_size
                if stat.st_mtime > latest:
                    latest = stat.st_mtime
                    cover = self.relative(path)
        return count, total, int(latest), cover

    def folders(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        mtime = self._root_mtime()
        if self._folders_cache and self._folders_cache[0] == mtime:
            return self._folders_cache[1]
        result = []
        try:
            entries = sorted(self.root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            return []
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name in EXCLUDED_DIRS:
                continue
            count, total, updated, cover = self._scan(entry)
            result.append(
                {
                    "name": entry.name,
                    "path": entry.name,
                    "count": count,
                    "bytes": total,
                    "updated": updated,
                    "cover": cover,
                }
            )
        self._folders_cache = (mtime, result)
        return result

    def summary(self) -> dict:
        mtime = self._root_mtime()
        if self._summary_cache and self._summary_cache[0] == mtime:
            return self._summary_cache[1]
        folders = self.folders()
        images = sum(item["count"] for item in folders)
        total_bytes = sum(item["bytes"] for item in folders)
        try:
            root_entries = list(self.root.iterdir())
        except OSError:
            root_entries = []
        for entry in root_entries:
            if not entry.is_file() or entry.name.startswith("."):
                continue
            if entry.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                total_bytes += entry.stat().st_size
            except OSError:
                continue
            images += 1
        payload = {"folders": folders, "images": images, "bytes": total_bytes}
        self._summary_cache = (mtime, payload)
        return payload

    def _manifest_map(self, directory: Path, cache: dict[Path, dict]) -> dict:
        if directory in cache:
            return cache[directory]
        mapping: dict = {}
        manifest = directory / "manifest.json"
        if manifest.is_file():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                images = payload.get("images") if isinstance(payload, dict) else None
                if isinstance(images, list):
                    for item in images:
                        if isinstance(item, dict) and item.get("file"):
                            mapping[str(item["file"])] = item
            except (OSError, ValueError):
                mapping = {}
        cache[directory] = mapping
        return mapping

    def _probe_dimensions(self, path: Path, stat: os.stat_result) -> tuple[int, int]:
        if not PIL_AVAILABLE:
            return 0, 0
        key = str(path)
        with self._dimension_lock:
            cached = self._dimensions.get(key)
            if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
                return cached[2], cached[3]
        width = height = 0
        try:
            from PIL import Image

            with Image.open(path) as image:
                width, height = image.size
        except Exception:
            width = height = 0
        with self._dimension_lock:
            if len(self._dimensions) > 10_000:
                self._dimensions.clear()
            self._dimensions[key] = (stat.st_mtime_ns, stat.st_size, width, height)
        return width, height

    def images(self, folder: str = "", page: int | None = None, page_size: int | None = None) -> list[dict]:
        base = self.root if not folder else self.resolve(folder)
        if not base.is_dir():
            raise LibraryError(f"dossier introuvable : {folder}")

        cache_key = folder or "__root__"
        mtime = self._folder_mtime(cache_key) if cache_key != "__root__" else self._root_mtime()
        cached = self._images_cache.get(cache_key)
        if cached and cached[0] == mtime:
            result = cached[1]
        else:
            manifest_cache: dict[Path, dict] = {}
            result = []
            for directory, filenames in self._walk(base):
                manifest = self._manifest_map(directory, manifest_cache)
                for name in filenames:
                    suffix = Path(name).suffix.lower()
                    if suffix not in IMAGE_EXTENSIONS:
                        continue
                    path = directory / name
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    meta = manifest.get(name, {})
                    width = int(meta.get("width") or 0)
                    height = int(meta.get("height") or 0)
                    if not width or not height:
                        width, height = self._probe_dimensions(path, stat)
                    relative = self.relative(path)
                    parts = relative.split("/")
                    result.append(
                        {
                            "path": relative,
                            "name": name,
                            "folder": parts[0] if len(parts) > 1 else "",
                            "size": stat.st_size,
                            "mtime": int(stat.st_mtime),
                            "width": width,
                            "height": height,
                            "title": str(meta.get("title") or Path(name).stem),
                            "provider": str(meta.get("provider") or ""),
                            "source_url": str(meta.get("page_url") or ""),
                            "license": str(meta.get("license") or ""),
                            "creator": str(meta.get("creator") or ""),
                            "score": meta.get("score"),
                        }
                    )
            result.sort(key=lambda item: (item["mtime"], item["name"].casefold()), reverse=True)
            self._images_cache[cache_key] = (mtime, result)

        if page is not None and page_size is not None:
            start = max(0, page - 1) * page_size
            end = start + page_size
            return result[start:end]
        return result

    def images_count(self, folder: str = "") -> int:
        base = self.root if not folder else self.resolve(folder)
        if not base.is_dir():
            raise LibraryError(f"dossier introuvable : {folder}")
        return len(self.images(folder))

    def cache_stats(self) -> dict:
        """Retourne la taille du cache de miniatures."""
        from .thumbs import _cache_dir
        cache_dir = _cache_dir()
        total = 0
        count = 0
        try:
            entries = list(cache_dir.rglob("*"))
        except Exception:
            entries = []
        for path in entries:
            try:
                if not path.is_file():
                    continue
                try:
                    total += path.stat().st_size
                    count += 1
                except Exception:
                    continue
            except Exception:
                continue
        return {"count": count, "bytes": total, "path": str(cache_dir)}

    def cache_clear(self) -> dict:
        """Vide le cache de miniatures."""
        from .thumbs import _cache_dir
        cache_dir = _cache_dir()
        freed = 0
        count = 0
        try:
            entries = list(cache_dir.rglob("*"))
        except Exception:
            entries = []
        for path in entries:
            try:
                if not path.is_file():
                    continue
                try:
                    freed += path.stat().st_size
                except Exception:
                    pass
                try:
                    path.unlink()
                    count += 1
                except Exception:
                    continue
            except Exception:
                continue
        # Nettoyage des dossiers vides laisses derriere
        try:
            for dirpath in sorted(
                [p for p in cache_dir.rglob("*") if p.is_dir()],
                key=lambda p: len(p.parts),
                reverse=True,
            ):
                try:
                    dirpath.rmdir()
                except Exception:
                    continue
        except Exception:
            pass
        return {"freed": freed, "count": count, "path": str(cache_dir)}

    def image_path(self, relative: str) -> Path:
        path = self.resolve(relative, must_exist=True)
        self._visible_parts(path)
        if not path.is_file():
            raise LibraryError("cette image n'existe pas")
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise LibraryError("ce fichier n'est pas une image")
        return path

    def _drop_manifest_entry(self, directory: Path, filename: str) -> None:
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            return
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("images"), list):
            return
        images = payload["images"]
        kept = [
            item
            for item in images
            if not (isinstance(item, dict) and str(item.get("file")) == filename)
        ]
        if len(kept) == len(images):
            return
        payload["images"] = kept
        payload["count"] = len(kept)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def delete_image(self, relative: str) -> dict:
        path = self.image_path(relative)
        size = 0
        try:
            size = path.stat().st_size
        except OSError:
            pass
        path.unlink()
        self._drop_manifest_entry(path.parent, path.name)
        with self._dimension_lock:
            self._dimensions.pop(str(path), None)
        self._invalidate()
        return {"freed": size, "path": self.relative(path)}

    def delete_folder(self, relative: str) -> dict:
        path = self.resolve(relative, must_exist=True)
        if path == self.root:
            raise LibraryError("impossible de supprimer la racine de la bibliotheque")
        if not path.is_dir():
            raise LibraryError("ce dossier n'existe pas")
        self._visible_parts(path)
        count, total, _, _ = self._scan(path)
        shutil.rmtree(path)
        self._invalidate()
        return {"images": count, "freed": total, "path": self.relative(path)}

    def copy_selection_to_folder(
        self, relative_paths: list[str], folder_name: str | None = None
    ) -> dict:
        """Copie une selection d'images vers un sous-dossier avec nom moderne.

        Nom par défaut : selection-<slug>-<date-heure>
        ex: selection-gta-2026-11-21-14h30
        """
        from imagefinder.textutil import clean_query

        if not relative_paths:
            raise LibraryError("aucune image selectionnee")

        slug = slugify(folder_name or "selection")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%Hh%M")
        subfolder_name = f"selection-{slug}-{timestamp}" if not folder_name else slug
        target_dir = self.root / subfolder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        copied: list[str] = []
        manifest_images: list[dict] = []

        for relative in relative_paths:
            src = self.image_path(relative)
            if not src.is_file():
                continue
            dest = unique_path(target_dir, src.name)
            shutil.copy2(str(src), str(dest))
            copied.append(self.relative(dest))

            # Lecture du manifest source pour recuperer les metadatas
            src_manifest = src.parent / "manifest.json"
            meta: dict = {}
            if src_manifest.is_file():
                try:
                    payload = json.loads(src_manifest.read_text(encoding="utf-8"))
                    images = payload.get("images") if isinstance(payload, dict) else None
                    if isinstance(images, list):
                        for item in images:
                            if isinstance(item, dict) and str(item.get("file")) == src.name:
                                meta = item
                                break
                except (OSError, ValueError):
                    meta = {}

            manifest_images.append(
                {
                    "file": dest.name,
                    "source_file": src.name,
                    "source_path": relative,
                    "width": meta.get("width"),
                    "height": meta.get("height"),
                    "title": meta.get("title") or src.stem,
                    "provider": meta.get("provider") or "",
                    "source_url": meta.get("page_url") or "",
                    "license": meta.get("license") or "",
                    "creator": meta.get("creator") or "",
                    "score": meta.get("score"),
                    "copied_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Ecriture du manifest du sous-dossier
        manifest_path = target_dir / "manifest.json"
        payload = {
            "folder": subfolder_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "selection",
            "count": len(copied),
            "images": manifest_images,
        }
        try:
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

        self._invalidate()
        return {
            "subfolder": subfolder_name,
            "path": self.relative(target_dir),
            "copied": len(copied),
            "files": copied,
            "manifest": str(manifest_path),
        }

    def move_selection_to_folder(
        self, relative_paths: list[str], folder_name: str
    ) -> dict:
        """Deplace une selection d'images depuis l'inbox vers un dossier definitif.

        Le dossier cible est cree sous la racine avec un nom moderne (slug).
        Les fichiers sont deplaces (pas copies) et le manifest est mis a jour.
        """
        if not relative_paths:
            raise LibraryError("aucune image selectionnee")

        target_name = self.validate_folder_name(folder_name)
        target_dir = self.root / target_name
        target_dir.mkdir(parents=True, exist_ok=True)

        moved: list[str] = []
        manifest_images: list[dict] = []

        for relative in relative_paths:
            src = self.image_path(relative)
            if not src.is_file():
                continue
            dest = unique_path(target_dir, src.name)
            shutil.move(str(src), str(dest))
            moved.append(self.relative(dest))

            # Lecture du manifest source pour recuperer les metadatas
            src_manifest = src.parent / "manifest.json"
            meta: dict = {}
            if src_manifest.is_file():
                try:
                    payload = json.loads(src_manifest.read_text(encoding="utf-8"))
                    images = payload.get("images") if isinstance(payload, dict) else None
                    if isinstance(images, list):
                        for item in images:
                            if isinstance(item, dict) and str(item.get("file")) == src.name:
                                meta = item
                                break
                except (OSError, ValueError):
                    meta = {}

            manifest_images.append(
                {
                    "file": dest.name,
                    "source_file": src.name,
                    "source_path": relative,
                    "width": meta.get("width"),
                    "height": meta.get("height"),
                    "title": meta.get("title") or src.stem,
                    "provider": meta.get("provider") or "",
                    "source_url": meta.get("page_url") or "",
                    "license": meta.get("license") or "",
                    "creator": meta.get("creator") or "",
                    "score": meta.get("score"),
                    "moved_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Ecriture du manifest du dossier cible
        manifest_path = target_dir / "manifest.json"
        payload = {
            "folder": target_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "inbox",
            "count": len(moved),
            "images": manifest_images,
        }
        try:
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

        self._invalidate()
        return {
            "folder": target_name,
            "path": self.relative(target_dir),
            "moved": len(moved),
            "files": moved,
            "manifest": str(manifest_path),
        }

    def delete_selection(self, relative_paths: list[str]) -> dict:
        """Supprime plusieurs images d'un coup.

        Retourne le nombre supprime et l'espace libere.
        """
        if not relative_paths:
            raise LibraryError("aucune image selectionnee")

        deleted = 0
        freed = 0
        errors: list[str] = []

        for relative in relative_paths:
            try:
                path = self.image_path(relative)
                if not path.is_file():
                    continue
                try:
                    freed += path.stat().st_size
                except OSError:
                    pass
                path.unlink()
                self._drop_manifest_entry(path.parent, path.name)
                with self._dimension_lock:
                    self._dimensions.pop(str(path), None)
                deleted += 1
            except Exception as exc:
                errors.append(f"{relative}: {exc}")

        self._invalidate()
        return {
            "deleted": deleted,
            "freed": freed,
            "errors": errors,
        }
