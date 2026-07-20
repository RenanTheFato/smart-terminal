from datetime import datetime, timezone
 
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QFont, QPainterPath, QPicture, QPainter
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt, Signal
from loguru import logger
import time
import pyqtgraph as pg

# Space between mark price and the text inside of own axis
AXIS_TEXT_PADDING = 10

# Price formatter handler
def _format_price(value: float) -> str:
  # dot character from cent's, comma separating thousands every 3 digits
  return f"{value:,.2f}"

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
  
class _PriceTagItem(pg.GraphicsObject):
  # Price tag style (same from exchanges terminals)
  def __init__(self):
    super().__init__()
    self.setZValue(1000)
    self._width = 70.0
    self._notch = 10.0
    self._row_height = 16.0
    self._color = pg.mkColor("#2ecc71")
    self._price_text = ""
    self._time_text = ""
    self._path = QPainterPath()
    self._rebuild_path()

  def set_geometry(self, width: float, notch: float = 10.0):
    width = max(width, notch * 2 + 20)
    if abs(width - self._width) < 0.5 and notch == self._notch:
      return
    self._width = width
    self._notch = notch
    self._rebuild_path()

  def set_content(self, price_text: str, time_text: str, color):
    self._price_text = price_text
    self._time_text = time_text
    self._color = pg.mkColor(color)
    self.update()

  def _rebuild_path(self):
    self.prepareGeometryChange()
    w, n, h, r = self._width, self._notch, self._row_height, 3

    path = QPainterPath()
    path.moveTo(0, 0)
    path.lineTo(n, -h)
    path.lineTo(w - r, -h)
    path.quadTo(w, -h, w, -h + r)
    path.lineTo(w, h - r)
    path.quadTo(w, h, w - r, h)
    path.lineTo(n, h)
    path.closeSubpath()
    self._path = path

  def boundingRect(self):
    return self._path.boundingRect().adjusted(-1, -1, 1, 1)
  
  def paint(self, painter, *args):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(pg.mkPen(self._color))
    painter.setBrush(pg.mkBrush(self._color))
    painter.drawPath(self._path)

    text_x = self._notch + 4
    text_width = self._width - text_x

    painter.setPen(pg.mkPen("k"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(14)
    painter.setFont(font)
    painter.drawText(
      QRectF(text_x, -self._row_height, text_width, self._row_height),
      Qt.AlignmentFlag.AlignCenter, self._price_text
    )
  
    font.setBold(False)
    font.setPixelSize(14)
    painter.setFont(font)
    painter.drawText(
      QRectF(text_x, 0, text_width, self._row_height),
      Qt.AlignmentFlag.AlignCenter, self._time_text
    )
  
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
    self.setAcceptHoverEvents(True)

  # Visual change from standard Qt
  def tickStrings(self, values, scale, spacing):
    return[_format_price(v) for v in values]
  def generateDrawSpecs(self, p):
    specs = super().generateDrawSpecs(p)
    if specs is None:
      return specs
    axisSpec, tickSpecs, textSpecs = specs

    full_width = self.size().width()
    centered_specs = [
      (
        QRectF(0, rect.y(), full_width, rect.height()),
        (flags & ~Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignHCenter,
         text,
      )
      for rect, flags, text in textSpecs
    ]
    return axisSpec, tickSpecs, centered_specs

  def hoverEnterEvent(self, event):
    self.setCursor(Qt.CursorShape.SizeVerCursor)
    super().hoverEnterEvent(event)

  def hoverLeaveEvent(self, event):
    self.unsetCursor()
    super().hoverLeaveEvent(event)

  def mouseDragEvent(self, event):
    view = self.linkedView()
    if view is None or event.button() != Qt.MouseButton.LeftButton:
      return super().mouseDragEvent(event)
    
    event.accept()
  
    # Vertical delta from drag start to frame finish
    dif = event.screenPos() - event.lastScreenPos()
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
    self._interval_seconds = 0

    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0 ,0)

    # Set chart properties manually
    date_axis = _DateAxisItem(self._timestamps, orientation="bottom")
    price_axis = _PriceAxisItem(orientation="right")

    axis_tick_font = QFont()
    axis_tick_font.setPixelSize(14)
    date_axis.setStyle(tickFont=axis_tick_font, tickTextOffset=AXIS_TEXT_PADDING)
    price_axis.setStyle(tickFont=axis_tick_font, tickTextOffset=AXIS_TEXT_PADDING)

    # Fixed space from each axis
    date_axis.setHeight(46)
    price_axis.setWidth(108)

    # Set higher density for price to show more intervals when scale is resized
    price_axis.setTickDensity(2.2)

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

    view_box.sigRangeChanged.connect(self._update_price_marker)

    self._candlestick_item: _CandlestickItem | None = None
    self._live_item: _CandlestickItem | None = None

    self._price_line = pg.InfiniteLine(
      angle=0, movable=False,
      pen=pg.mkPen("#f0b90b", width=1, style=Qt.PenStyle.DashLine)
    )
    self._price_line.setZValue(100)
    self._plot_widget.addItem(self._price_line, ignoreBounds=True)

    # Price tag added directly into the scene
    self._price_tag = _PriceTagItem()
    self._plot_widget.scene().addItem(self._price_tag)

    # Smooth price change transition
    self._display_price: float | None = None
    self._tag_color = "#2ecc71"
    self._time_text = ""

    self._price_anim = QVariantAnimation(self)
    self._price_anim.setDuration(220)
    self._price_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    self._price_anim.valueChanged.connect(self._on_price_anim_value)

    self._countdown_timer = QTimer()
    self._countdown_timer.timeout.connect(self._update_price_marker)
    self._countdown_timer.start(1000)

  def set_interval(self, interval: str):
    # Manual override (optional), he act like as fallback
    unit_seconds = {"1": 60, "3": 180, "5": 300, "15": 900, "30": 1800, "60": 3600, "120": 7200, "240": 14400, "360": 21600, "720": 43200, "D": 86400, "W": 604800, "M": 2592000}
    self._interval_seconds = unit_seconds.get(interval) or int(interval) * 60

  def _infer_interval_seconds(self):
    # Identify candle time interval smarter
    if len(self._candles) < 2:
      return
    sample = self._candles[-21:] if len(self._candles) > 21 else self._candles
    deltas = [
      (sample[i][0] - sample[i - 1][0]).total_seconds()
      for i in range(1, len(sample))
    ]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
      return
    deltas.sort()
    median = deltas[len(deltas) // 2]

    if median != self._interval_seconds:
      self._interval_seconds = int(median)
  def _update_price_marker(self, *_):
    if not self._candles:
      return
    
    ts, o, h, l, c = self._candles[-1]
    color = "#2ecc71" if c >= o else "#e74c3c"

    remaining = int((ts.timestamp() + self._interval_seconds) - datetime.now(timezone.utc).timestamp())
    remaining = max(remaining, 0)
    mm, ss = divmod(remaining, 60)
    self._time_text = f"{mm:02d}:{ss:02d}"

    self._animate_price_to(c, color)
    self._reposition_price_tag()

  def _set_price_visuals(self, price: float, color):
    self._price_line.setPos(price)
    self._price_line.setPen(pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine))
    self._price_tag.set_content(_format_price(price), self._time_text, color)
  
  def _animate_price_to(self, target_price: float, color):
    self._tag_color = color

    if self._display_price is None:
      # First paint
      self._display_price = target_price
      self._set_price_visuals(target_price, color)
      return
    
    if target_price == self._display_price:
      # Price not changed, only countdown will update
      self._set_price_visuals(self._display_price, color)
      return
    
    self._price_anim.stop()
    self._price_anim.setStartValue(self._display_price)
    self._price_anim.setEndValue(target_price)
    self._price_anim.start()

  def _on_price_anim_value(self, value):
    self._display_price = float(value)
    self._set_price_visuals(self._display_price, self._tag_color)
    self._reposition_price_tag()

  def _reposition_price_tag(self):
    if self._display_price is None or not self._candles:
      return
    
    view_box = self._plot_widget.getPlotItem().getViewBox()
    axis = self._plot_widget.getPlotItem().getAxis("right")

    tip_x = view_box.sceneBoundingRect().right()
    tag_width = max(axis.width(), 60)
    self._price_tag.set_geometry(tag_width)

    scene_pos = view_box.mapViewToScene(QPointF(0, self._display_price))
    self._price_tag.setPos(tip_x, scene_pos.y())

  def resizeEvent(self, event):
    super().resizeEvent(event)
    self._reposition_price_tag()

  # Set minimum interval between two load more requests
  MIN_REQUEST_INTERVAL_SECONDS = 1.0

  def _on_x_range_changed(self, view_box, x_range):
    if self._loading_more or not self._candles:
      return
    if x_range[0] >= 20:
      return
    
    now = time.monotonic()
    if now - self._last_request_time < self.MIN_REQUEST_INTERVAL_SECONDS:
      return
    
    logger.info("emitting request: needs_more_history")
    self._loading_more = True
    self._last_request_time = now
    self.needs_more_history.emit()

  def set_loading_more(self, is_loading: bool):
    self._loading_more = is_loading

  def _rebuild_candlestick_item(self):
    if len(self._candles) <= 1:
      indexed = []
    else:
      indexed = [
        (i, o, h, l, c) for i, (_, o, h, l, c) in enumerate(self._candles[:-1])
      ]

    if self._candlestick_item is not None:
      self._plot_widget.removeItem(self._candlestick_item)
      self._candlestick_item = None
    
    if indexed:
      self._candlestick_item = _CandlestickItem(indexed)
      self._plot_widget.addItem(self._candlestick_item)

  def _rebuild_live_item(self):
    # Only the last candle, call on every tick
    if not self._candles:
      return
    
    last_index = len(self._candles) - 1
    _, o, h, l, c = self._candles[-1]

    if self._live_item is not None:
      self._plot_widget.removeItem(self._live_item)

    self._live_item = _CandlestickItem([(last_index, o, h, l, c)])
    self._plot_widget.addItem(self._live_item)

  def set_data(self, candles: list[tuple], reset_view: bool = True):
    if not candles:
      return
    
    self._candles = candles

    # Keep same list object as _DateAxisItem already holds a reference to it clear + extend in place, never reassign self._timestamps.
    self._timestamps.clear()
    self._timestamps.extend(c[0] for c in candles)

    # Recalculate interval based on most recent data
    # Cover the initializing and the timeframe change
    self._infer_interval_seconds()

    self._rebuild_candlestick_item()
    self._rebuild_live_item()
    # Force axis to redraw labels with the new timestamps
    self._plot_widget.getAxis("bottom").update()

    if reset_view:
      self.focus_on_latest()
    
    self._update_price_marker()

  def update_realtime_candle(self, candle: tuple):
    if not self._candles:
      return
    
    ts = candle[0]
    last_ts = self._candles[-1][0]

    if ts == last_ts:
      self._candles[-1] = candle
      self._rebuild_live_item()
    elif ts > last_ts:
      delta = (ts - last_ts).total_seconds()
      if self._interval_seconds and delta < self._interval_seconds * 0.5:
        logger.error(f"Candle with unexpected delta {delta} ignored")
        return
      # New candle opened, the last live candle now belogns to history
      self._candles.append(candle)
      self._timestamps.append(ts)
      self._infer_interval_seconds()
      self._rebuild_candlestick_item()
      self._rebuild_live_item()
      self._plot_widget.getAxis("bottom").update()
    else:
      return
  
    self._update_price_marker()

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
    self._loading_more = False