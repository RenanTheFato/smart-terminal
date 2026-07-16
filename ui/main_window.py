from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from api.connector import ByBitClient

class MainWindow(QMainWindow):
  def _drain_events(self):
    while not self.bybit_client.events.empty():
      event = self.bybit_client.events.get_nowait()
      if event["type"] == "status" and not event["connected"]:
        self.status_label.setText(f"Fail to Connect to Bybit: {event['message']}")
      
      if event["type"] == "ticker":
        price = event["data"].get("lastPrice")
        if price:
          self.status_label.setText(f"{event["data"]["symbol"]}: {price}")

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

    # Catch connector queue into main thread
    self.poll_timer = QTimer()
    self.poll_timer.timeout.connect(self._drain_events)
    # Safe Polling to update ever 100ms and not delayed the price
    self.poll_timer.start(100)

    QTimer.singleShot(100, lambda: self.bybit_client.start_ticker_strem())
