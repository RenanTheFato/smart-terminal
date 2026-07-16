from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from api.connector import ByBitClient

class MainWindow(QMainWindow):
  def __init__(self):
    super().__init__()

    self.setWindowTitle("Smart Finance Terminal")
    self.showMaximized()
    self.setMinimumSize(960, 540)
    self.bybit_client = ByBitClient()

    central = QWidget()
    layout = QVBoxLayout(central)

    self.status_label = QLabel("Connecting to ByBit...")
    self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(self.status_label)

    self.setCentralWidget(central)

    result = self.bybit_client.check_connection()

    if result == "Faild":
      self.status_label.setText("Fail to Connect to Bybit")
    
    self.status_label.setText("Connected Successfully")

    QTimer.singleShot(100, self.bybit_client.check_connection)
