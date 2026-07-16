from pybit.unified_trading import HTTP
from loguru import logger

class ByBitClient:
  def __init__(self, testnet: bool = False):
    self._session = HTTP(testnet=testnet)
    
  def check_connection(self) -> str:
    try: 
      self._session.get_tickers(category="linear", symbol="BTCUSDT")
      logger.info(f"ByBit connected successfully")
      return "Success"
    except Exception as e:
      logger.error(f"Error on try to connect into ByBit server: {e}")
      return "Fail"