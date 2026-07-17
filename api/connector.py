import queue
import threading

from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket
from loguru import logger
from datetime import datetime, timezone

class ByBitClient:
  def __init__(self, testnet: bool = False):
    self._testnet = testnet
    self._session = HTTP(testnet=testnet)
    self._ws: WebSocket | None = None
    self._symbol: str | None = None
    self._should_run = False
    self._reconnect_delay = 5

    # Thread Safe Queue, WS callback runs by himself and we only stack and return at the time
    self.events: queue.Queue[dict] = queue.Queue()

    
  # REST Connection
  def check_connection(self) -> bool:
    try: 
      self._session.get_tickers(category="linear", symbol="BTCUSDT")
      logger.info(f"ByBit REST connected successfully")
      return True
    except Exception as e:
      logger.error(f"Error on try to connect into ByBit on REST: {e}")
      return False
    
  # REST Get for Symbol Kline Data
  def get_kline_data(self, symbol: str = "BTCUSDT", interval: str = "3"):
    try:
      kline_data = self._session.get_kline(category="linear", symbol=symbol, interval=interval)
      raw_candles = kline_data["result"]["list"]

      # Reverse Candles Data
      candles = [
        (
          datetime.fromtimestamp(float(c[0]) / 1000, tz=timezone.utc), # -> Timestamp
          float(c[1]), # -> Open
          float(c[2]), # -> High
          float(c[3]), # -> Low
          float(c[4]) # -> Close
        )
        for c in reversed(raw_candles)
      ]

      logger.info(f"Kline Data Successfully Fetched. Symbol: {symbol}")
      return candles
    except Exception as e:
      logger.error(f"Error on try to fetch kline data from symbol {symbol}; Error: {e}")
      return None
    

  # Init Ticker Stream WS
  def start_ticker_strem(self, symbol: str = "BTCUSDT"):
    self._symbol = symbol
    self._should_run = True
    self._connect_ws()

  # Stop All WS Proccess
  def ws_stop(self):
    self._should_run = False
    if self._ws:
      self._ws.exit()
      self._ws = None

  # WS Message Callback
  def _on_message(self, message: dict):
    data = message.get("data", {})
    if data:
      self.events.put({"type": "ticker", "data": data})

  # Method to force reconnection
  def _schedule_reconnect(self):
    if not self._should_run:
      return
    delay = self._reconnect_delay
    logger.warning(f"Reconnect to WS in {delay} seconds")
    threading.Timer(delay, self._connect_ws).start()
    self._reconnect_delay = min(self._reconnect_delay * 2,60)

  # Websocket Connection
  def _connect_ws(self):
    try:
      self._ws = WebSocket(channel_type="linear", testnet=self._testnet, ping_interval=20, ping_timeout=10, retries=10, restart_on_error=True)
      self._ws.ticker_stream(symbol=self._symbol, callback=self._on_message)
      self._reconnect_delay = 5
      self.events.put({"type": "status", "connected": True, "message": "Connected" })
      logger.info(f"WS Connected - {self._symbol}")
    except Exception as e:
      logger.error(f"Error on try to Connect on WS: {e}")
      self.events.put({"type": "status", "connected": False, "message": str(e) })
      self._schedule_reconnect()

