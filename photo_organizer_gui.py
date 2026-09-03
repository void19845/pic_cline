#!/usr/bin/env python3
"""
photo_organizer_gui.py — PyQt6 UI entry point (Phase 2).

Replaces photo_organizer_ui.py (Tkinter). Runs the pipeline in-process
via ui/pipeline_bridge.py (QThread + signals) instead of shelling out to
photo_organizer.py as a subprocess and parsing stdout.

Run:  python photo_organizer_gui.py
"""
import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet())
    app.setApplicationName("Photo Organizer")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
