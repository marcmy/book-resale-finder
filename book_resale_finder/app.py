from __future__ import annotations

import os
import sys

from .constants import APP_ID, APP_NAME


def main() -> int:
    # Keep Qt imports inside main so the frozen launcher can record import and
    # DLL failures in startup.log instead of silently disappearing.
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .gui import MainWindow

    # Applying a Qt stylesheet can itself emit PaletteChange. The original
    # changeEvent handler reacted by applying the stylesheet again, producing
    # an infinite recursion and native stack overflow before the window opened.
    original_apply_theme = MainWindow._apply_theme

    def guarded_apply_theme(window: MainWindow) -> None:
        if getattr(window, "_applying_theme", False):
            return
        window._applying_theme = True
        try:
            original_apply_theme(window)
        finally:
            window._applying_theme = False

    MainWindow._apply_theme = guarded_apply_theme

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("marcmy")
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    # CI launches the real frozen executable and asks it to close after the UI
    # has entered the event loop. This catches packaging and startup failures
    # that unit tests and a successful PyInstaller build cannot detect.
    if os.environ.get("BRF_SMOKE_TEST") == "1":
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
