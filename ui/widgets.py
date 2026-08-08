import urllib.request

from PySide6.QtCore import (
    Qt, QSize, Signal, QThreadPool, QRunnable, QObject, QRectF,
)
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QLinearGradient, QBrush, QFont, QPainterPath,
)
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy, QWidget,
    QGraphicsDropShadowEffect, QStyledItemDelegate, QStyle,
)

from . import theme

_pool = QThreadPool.globalInstance()

# Thumbnails are fetched once per URL and kept for the life of the process.
# Without this, every grid rebuild re-downloads from ShotGrid.
_thumb_cache = {}


class _ThumbSignals(QObject):
    done = Signal(str, bytes)


class _ThumbJob(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = _ThumbSignals()

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                self.signals.done.emit(self.url, r.read())
        except Exception:
            pass    # a missing thumbnail is not worth bothering anyone about


def rounded(pixmap, size, radius):
    """Scale to fill, centre-crop, and round the corners."""
    scaled = pixmap.scaled(size, Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    scaled = scaled.copy(x, y, size.width(), size.height())

    out = QPixmap(size)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()),
                        radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return out


def placeholder(text, size, radius):
    """Gradient square with initials, for anything without a thumbnail."""
    start, end = theme.tile_colours(text)
    out = QPixmap(size)
    out.fill(Qt.transparent)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, size.width(), size.height())
    gradient.setColorAt(0, QColor(start))
    gradient.setColorAt(1, QColor(end))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()),
                        radius, radius)
    painter.fillPath(path, QBrush(gradient))

    initials = "".join(w[0] for w in str(text).split()[:2]).upper() or "?"
    font = QFont(painter.font())
    font.setPixelSize(int(size.height() * 0.34))
    font.setWeight(QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 200))
    painter.drawText(out.rect(), Qt.AlignCenter, initials)
    painter.end()
    return out


class Tile(QFrame):
    """Project / app card: thumbnail, name, and an optional second line."""

    clicked = Signal()

    def __init__(self, title, image_url=None, subtitle=None,
                 size=QSize(168, 104)):
        super().__init__()
        self.setObjectName("tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(size.width() + 20,
                          size.height() + (68 if subtitle else 52))

        self._title = title
        self._thumb_size = size

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.thumb = QLabel()
        self.thumb.setObjectName("tileThumb")
        self.thumb.setFixedSize(size)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setPixmap(placeholder(title, size, theme.RADIUS_SM))
        lay.addWidget(self.thumb, alignment=Qt.AlignHCenter)

        name = QLabel(title)
        name.setObjectName("tileName")
        name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.addWidget(name)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("tileSub")
            lay.addWidget(sub)

        lay.addStretch()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

        if image_url:
            self._load(image_url)

    def _load(self, url):
        cached = _thumb_cache.get(url)
        if cached is not None:
            self._apply(url, cached)
            return
        job = _ThumbJob(url)
        job.signals.done.connect(self._on_loaded)
        _pool.start(job)

    def _on_loaded(self, url, data):
        _thumb_cache[url] = data
        self._apply(url, data)

    def _apply(self, url, data):
        pm = QPixmap()
        if not pm.loadFromData(data):
            return
        try:
            self.thumb.setPixmap(
                rounded(pm, self._thumb_size, theme.RADIUS_SM))
        except RuntimeError:
            pass    # tile was destroyed while the download was in flight

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Avatar(QLabel):
    """Small circle with the user's initials."""

    def __init__(self, text, diameter=20):
        super().__init__()
        self.setObjectName("avatar")
        self.setFixedSize(diameter, diameter)
        self.setAlignment(Qt.AlignCenter)
        initials = (text or "?").split("@")[0][:2].upper()
        self.setText(initials)


class EmptyState(QWidget):
    """Shown instead of a blank grid or table."""

    def __init__(self, icon, title, hint=""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(6)

        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("emptyIcon")
        icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("emptyTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(title_lbl)

        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setObjectName("emptyHint")
            hint_lbl.setAlignment(Qt.AlignCenter)
            hint_lbl.setWordWrap(True)
            lay.addWidget(hint_lbl)


class StatusPill(QStyledItemDelegate):
    """Draws a task status as a coloured pill instead of a bare short code."""

    def paint(self, painter, option, index):
        code = index.data(Qt.DisplayRole) or ""
        if not code:
            return

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(61, 157, 255, 36))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(theme.SURFACE))

        colour = QColor(theme.status_colour(code))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        font = QFont(option.font)
        font.setPixelSize(11)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)

        text = code.upper()
        width = painter.fontMetrics().horizontalAdvance(text) + 20
        height = 20
        rect = QRectF(option.rect.left() + 12,
                      option.rect.center().y() - height / 2 + 1,
                      width, height)

        bg = QColor(colour)
        bg.setAlpha(38)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, height / 2, height / 2)

        painter.setPen(colour)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(90, 38)


class DueDate(QStyledItemDelegate):
    """Due dates, with overdue ones picked out in red."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        import datetime
        raw = (index.data(Qt.DisplayRole) or "").strip()
        if not raw:
            option.palette.setColor(option.palette.Text,
                                    QColor(theme.TEXT_FAINT))
            return
        try:
            due = datetime.date.fromisoformat(raw)
        except ValueError:
            return
        today = datetime.date.today()
        if due < today:
            option.palette.setColor(option.palette.Text, QColor(theme.ERROR))
        elif (due - today).days <= 2:
            option.palette.setColor(option.palette.Text, QColor(theme.WARN))


STYLE = theme.STYLE
