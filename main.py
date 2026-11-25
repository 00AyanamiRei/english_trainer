import sys

from PySide6.QtWidgets import QApplication

from app.database import Database
from app.ui.main_window import MainWindow
from app.ui.styles import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("English Trainer")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(Database())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
