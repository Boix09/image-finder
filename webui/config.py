from __future__ import annotations

"""Configuration persistante de l'interface web."""

import json
import os
import tempfile
from pathlib import Path

from imagefinder.service import TOOL_ROOT

CONFIG_FILENAME = "web_config.json"
DEFAULT_ROOT = TOOL_ROOT / "images"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8420
DEFAULT_INBOX_MODE = False
DEFAULT_INBOX_FOLDER = "inbox"

# Sources qui requient une cle API
API_KEY_SOURCES = ("unsplash", "pexels", "pixabay", "smithsonian", "brave")
ENV_VAR_FOR_SOURCE = {
    "unsplash": "UNSPLASH_ACCESS_KEY",
    "pexels": "PEXELS_API_KEY",
    "pixabay": "PIXABAY_API_KEY",
    "smithsonian": "SMITHSONIAN_API_KEY",
    "brave": "BRAVE_API_KEY",
}


def default_config_path() -> Path:
    configured = os.environ.get("IMAGE_FINDER_WEB_CONFIG")
    if configured:
        return Path(configured).expanduser()
    return TOOL_ROOT / CONFIG_FILENAME


class WebConfig:
    """Charge et sauvegarde le repertoire racine de la bibliotheque et les cles API."""

    def __init__(
        self,
        path: str | Path | None = None,
        root: str | Path | None = None,
        inbox_mode: bool | None = None,
        inbox_folder: str | None = None,
    ) -> None:
        self.path = Path(path).expanduser() if path else default_config_path()
        self._root = DEFAULT_ROOT
        self._inbox_mode = DEFAULT_INBOX_MODE
        self._inbox_folder = DEFAULT_INBOX_FOLDER
        self._api_keys: dict[str, str] = {source: "" for source in API_KEY_SOURCES}
        self.load()

        env_root = os.environ.get("IMAGE_FINDER_WEB_ROOT")
        if env_root:
            self.set_root(env_root, persist=False)
        if root:
            self.set_root(root, persist=False)
        if inbox_mode is not None:
            self._inbox_mode = bool(inbox_mode)
        if inbox_folder:
            self._inbox_folder = str(inbox_folder).strip() or DEFAULT_INBOX_FOLDER
        self.ensure_root()
        self.ensure_inbox()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def inbox_mode(self) -> bool:
        return self._inbox_mode

    @property
    def inbox_folder(self) -> str:
        return self._inbox_folder

    @property
    def unsplash_access_key(self) -> str:
        return self._api_keys.get("unsplash", "")

    @property
    def api_keys(self) -> dict[str, str]:
        return dict(self._api_keys)

    @property
    def api_keys_configured(self) -> dict[str, bool]:
        return {source: bool(self._api_keys.get(source, "").strip()) for source in API_KEY_SOURCES}

    @property
    def inbox_root(self) -> Path:
        return self._root / self._inbox_folder

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        raw = data.get("root")
        if isinstance(raw, str) and raw.strip():
            try:
                self._root = self._normalize(raw)
            except (OSError, ValueError):
                pass
        raw_inbox = data.get("inbox_mode")
        if isinstance(raw_inbox, bool):
            self._inbox_mode = raw_inbox
        raw_inbox_folder = data.get("inbox_folder")
        if isinstance(raw_inbox_folder, str) and raw_inbox_folder.strip():
            self._inbox_folder = raw_inbox_folder.strip()
        raw_keys = data.get("api_keys")
        if isinstance(raw_keys, dict):
            for source in API_KEY_SOURCES:
                value = raw_keys.get(source)
                if isinstance(value, str) and value.strip():
                    self._api_keys[source] = value.strip()
                    env_var = ENV_VAR_FOR_SOURCE.get(source)
                    if env_var:
                        os.environ[env_var] = self._api_keys[source]

    def _normalize(self, value: str | Path) -> Path:
        text = os.path.expandvars(str(value)).strip()
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = TOOL_ROOT / path
        return path.resolve(strict=False)

    def set_root(self, value: str | Path, *, persist: bool = True) -> Path:
        if value is None or not str(value).strip():
            raise ValueError("indiquez un chemin de repertoire")

        path = self._normalize(value)
        if path.exists() and not path.is_dir():
            raise ValueError(f"{path} existe mais n'est pas un dossier")

        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"impossible de creer {path} : {exc}") from exc

        probe = path / ".imagefinder-write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ValueError(
                f"le dossier {path} n'est pas accessible en ecriture : {exc}"
            ) from exc

        self._root = path
        if persist:
            self.save()
        return path

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 3,
            "root": str(self._root),
            "inbox_mode": self._inbox_mode,
            "inbox_folder": self._inbox_folder,
            "api_keys": dict(self._api_keys),
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix=".web_config-", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except OSError:
                pass

    def ensure_root(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._root = DEFAULT_ROOT
            self._root.mkdir(parents=True, exist_ok=True)

    def ensure_inbox(self) -> None:
        if self._inbox_mode:
            try:
                self.inbox_root.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def set_inbox_mode(self, enabled: bool, *, persist: bool = True) -> None:
        self._inbox_mode = bool(enabled)
        self.ensure_inbox()
        if persist:
            self.save()

    def set_inbox_folder(self, name: str, *, persist: bool = True) -> None:
        name = str(name).strip() or DEFAULT_INBOX_FOLDER
        self._inbox_folder = name
        self.ensure_inbox()
        if persist:
            self.save()

    def set_api_key(self, source: str, key: str, *, persist: bool = True) -> None:
        if source not in API_KEY_SOURCES:
            raise ValueError(f"source non supportee pour une cle API : {source}")
        self._api_keys[source] = str(key or "").strip()
        env_var = ENV_VAR_FOR_SOURCE.get(source)
        if env_var:
            if self._api_keys[source]:
                os.environ[env_var] = self._api_keys[source]
            elif env_var in os.environ:
                del os.environ[env_var]
        if persist:
            self.save()
