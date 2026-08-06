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

    # CI launches the real frozen executable and verifies that styling and the
    # result-card layout are actually usable—not merely that a window opens.
    if os.environ.get("BRF_SMOKE_TEST") == "1":
        light_button = window.theme_buttons["light"]
        dark_button = window.theme_buttons["dark"]
        light_button.setChecked(True)
        light_stylesheet = window.styleSheet()
        dark_button.setChecked(True)
        dark_stylesheet = window.styleSheet()
        if not light_stylesheet or not dark_stylesheet or light_stylesheet == dark_stylesheet:
            raise RuntimeError("Theme smoke test failed: light and dark styles were not applied.")

        # The prominent scan area is intentionally fixed at four cards.
        hidden_values = [window.item_calls_value, window.item_quota_value]
        if any(window._stat_frames[value].isVisible() for value in hidden_values):
            raise RuntimeError("Stat-card smoke test failed: shipping-only cards are visible.")

        browse_frame = window._stat_frames[window.search_quota_value]
        search_calls_frame = window._stat_frames[window.search_calls_value]
        app.processEvents()
        if browse_frame.geometry().y() != search_calls_frame.geometry().y():
            raise RuntimeError("Stat-card smoke test failed: Browse quota is not in the four-card grid.")

        values = [
            window.processed_value,
            window.found_value,
            window.search_calls_value,
            window.search_quota_value,
        ]
        for index, value in enumerate(values, start=1):
            value.setText(str(index * 100))
        app.processEvents()
        if any(
            not value.text()
            or value.width() <= 0
            or value.height() <= 0
            or value.visibleRegion().isEmpty()
            for value in values
        ):
            raise RuntimeError("Stat-card smoke test failed: one or more values are not visible.")

        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
