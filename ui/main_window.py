from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from api.connector import ByBitClient
from ui.widgets.candlestick_chart_widget import CandlestickChartWidget

class _CandleHistoryFetch(QThread):
  # Runs the method get_kline_data() outsise of the main thread
  #QThread moves that wait off the UI thread and the result comes back through aSignal, which Qt safely marshals onto the main thread for us"
  finished_with_data = Signal(object)

  def __init__(self, bybit_client, symbol: str, interval: str, end_ms: int):
    super().__init__()
    self._bybit_client = bybit_client
    self._symbol = symbol
    self._interval = interval
    self._end_ms = end_ms

  def run(self):
    candles = self._bybit_client.get_kline_data(self._symbol, self._interval, end_time_ms=self._end_ms)
    self.finished_with_data.emit(candles)
  

class MainWindow(QMainWindow):
  def __init__(self):
    super().__init__()

    self.setWindowTitle("Smart Finance Terminal")
    self.showMaximized()
    self.setMinimumSize(960, 540)
    self.bybit_client = ByBitClient()
    self._last_history_end_ms: int | None = None

    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # Sup Bar -> Ticker Price
    self.status_label = QLabel("Connecting to ByBit...")
    self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.status_label.setFixedHeight(40)
    layout.addWidget(self.status_label)


    # Candlestick Chart
    self.chart_widget = CandlestickChartWidget()
    layout.addWidget(self.chart_widget, stretch=1)

    # Put before data, connect after would lost the first emit and the guard will stay locked in True
    self.chart_widget.needs_more_history.connect(self.load_more_history)

    # Get Candle Data to Plot into Candlestick Chart
    candles = self.bybit_client.get_kline_data("BTCUSDT", "3")
    if candles:
      self.chart_widget.set_data(candles)

    # Default Setting Central Widget
    self.setCentralWidget(central)

    # Catch connector queue into main thread
    self.poll_timer = QTimer()
    self.poll_timer.timeout.connect(self._drain_events)
    # Safe Polling to update ever 100ms and not delayed the price
    self.poll_timer.start(100)

    QTimer.singleShot(100, lambda: self.bybit_client.start_ticker_strem())

  def load_more_history(self):
    logger.info("load_more_history called")
    oldest = self.chart_widget.oldest_timestamp()
    if oldest is None:
      self.chart_widget.set_loading_more(False)
      return
    
    end_ms = int(oldest.timestamp() * 1000) - 1

    # Check if this is the same boundary as the last request, the edge hasn't actually moved yet
    if end_ms == self._last_history_end_ms:
      logger.info(f"same boundary as last request (end_ms={end_ms}, skipping duplicate request)")
      self.chart_widget.set_loading_more(False)
      return

    self._last_history_end_ms = end_ms
    # Process the fetch into a background thread
    self._candle_history_fetch = _CandleHistoryFetch(self.bybit_client, "BTCUSDT", "3", end_ms)
    self._candle_history_fetch.finished_with_data.connect(self._on_history_loaded)
    self._candle_history_fetch.start()

  def _on_history_loaded(self, older_candles):
    if older_candles:
      self.chart_widget.prepend_data(older_candles)
    else:
      # Nothing delivered from request, free the guard manually
      self.chart_widget.set_loading_more(False)


  def _drain_events(self):
    while not self.bybit_client.events.empty():
      event = self.bybit_client.events.get_nowait()
      if event["type"] == "status" and not event["connected"]:
        self.status_label.setText(f"Fail to Connect to Bybit: {event['message']}")
      
      if event["type"] == "ticker":
        price = event["data"].get("lastPrice")
        if price:
          self.status_label.setText(f"{event["data"]["symbol"]}: {price}")
