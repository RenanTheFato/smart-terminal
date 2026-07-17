from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QPicture, QPainter
from PySide6.QtCore import QRectF
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
  
class CandlestickChartWidget(QWidget):
  def __init__(self):
    super().__init__()

    self._timestamps: list =[]

    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0 ,0)

    date_axis = _DateAxisItem(self._timestamps, orientation="bottom")
    self._plot_widget = pg.PlotWidget(axisItems={"bottom": date_axis})
    self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
    layout.addWidget(self._plot_widget)

    # Price axis to right side
    plot_item = self._plot_widget.getPlotItem()
    plot_item.hideAxis("left")
    plot_item.showAxis("right")
    plot_item.getAxis("right").linkToView(plot_item.getViewBox())

    self._candlestick_item: _CandlestickItem | None = None
  
  def set_data(self, candles: list[tuple]):
    if not candles:
      return

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
    self._plot_widget.autoRange()

    # view_box = self._plot_widget.getPlotItem().getViewBox()
    # view_box.setLimits(xMin=5, xMax=len(candles) + 5, minXRange=10, maxXRange=len(candles) + 10)

    # Force axis to redraw labels with the new timestamps
    self._plot_widget.getAxis("bottom").update()