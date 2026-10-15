"""Application entry: open the main window directly.
/ 应用入口：直接打开主窗口"""
import sys

from PySide6.QtWidgets import QApplication

from app.gui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Nikon Camera Suite")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
