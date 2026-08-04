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

    # CI launches the real frozen executable and asks it to close after the UI
    # has entered the event loop. This catches packaging failures that unit
    # tests and a successful PyInstaller build cannot detect.
    if os.environ.get("BRF_SMOKE_TEST") == "1":
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
