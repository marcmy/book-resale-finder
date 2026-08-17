from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import platform
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import keyring
import pystray
from PIL import Image, ImageDraw
import tkinter as tk
from tkinter import messagebox, ttk

from bridge.server import Config, Handler, SpApiClient


APP_NAME = "Sourcing Cockpit"
APP_VERSION = "0.2.1"
SERVICE_NAME = "SourcingCockpit"
DEFAULT_PORT = 8765
AMAZON_SETUP_DOCS = "https://developer-docs.amazon.com/sp-api/docs/self-authorization"
UPDATE_API = "https://api.github.com/repos/marcmy/book-resale-finder/releases?per_page=50"
UPDATE_TAG_PREFIX = "sourcing-cockpit-v"
MUTEX_NAME = "Local\\SourcingCockpitHelper"
SHOW_EVENT_NAME = "Local\\SourcingCockpitShowSettings"


def app_data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    path = root / "SourcingCockpit"
    path.mkdir(parents=True, exist_ok=True)
    return path


APP_DIR = app_data_dir()
SETTINGS_PATH = APP_DIR / "settings.json"
LOG_PATH = APP_DIR / "helper.log"


def configure_logging() -> None:
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    if sys.stdout is None:
        sys.stdout = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout


def _kernel32() -> Any:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateEventW.restype = ctypes.c_void_p
    kernel32.OpenEventW.restype = ctypes.c_void_p
    return kernel32


def acquire_single_instance() -> Any:
    if os.name != "nt":
        return object()
    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return None
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return None
    return handle


def signal_existing_instance() -> bool:
    if os.name != "nt":
        return False
    EVENT_MODIFY_STATE = 0x0002
    kernel32 = _kernel32()
    for _ in range(15):
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        if handle:
            try:
                return bool(kernel32.SetEvent(handle))
            finally:
                kernel32.CloseHandle(handle)
        time.sleep(0.1)
    return False


def load_settings() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "client_id": "",
        "seller_id": "",
        "marketplace_id": "ATVPDKIKX0DER",
        "region": "NA",
        "port": DEFAULT_PORT,
        "browser_paired_at": "",
    }
    if not SETTINGS_PATH.exists():
        return defaults
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            defaults.update(payload)
    except Exception:
        logging.exception("Could not read settings")
    return defaults


def save_settings(settings: dict[str, Any]) -> None:
    public = {
        "client_id": str(settings.get("client_id", "")).strip(),
        "seller_id": str(settings.get("seller_id", "")).strip(),
        "marketplace_id": str(settings.get("marketplace_id", "ATVPDKIKX0DER")).strip(),
        "region": str(settings.get("region", "NA")).strip().upper(),
        "port": int(settings.get("port", DEFAULT_PORT)),
        "browser_paired_at": str(settings.get("browser_paired_at", "")).strip(),
    }
    temp = SETTINGS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(public, indent=2), encoding="utf-8")
    temp.replace(SETTINGS_PATH)


def get_secret(name: str) -> str:
    return keyring.get_password(SERVICE_NAME, name) or ""


def set_secret(name: str, value: str) -> None:
    value = value.strip()
    if value:
        keyring.set_password(SERVICE_NAME, name, value)
    else:
        try:
            keyring.delete_password(SERVICE_NAME, name)
        except keyring.errors.PasswordDeleteError:
            pass


def get_bridge_token() -> str:
    token = get_secret("bridge_token")
    if token:
        return token
    token = secrets.token_urlsafe(32)
    keyring.set_password(SERVICE_NAME, "bridge_token", token)
    return token


def configured(settings: dict[str, Any] | None = None) -> bool:
    settings = settings or load_settings()
    return all([
        str(settings.get("client_id", "")).strip(),
        str(settings.get("seller_id", "")).strip(),
        str(settings.get("marketplace_id", "")).strip(),
        get_secret("client_secret"),
        get_secret("refresh_token"),
    ])


def make_spapi_config(settings: dict[str, Any] | None = None) -> Config:
    settings = settings or load_settings()
    client_secret = get_secret("client_secret")
    refresh_token = get_secret("refresh_token")
    missing = []
    for key, value in [
        ("client_id", settings.get("client_id")),
        ("client_secret", client_secret),
        ("refresh_token", refresh_token),
        ("seller_id", settings.get("seller_id")),
        ("marketplace_id", settings.get("marketplace_id")),
    ]:
        if not str(value or "").strip():
            missing.append(key)
    if missing:
        raise ValueError("Missing Amazon setup values: " + ", ".join(missing))
    return Config(
        client_id=str(settings["client_id"]).strip(),
        client_secret=client_secret,
        refresh_token=refresh_token,
        seller_id=str(settings["seller_id"]).strip(),
        marketplace_id=str(settings["marketplace_id"]).strip(),
        region=str(settings.get("region", "NA")).strip().upper() or "NA",
        user_agent=f"SourcingCockpit/{APP_VERSION} (Language=Python/3.12; Platform=Windows)",
    )


def marketplace_name(marketplace_id: str) -> str:
    return {
        "ATVPDKIKX0DER": "United States",
        "A2EUQ1WTGCTBG2": "Canada",
        "A1F83G8C2ARO7P": "United Kingdom",
    }.get(marketplace_id, marketplace_id or "Unknown")


def mask_value(value: str, head: int = 3, tail: int = 3) -> str:
    value = str(value or "")
    if not value:
        return "Not configured"
    if len(value) <= head + tail + 1:
        return "•" * len(value)
    return f"{value[:head]}…{value[-tail:]}"


def version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.strip().lstrip("v").split(".")
    values: list[int] = []
    for part in parts[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        values.append(int(digits or 0))
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def make_tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (25, 29, 36, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5, 5, 59, 59), radius=12, fill=(41, 122, 91, 255))
    draw.text((17, 20), "SC", fill=(255, 255, 255, 255))
    return image


class HelperApp:
    def __init__(self, show_configure: bool = False):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.httpd: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.current_client: SpApiClient | None = None
        self.settings_window: tk.Toplevel | None = None
        self.status_window: tk.Toplevel | None = None
        self.status_label: ttk.Label | None = None
        self.status_vars: dict[str, tk.StringVar] = {}
        self.status = "Not configured"
        self.update_status = "Not checked"
        self._quitting = False
        self.activation_event: Any = None
        self._start_activation_listener()

        self.tray = pystray.Icon(
            "SourcingCockpit",
            make_tray_image(),
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem("Status…", self._tray_status, default=True),
                pystray.MenuItem("Settings…", self._tray_settings),
                pystray.MenuItem("Test Amazon connection", self._tray_test),
                pystray.MenuItem("Pair browser extension…", self._tray_pair),
                pystray.MenuItem("Install Firefox extension…", self._tray_firefox, visible=self._xpi_available),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Create diagnostics bundle…", self._tray_diagnostics),
                pystray.MenuItem("Check for updates", self._tray_update),
                pystray.MenuItem("Open log", self._tray_log),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._tray_quit),
            ),
        )
        self.tray.run_detached()
        if configured():
            self.start_server()
        if show_configure or not configured():
            self.root.after(150, self.show_settings)

    def _start_activation_listener(self) -> None:
        if os.name != "nt":
            return
        kernel32 = _kernel32()
        self.activation_event = kernel32.CreateEventW(None, True, False, SHOW_EVENT_NAME)
        if not self.activation_event:
            logging.warning("Could not create activation event")
            return

        def wait_for_activation() -> None:
            while not self._quitting and self.activation_event:
                if kernel32.WaitForSingleObject(self.activation_event, 1000) == 0:
                    kernel32.ResetEvent(self.activation_event)
                    self.root.after(0, self.show_settings)

        threading.Thread(target=wait_for_activation, name="activation-listener", daemon=True).start()

    def _xpi_path(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().with_name("SourcingCockpit.xpi")
        return Path(__file__).resolve().parent / "build" / "firefox" / "SourcingCockpit.xpi"

    def _xpi_available(self, _item: pystray.MenuItem) -> bool:
        return self._xpi_path().exists()

    def _tray_status(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.show_status)

    def _tray_settings(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.show_settings)

    def _tray_test(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.test_amazon_async)

    def _tray_pair(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.start_browser_pairing)

    def _tray_firefox(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.install_firefox_extension)

    def _tray_diagnostics(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.create_diagnostics_bundle)

    def _tray_update(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, lambda: self.check_updates_async(show_no_update=True))

    def _tray_log(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.open_log)

    def _tray_quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self.quit)

    def notify(self, message: str) -> None:
        try:
            self.tray.notify(message, APP_NAME)
        except Exception:
            logging.info("Tray notification: %s", message)

    def set_status(self, status: str) -> None:
        self.status = status
        self.tray.title = f"{APP_NAME} — {status}"
        try:
            self.tray.update_menu()
        except Exception:
            pass
        if self.status_label is not None and self.status_label.winfo_exists():
            self.status_label.configure(text=status)
        self.refresh_status_window()

    def stop_server(self) -> None:
        server = self.httpd
        self.httpd = None
        self.current_client = None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                logging.exception("Could not stop bridge")

    def start_server(self) -> bool:
        self.stop_server()
        try:
            settings = load_settings()
            cfg = make_spapi_config(settings)
            port = int(settings.get("port", DEFAULT_PORT))
            client = SpApiClient(cfg)
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            server.spapi_client = client  # type: ignore[attr-defined]
            server.bridge_token = get_bridge_token()  # type: ignore[attr-defined]
            server.pairing_code = None  # type: ignore[attr-defined]
            server.pairing_expires_at = 0.0  # type: ignore[attr-defined]
            server.pairing_callback = self._browser_paired_from_server  # type: ignore[attr-defined]
            thread = threading.Thread(target=server.serve_forever, name="spapi-bridge", daemon=True)
            thread.start()
            self.httpd = server
            self.current_client = client
            self.server_thread = thread
            self.set_status(f"Running on 127.0.0.1:{port}")
            logging.info("Bridge started on port %s", port)
            return True
        except OSError as exc:
            logging.exception("Bridge could not start")
            if self.local_health_ok():
                self.set_status("Already running")
                return True
            self.set_status(f"Bridge error: {exc}")
            return False
        except Exception as exc:
            logging.exception("Bridge could not start")
            self.set_status(f"Setup needed: {exc}")
            return False

    def local_health_payload(self) -> dict[str, Any]:
        settings = load_settings()
        port = int(settings.get("port", DEFAULT_PORT))
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/health",
            headers={"User-Agent": f"SourcingCockpit/{APP_VERSION}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

    def local_health_ok(self) -> bool:
        return bool(self.local_health_payload().get("ok"))

    def start_browser_pairing(self) -> None:
        if not self.httpd:
            if not configured():
                messagebox.showinfo(
                    APP_NAME,
                    "Configure the Amazon connection first so the local helper can start.",
                    parent=self.settings_window if self.settings_window else self.root,
                )
                self.show_settings()
                return
            if not self.start_server():
                return
        assert self.httpd is not None
        code = secrets.token_urlsafe(24)
        self.httpd.pairing_code = code  # type: ignore[attr-defined]
        self.httpd.pairing_expires_at = time.time() + 120  # type: ignore[attr-defined]
        port = int(load_settings().get("port", DEFAULT_PORT))
        url = f"http://127.0.0.1:{port}/pair#code={urllib.parse.quote(code)}"
        logging.info("Browser pairing window opened for 120 seconds")
        webbrowser.open(url)
        self.notify("Browser pairing opened. Complete it within two minutes.")

    def _browser_paired_from_server(self) -> None:
        def complete() -> None:
            settings = load_settings()
            settings["browser_paired_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_settings(settings)
            logging.info("Browser extension paired with localhost bridge")
            self.notify("Browser extension paired successfully.")
            self.refresh_status_window()
        self.root.after(0, complete)

    def show_status(self) -> None:
        if self.status_window and self.status_window.winfo_exists():
            self.status_window.deiconify()
            self.status_window.lift()
            self.status_window.focus_force()
            self.refresh_status_window()
            return
        window = tk.Toplevel(self.root, name="statusWindow")
        self.status_window = window
        window.title(f"{APP_NAME} Status")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        outer = ttk.Frame(window, padding=18)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(1, weight=1)
        ttk.Label(outer, text="Sourcing Cockpit status", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        fields = [
            ("Version", "version"), ("Helper", "helper"), ("Amazon", "amazon"),
            ("Bridge", "bridge"), ("Marketplace", "marketplace"), ("Seller", "seller"),
            ("Browser pairing", "pairing"), ("Updates", "updates"),
        ]
        self.status_vars = {key: tk.StringVar(value="…") for _, key in fields}
        for row, (label, key) in enumerate(fields, start=1):
            ttk.Label(outer, text=label).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=4)
            ttk.Label(outer, textvariable=self.status_vars[key]).grid(row=row, column=1, sticky="w", pady=4)
        buttons = ttk.Frame(outer)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh_status_window).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Test Amazon", command=self.test_amazon_async).pack(side="left", padx=6)
        ttk.Button(buttons, text="Pair browser", command=self.start_browser_pairing).pack(side="left", padx=6)
        ttk.Button(buttons, text="Diagnostics", command=self.create_diagnostics_bundle).pack(side="left", padx=6)
        ttk.Button(buttons, text="Check updates", command=lambda: self.check_updates_async(True)).pack(side="left", padx=6)
        self.refresh_status_window()
        window.update_idletasks()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 3)
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        window.lift()
        window.focus_force()

    def refresh_status_window(self) -> None:
        if not self.status_vars:
            return
        settings = load_settings()
        health = self.local_health_payload()
        port = int(settings.get("port", DEFAULT_PORT))
        paired = str(settings.get("browser_paired_at", "")).strip()
        values = {
            "version": APP_VERSION,
            "helper": self.status,
            "amazon": "Configured" if configured(settings) else "Setup incomplete",
            "bridge": f"Online on 127.0.0.1:{port}" if health.get("ok") else "Offline",
            "marketplace": marketplace_name(str(settings.get("marketplace_id", ""))),
            "seller": health.get("sellerIdMasked") or mask_value(str(settings.get("seller_id", ""))),
            "pairing": f"Paired {paired}" if paired else "Not paired yet",
            "updates": self.update_status,
        }
        for key, value in values.items():
            var = self.status_vars.get(key)
            if var:
                var.set(str(value))

    def show_settings(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return
        values = load_settings()
        window = tk.Toplevel(self.root, name="settingsWindow")
        self.settings_window = window
        window.title(f"{APP_NAME} {APP_VERSION}")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        outer = ttk.Frame(window, padding=18)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(1, weight=1)
        ttk.Label(outer, text="Amazon connection", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            outer,
            text="One-time setup. Paste the values from your private Amazon SP-API app.\n"
                 "The client secret, refresh token, and localhost bridge token are stored in Windows Credential Manager.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))
        client_id_var = tk.StringVar(value=str(values.get("client_id", "")))
        client_secret_var = tk.StringVar(value=get_secret("client_secret"))
        refresh_var = tk.StringVar(value=get_secret("refresh_token"))
        seller_var = tk.StringVar(value=str(values.get("seller_id", "")))
        marketplace_var = tk.StringVar(value=str(values.get("marketplace_id", "ATVPDKIKX0DER")))
        port_var = tk.StringVar(value=str(values.get("port", DEFAULT_PORT)))
        row = 2
        fields = [
            ("Client ID", client_id_var, False), ("Client secret", client_secret_var, True),
            ("Refresh token", refresh_var, True), ("Seller ID", seller_var, False),
        ]
        for label, variable, secret in fields:
            ttk.Label(outer, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            ttk.Entry(outer, textvariable=variable, width=54, show="•" if secret else "").grid(
                row=row, column=1, columnspan=2, sticky="ew", pady=5
            )
            row += 1
        ttk.Label(outer, text="Marketplace").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Combobox(
            outer, textvariable=marketplace_var, width=51, state="readonly",
            values=["ATVPDKIKX0DER", "A2EUQ1WTGCTBG2", "A1F83G8C2ARO7P"],
        ).grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
        row += 1
        ttk.Label(outer, text="Local port").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(outer, textvariable=port_var, width=12).grid(row=row, column=1, sticky="w", pady=5)
        ttk.Button(outer, text="Amazon setup instructions", command=lambda: webbrowser.open(AMAZON_SETUP_DOCS)).grid(
            row=row, column=2, sticky="e", pady=5
        )
        row += 1
        ttk.Separator(outer).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 10))
        row += 1
        self.status_label = ttk.Label(outer, text=self.status)
        self.status_label.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1
        buttons = ttk.Frame(outer)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew")
        buttons.columnconfigure(0, weight=1)

        def save_and_connect() -> None:
            try:
                port = int(port_var.get().strip())
                if not (1024 <= port <= 65535):
                    raise ValueError("Port must be between 1024 and 65535.")
                existing = load_settings()
                settings = {
                    "client_id": client_id_var.get(),
                    "seller_id": seller_var.get(),
                    "marketplace_id": marketplace_var.get(),
                    "region": "EU" if marketplace_var.get() == "A1F83G8C2ARO7P" else "NA",
                    "port": port,
                    "browser_paired_at": existing.get("browser_paired_at", ""),
                }
                save_settings(settings)
                set_secret("client_secret", client_secret_var.get())
                set_secret("refresh_token", refresh_var.get())
                if not configured(settings):
                    raise ValueError("Fill in all Amazon fields first.")
                if self.start_server():
                    self.notify("Helper is running. Testing Amazon authorization…")
                    self.test_amazon_async()
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=window)

        ttk.Button(buttons, text="Status", command=self.show_status).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(buttons, text="Save & connect", command=save_and_connect).grid(row=0, column=1, padx=4)
        ttk.Button(buttons, text="Test Amazon", command=self.test_amazon_async).grid(row=0, column=2, padx=4)
        ttk.Button(buttons, text="Pair browser", command=self.start_browser_pairing).grid(row=0, column=3, padx=4)
        if self._xpi_path().exists():
            ttk.Button(buttons, text="Install Firefox extension", command=self.install_firefox_extension).grid(
                row=0, column=4, padx=4
            )
        ttk.Button(buttons, text="Hide", command=window.withdraw).grid(row=0, column=5, padx=(12, 0))
        window.update_idletasks()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 3)
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        window.lift()
        window.focus_force()

    def test_amazon_async(self) -> None:
        if not configured():
            self.show_settings()
            self.set_status("Amazon setup is incomplete")
            return
        self.set_status("Testing Amazon authorization…")
        def worker() -> None:
            try:
                client = self.current_client or SpApiClient(make_spapi_config())
                client.access_token()
            except Exception as exc:
                logging.exception("Amazon authorization test failed")
                self.root.after(0, lambda: self._amazon_test_done(False, str(exc)))
            else:
                self.root.after(0, lambda: self._amazon_test_done(True, ""))
        threading.Thread(target=worker, name="amazon-test", daemon=True).start()

    def _amazon_test_done(self, ok: bool, error: str) -> None:
        if ok:
            port = int(load_settings().get("port", DEFAULT_PORT))
            self.set_status(f"Amazon connected · helper online on port {port}")
            self.notify("Amazon connection verified.")
        else:
            self.set_status("Amazon authorization failed")
            messagebox.showerror(
                APP_NAME,
                "Amazon authorization failed. Check the values in Settings.\n\n" + error,
                parent=self.settings_window if self.settings_window else self.root,
            )

    def install_firefox_extension(self) -> None:
        xpi = self._xpi_path()
        if not xpi.exists():
            messagebox.showinfo(
                APP_NAME, "The signed Firefox extension is not bundled in this build yet.",
                parent=self.settings_window if self.settings_window else self.root,
            )
            return
        try:
            os.startfile(xpi)  # type: ignore[attr-defined]
        except Exception:
            logging.exception("Could not open Firefox extension package")
            messagebox.showerror(
                APP_NAME, f"Could not open:\n{xpi}",
                parent=self.settings_window if self.settings_window else self.root,
            )

    def create_diagnostics_bundle(self) -> None:
        try:
            for handler in logging.getLogger().handlers:
                try:
                    handler.flush()
                except Exception:
                    pass
            settings = load_settings()
            health = self.local_health_payload()
            now = datetime.now(timezone.utc)
            path = APP_DIR / f"SourcingCockpit-Diagnostics-{now.strftime('%Y%m%d-%H%M%SZ')}.zip"
            diagnostics = {
                "generatedAt": now.isoformat(timespec="seconds"),
                "app": {"name": APP_NAME, "version": APP_VERSION},
                "runtime": {
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "executable": str(Path(sys.executable).resolve()),
                },
                "settings": {
                    "clientIdMasked": mask_value(str(settings.get("client_id", "")), 4, 4),
                    "sellerIdMasked": mask_value(str(settings.get("seller_id", ""))),
                    "marketplaceId": str(settings.get("marketplace_id", "")),
                    "marketplace": marketplace_name(str(settings.get("marketplace_id", ""))),
                    "region": str(settings.get("region", "")),
                    "port": int(settings.get("port", DEFAULT_PORT)),
                    "browserPairedAt": str(settings.get("browser_paired_at", "")),
                },
                "credentialsPresent": {
                    "clientSecret": bool(get_secret("client_secret")),
                    "refreshToken": bool(get_secret("refresh_token")),
                    "bridgeToken": bool(get_secret("bridge_token")),
                },
                "bridgeHealth": health,
                "currentStatus": self.status,
                "updateStatus": self.update_status,
            }
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("diagnostics.json", json.dumps(diagnostics, indent=2, ensure_ascii=False))
                if LOG_PATH.exists():
                    archive.write(LOG_PATH, arcname="helper.log")
            logging.info("Diagnostics bundle created: %s", path)
            try:
                os.startfile(APP_DIR)  # type: ignore[attr-defined]
            except Exception:
                pass
            messagebox.showinfo(
                APP_NAME,
                f"Diagnostics bundle created:\n\n{path}\n\nNo Amazon secrets or localhost bridge token are included.",
                parent=self.status_window if self.status_window else self.root,
            )
        except Exception as exc:
            logging.exception("Could not create diagnostics bundle")
            messagebox.showerror(APP_NAME, f"Could not create diagnostics bundle:\n\n{exc}")

    def check_updates_async(self, show_no_update: bool = False) -> None:
        self.update_status = "Checking…"
        self.refresh_status_window()
        def worker() -> None:
            try:
                request = urllib.request.Request(
                    UPDATE_API,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": f"SourcingCockpit/{APP_VERSION}"},
                )
                with urllib.request.urlopen(request, timeout=8) as response:
                    releases = json.loads(response.read().decode("utf-8"))
                candidates: list[tuple[tuple[int, int, int], str, str]] = []
                if isinstance(releases, list):
                    for release in releases:
                        if not isinstance(release, dict) or release.get("draft"):
                            continue
                        tag = str(release.get("tag_name") or "")
                        if not tag.startswith(UPDATE_TAG_PREFIX):
                            continue
                        version = tag[len(UPDATE_TAG_PREFIX):]
                        candidates.append((version_tuple(version), version, str(release.get("html_url") or "")))
                candidates.sort(reverse=True)
                latest = candidates[0] if candidates else None
            except Exception as exc:
                logging.exception("Update check failed")
                self.root.after(0, lambda: self._update_check_done(None, show_no_update, str(exc)))
            else:
                self.root.after(0, lambda: self._update_check_done(latest, show_no_update, ""))
        threading.Thread(target=worker, name="update-check", daemon=True).start()

    def _update_check_done(
        self,
        latest: tuple[tuple[int, int, int], str, str] | None,
        show_no_update: bool,
        error: str,
    ) -> None:
        if error:
            self.update_status = "Check failed"
            self.refresh_status_window()
            if show_no_update:
                messagebox.showerror(APP_NAME, f"Update check failed:\n\n{error}")
            return
        if not latest:
            self.update_status = "No published Sourcing Cockpit release yet"
            self.refresh_status_window()
            if show_no_update:
                messagebox.showinfo(APP_NAME, "No published Sourcing Cockpit release was found yet.")
            return
        latest_tuple, latest_version, release_url = latest
        if latest_tuple > version_tuple(APP_VERSION):
            self.update_status = f"{latest_version} available"
            self.refresh_status_window()
            if messagebox.askyesno(APP_NAME, f"Sourcing Cockpit {latest_version} is available.\n\nOpen the release page?") and release_url:
                webbrowser.open(release_url)
        else:
            self.update_status = f"Up to date ({APP_VERSION})"
            self.refresh_status_window()
            if show_no_update:
                messagebox.showinfo(APP_NAME, f"Sourcing Cockpit {APP_VERSION} is up to date.")

    def open_log(self) -> None:
        try:
            os.startfile(LOG_PATH)  # type: ignore[attr-defined]
        except Exception:
            webbrowser.open(LOG_PATH.as_uri())

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.stop_server()
        if self.activation_event and os.name == "nt":
            try:
                kernel32 = _kernel32()
                kernel32.SetEvent(self.activation_event)
                kernel32.CloseHandle(self.activation_event)
            except Exception:
                pass
            self.activation_event = None
        try:
            self.tray.stop()
        except Exception:
            pass
        self.root.quit()
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args, _ = parser.parse_known_args()
    configure_logging()
    if args.smoke_test:
        logging.info("%s %s smoke test passed imports", APP_NAME, APP_VERSION)
        return 0
    instance = acquire_single_instance()
    if instance is None:
        signal_existing_instance()
        return 0
    logging.info("%s %s starting", APP_NAME, APP_VERSION)
    app = HelperApp(show_configure=args.configure)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())