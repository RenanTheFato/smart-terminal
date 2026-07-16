"""Application Entry Point

Initialize MainWindow and his inherited widgets
"""

import sys

from PySide6.QtWidgets import QApplication
from pybit.unified_trading import HTTP

from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()