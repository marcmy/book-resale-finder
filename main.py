from __future__ import annotations

import ctypes
import faulthandler
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

APP_NAME = "Book Resale Finder"
_LOG_HANDLE: TextIO | None = None


def _log_path() -> Path:
    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")

    if local_app_data:
        candidates.append(Path(local_app_data) / APP_NAME / "startup.log")
    if app_data:
        candidates.append(Path(app_data) / APP_NAME / "startup.log")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "startup.log")
    candidates.append(Path.cwd() / "startup.log")

    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("a", encoding="utf-8"):
                pass
            return candidate
        except OSError:
            continue

    return Path("startup.log")


def _open_log() -> tuple[Path, TextIO | None]:
    global _LOG_HANDLE
    path = _log_path()
    try:
        _LOG_HANDLE = path.open("a", encoding="utf-8", buffering=1)
        return path, _LOG_HANDLE
    except OSError:
        return path, None


def _log(message: str) -> None:
    if _LOG_HANDLE is None:
        return
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        _LOG_HANDLE.write(f"[{timestamp}] {message}\n")
        _LOG_HANDLE.flush()
    except OSError:
        pass


def _configure_frozen_qt_paths() -> None:
    if not getattr(sys, "frozen", False):
        return

    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    plugin_root = bundle_root / "PySide6" / "plugins"
    platform_root = plugin_root / "platforms"

    if plugin_root.is_dir():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))
    if platform_root.is_dir():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platform_root))

    _log(f"Frozen bundle root: {bundle_root}")
    _log(f"Qt plugin root exists: {plugin_root.is_dir()} ({plugin_root})")
    _log(f"Qt platform root exists: {platform_root.is_dir()} ({platform_root})")


def _show_fatal_error(message: str, log_path: Path) -> None:
    text = (
        f"{APP_NAME} could not start.\n\n"
        f"A diagnostic log was written to:\n{log_path}\n\n"
        f"Error:\n{message}"
    )
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, text, f"{APP_NAME} startup error", 0x10)
            return
        except Exception:
            pass

    try:
        print(text, file=sys.stderr or sys.__stderr__)
    except Exception:
        pass


def _run() -> int:
    log_path, handle = _open_log()
    if handle is not None:
        try:
            faulthandler.enable(file=handle, all_threads=True)
        except Exception:
            pass

    _log("=" * 72)
    _log(f"Starting {APP_NAME}")
    _log(f"Executable: {sys.executable}")
    _log(f"Frozen: {getattr(sys, 'frozen', False)}")
    _log(f"Python: {sys.version}")
    _log(f"Working directory: {Path.cwd()}")

    try:
        _configure_frozen_qt_paths()
        from book_resale_finder.app import main

        exit_code = int(main())
        _log(f"Application exited normally with code {exit_code}")
        return exit_code
    except BaseException as exc:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _log("Unhandled startup exception:\n" + details)
        _show_fatal_error(str(exc), log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(_run())
