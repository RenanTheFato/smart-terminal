from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QPicture, QPainter
from PySide6.QtCore import QRectF, Qt, Signal
from loguru import logger
import time
import pyqtgraph as pg

class _CandlestickItem(pg.GraphicsObject):
  def __init__(self, data):
    super().__init__()
    self._data = data
    self._picture = QPicture()
    self._generate_picture()

  def _generate_picture(self):
    painter = QPainter(self._picture)
    width = 0.3

    for i, o, h, l, c in self._data:
      color = pg.mkColor("#2ecc71") if c >= o else pg.mkColor("#e74c3c")
      painter.setPen(pg.mkPen(color))
      painter.setBrush(pg.mkBrush(color))

      # Candle Wick
      painter.drawLine(pg.QtCore.QPointF(i, l), pg.QtCore.QPointF(i, h))
      # Candle Body
      painter.drawRect(QRectF(i - width, o, width * 2, c - o))

    painter.end()
  
  def paint(self, painter, *args):
    painter.drawPicture(0, 0, self._picture)

  def boundingRect(self):
    return QRectF(self._picture.boundingRect())
  
class _DateAxisItem(pg.AxisItem):
  # Format each tick as real datetime
  def __init__(self, timestamps: list, *args, **kwargs ):
    super().__init__(*args, **kwargs)
    self._timestamps = timestamps

  # Must be named EXACTLY "tickStrings" (camelCase) — pyqtgraph calls
  # this specific method internally to build the axis labels. A typo
  # here doesn't raise any error, it just silently falls back to the
  # default numeric labels (0, 20, 40...), which is what was happening.
  def tickStrings(self, values, scale, spacing):
    strings = []
    for v in values:
      index = int(round(v))
      if 0 <= index < len(self._timestamps):
        dt = self._timestamps[index]
        strings.append(dt.strftime("%m/%d %H:%M"))
      else:
        strings.append("")
    return strings
  
class _PriceAxisItem(pg.AxisItem):
  # Put price scale to right 
  # If hold left-click the Y axis will rescales

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.acceptHoverEvents(True)

  # Visual change from standard Qt
  def hoverEnterEvent(self, event):
    self.setCursor(Qt.CursorShape.SizeVerCursor)
    super().hover_enter_event(event)

  def hoverLeaveEvent(self, event):
    self.unsetCursor()
    super().hoverLeaveEvent(event)

  def mouseDragEvent(self, event):
    view = self.linkedView()
    if view is None or event.button() != Qt.MouseButton.LeftButton:
      return super().mouseDragEvent(event)
    
    event.accept()
  
    # Vertical delta from drag start to frame finish
    dif = event.screenPos() = event.lastScreenPos()
    scale = 1.004 ** dif.y()

    # Set anchor to the most recent candle
    anchor = view.mapSceneToView(event.buttonDownScenePos())
    view.scaleBy(y=scale, center=anchor)

class _ChartViewBox(pg.ViewBox):
  """Same as pyqtgraph's default ViewBox, but the mouse wheel only
  zooms the X (time) axis, it never touches the Y (price) range,
  and always anchors the zoom to the right edge of the current view
  (the most recent candle), not to the mouse cursor.

  This matches TradingView: "now" always stays pinned at the same
  screen position, and zooming out only reveals more history to the
  left. Anchoring at the cursor instead (pyqtgraph's default, and our
  first attempt) makes the chart drift sideways whenever the cursor
  isn't exactly over the rightmost candle.

  The max-zoom-out cap is enforced here manually (clamping the target
  width before calling scaleBy), instead of via setLimits(maxXRange=).
  setLimits() clips the range after the fact using pyqtgraph's own
  recentering logic, which doesn't respect our right-edge anchor —
  that mismatch was what made the newest candle drift off-screen
  right as the zoom-out limit was reached."""

  MAX_ZOOM_OUT_RANGE = 1500

  def wheelEvent(self, ev, axis=None):
    s = 1.02 ** (ev.delta() * self.state["wheelScaleFactor"])

    x_range, y_range = self.viewRange()
    current_width = x_range[1] - x_range[0]
    target_width = current_width * s

    #Clamp before applying
    clamped_width = min(target_width, self.MAX_ZOOM_OUT_RANGE)
    effective_s = clamped_width / current_width

    anchor = pg.Point(x_range[1], (y_range[0] + y_range[1]) / 2)

    self._resetTarget()
    # Price scale untouched when y=None
    self.scaleBy(x=effective_s, y=None, center=anchor)
    ev.accept()
    self.sigRangeChangedManually.emit(self.state["mouseEnabled"])

class _PlotItemAutoBtnRight(pg.PlotItem):
  # Plot auto adjust button ('A') anchored to bottom right in Y scale (price)

  def resizeEvent(self, ev):
    super().resizeEvent(ev)
    if self.autoBtn is None:
      return
    
    btn_rect = self.mapRectFromItem(self.autoBtn, self.autoBtn.boundingRect())
    x = self.size().width() - btn_rect.width()
    y = self.size().height() - btn_rect.height()
    self.autoBtn.setPos(x, y)
  
class CandlestickChartWidget(QWidget):
  # Emit when the scroll close to oldest loaded candle
  # Requiring more data to fill the chart

  needs_more_history = Signal()

  def __init__(self):
    super().__init__()

    self._timestamps: list =[]
    # Candle Data (date, o, h, l, c)
    self._candles: list[tuple] = []
    # Set state for loading
    self._loading_more = False
    # Set timeout/cooldown
    self._last_request_time = 0.0

    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0 ,0)

    # Set chart properties manually
    date_axis = _DateAxisItem(self._timestamps, orientation="bottom")
    price_axis = _PriceAxisItem(orientation="right")
    view_box = _ChartViewBox()
    plot_item = _PlotItemAutoBtnRight(
      viewBox=view_box,
      axisItems={"bottom": date_axis, "right": price_axis}
    )
    self._plot_widget = pg.PlotWidget(plotItem=plot_item)
    self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
    layout.addWidget(self._plot_widget)


    # Price axis to right side
    plot_item.hideAxis("left")
    plot_item.showAxis("right")
    plot_item.getAxis("right").linkToView(plot_item.getViewBox())

    # Fires on every pan/zoom — used to detect "user is near the left edge of loaded data" and ask for more history.
    view_box.sigXRangeChanged.connect(self._on_x_range_changed)

    self._candlestick_item: _CandlestickItem | None = None

  # Set minimum interval between two load more requests
  MIN_REQUEST_INTERVAL_SECONDS = 1.0

  def _on_x_range_changed(self, x_range):
    if self._loading_more or not self._candles:
      return
    if x_range[0] >= 20:
      return
    
    now = time.monotonic()
    if now - self._last_request_time < self.MIN_REQUEST_INTERVAL_SECONDS:
      return
    
    logger.info("emmiting request: needs_more_history")
    self._loading_more = True
    self._last_request_time = now
    self.needs_more_history.emit()

  def set_loading_more(self, is_loading: bool):
    self._loading_more = is_loading

  def set_data(self, candles: list[tuple], reset_view: bool = True):
    if not candles:
      return
    
    self._candles = candles

    # Keep same list object as _DateAxisItem already holds a reference to it clear + extend in place, never reassign self._timestamps.
    self._timestamps.clear()
    self._timestamps.extend(c[0] for c in candles)

    # Convert (datetime, o, h, l, c) -> (index, o, h, l, c) for the chart
    indexed_candles = [
      (i, o, h, l, c) for i, (_, o, h, l, c) in enumerate(candles)
    ]

    if self._candlestick_item is not None:
      self._plot_widget.removeItem(self._candlestick_item)

    self._candlestick_item = _CandlestickItem(indexed_candles)
    self._plot_widget.addItem(self._candlestick_item)

    if reset_view:
      self.focus_on_latest()

    # Force axis to redraw labels with the new timestamps
    self._plot_widget.getAxis("bottom").update()

  def focus_on_latest(self, visible_candles: int = 100):
    # Frame the view on most recent candles
    if not self._candles:
      return
    
    last_index = len(self._candles) - 1
    # Small right margin so the last candle isn't glued to the edge
    x_max = last_index + 5
    x_min = max(-5, x_max - visible_candles)

    window = self._candles[max(0, len(self._candles) - visible_candles):]
    lows = [c[3] for c in window]
    highs = [c[2] for c in window]
    y_min, y_max = min(lows), max(highs)
    # Prevent zero padding
    padding = (y_max - y_min) * 0.1 or 1

    self._plot_widget.getPlotItem().getViewBox().setRange(
      xRange=(x_min, x_max),
      yRange=(y_min - padding, y_max + padding),
      padding=0
    )

  def oldest_timestamp(self):
    """Datetime of the oldest candle currently loaded. Feed this (minus
    1ms) into BybitClient.get_kline_data(end_time_ms=...) to page
    backwards for more history."""
    return self._timestamps[0] if self._timestamps else None

  def prepend_data(self, older_candles: list[tuple]):
    # Insert older candles before any other request that already loaded
    if not older_candles or not self._candles:
      return
    
    shift = len(older_candles)
    x_range, _ = self._plot_widget.getPlotItem().getViewBox().viewRange()

    full_candles = older_candles + self._candles
    self.set_data(full_candles, reset_view=False)

    self._plot_widget.getPlotItem().getViewBox().setRange(
      xRange=(x_range[0] + shift, x_range[1] + shift),
      padding=0
    )

    # Release guard to next scroll can make the request
    self._loading_more(False)