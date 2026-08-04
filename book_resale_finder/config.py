from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .constants import APP_NAME, DEFAULT_CONFIG, KEYRING_SERVICE


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def config_path() -> Path:
    return executable_dir() / "config.yaml"


def user_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        path = root / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "book-resale-finder"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or config_path()
    config = deepcopy(DEFAULT_CONFIG)
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                config.update(loaded)
        except (OSError, yaml.YAMLError):
            pass
    return config


def resolve_path(value: str | os.PathLike[str], *, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base or executable_dir()) / path


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "theme": "auto",
        "include_shipping": False,
        "input_file": "",
    }
    path = settings_path()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            defaults.update(loaded)
    except (OSError, ValueError):
        pass
    return defaults


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    temp.replace(path)


def load_credentials(config: dict[str, Any]) -> tuple[str | None, str | None]:
    client_id = str(config.get("client_id") or os.getenv("EBAY_CLIENT_ID") or "").strip()
    client_secret = str(config.get("client_secret") or os.getenv("EBAY_CLIENT_SECRET") or "").strip()
    if client_id and client_secret:
        return client_id, client_secret

    try:
        import keyring

        # Read the new service first, then transparently migrate credentials
        # saved by the original isbn_lookup.exe.
        service_names = (KEYRING_SERVICE, "ebay_api_credentials")
        for service in service_names:
            client_id = client_id or (keyring.get_password(service, "client_id") or "").strip()
            client_secret = client_secret or (keyring.get_password(service, "client_secret") or "").strip()
            if client_id and client_secret:
                break
    except Exception:
        pass

    if not (client_id and client_secret):
        env_path = executable_dir() / ".env"
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if not separator:
                    continue
                if key.strip() == "EBAY_CLIENT_ID" and not client_id:
                    client_id = value.strip().strip('"').strip("'")
                elif key.strip() == "EBAY_CLIENT_SECRET" and not client_secret:
                    client_secret = value.strip().strip('"').strip("'")
        except OSError:
            pass
    return client_id or None, client_secret or None


def save_credentials(client_id: str, client_secret: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, "client_id", client_id.strip())
    keyring.set_password(KEYRING_SERVICE, "client_secret", client_secret.strip())


def credentials_present(config: dict[str, Any]) -> bool:
    return all(load_credentials(config))
