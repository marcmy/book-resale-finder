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

    # CI launches the real frozen executable and verifies that styling is
    # actually active—not merely that an unstyled window can open.
    if os.environ.get("BRF_SMOKE_TEST") == "1":
        light_button = window.theme_buttons["light"]
        dark_button = window.theme_buttons["dark"]
        light_button.setChecked(True)
        light_stylesheet = window.styleSheet()
        dark_button.setChecked(True)
        dark_stylesheet = window.styleSheet()
        if not light_stylesheet or not dark_stylesheet or light_stylesheet == dark_stylesheet:
            raise RuntimeError("Theme smoke test failed: light and dark styles were not applied.")
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
