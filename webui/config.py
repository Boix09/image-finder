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


def default_config_path() -> Path:
    configured = os.environ.get("IMAGE_FINDER_WEB_CONFIG")
    if configured:
        return Path(configured).expanduser()
    return TOOL_ROOT / CONFIG_FILENAME


class WebConfig:
    """Charge et sauvegarde le repertoire racine de la bibliotheque."""

    def __init__(
        self,
        path: str | Path | None = None,
        root: str | Path | None = None,
    ) -> None:
        self.path = Path(path).expanduser() if path else default_config_path()
        self._root = DEFAULT_ROOT
        self.load()

        env_root = os.environ.get("IMAGE_FINDER_WEB_ROOT")
        if env_root:
            self.set_root(env_root, persist=False)
        if root:
            self.set_root(root, persist=False)
        self.ensure_root()

    @property
    def root(self) -> Path:
        return self._root

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
        payload = {"version": 3, "root": str(self._root)}
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
