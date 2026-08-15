"""The 5 AND 8 logo, recoloured for the dark UI, and the pulse it animates with.

The artwork in media/ is black on opaque white, which is unusable as-is on a
#14171c background. Rather than keep a second exported asset in step with the
first, the pixmap is tinted at runtime: the greyscale of the file becomes the
alpha channel, so the white ground drops out and the mark takes whatever
colour it is asked for.

One widget covers both places a logo animates -- the splash and the wait while
tasks arrive -- so the two never drift apart.
"""

import math
import os
from functools import lru_cache

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from . import theme

LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "media", "5and8_logo.png")


@lru_cache(maxsize=16)
def logo_pixmap(height, colour=theme.TEXT):
    """The mark at `height` px, tinted `colour`, transparent everywhere else.

    Cached: the splash and every loading state ask for the same few sizes, and
    the source file is a 2000px PNG that is not worth decoding twice.
    """
    img = QImage(LOGO_PATH)
    if img.isNull():                      # asset missing: callers get nothing
        return QPixmap()                  # rather than a crash on a farm box

    grey = img.convertToFormat(QImage.Format_Grayscale8)
    grey.invertPixels()                   # black artwork becomes white on black

    out = QImage(img.size(), QImage.Format_ARGB32)
    out.fill(QColor(colour))
    out.setAlphaChannel(grey)             # ink opaque, white ground gone
    return QPixmap.fromImage(out).scaledToHeight(height, Qt.SmoothTransformation)


class LogoPulse(QWidget):
    """The mark breathing in and out: opacity and scale on one sine.

    A spinner says "busy"; this says "busy" in the studio's own mark, which is
    the whole point of putting it on the splash. The timer only runs while the
    widget is visible, so a hidden loading page costs nothing.
    """

    INTERVAL_MS = 40                      # 25fps, plenty for a slow breath

    def __init__(self, height=72, colour=theme.TEXT, parent=None):
        super().__init__(parent)
        self._pixmap = logo_pixmap(height, colour)
        self._phase = 0.0
        self.setMinimumSize(QSize(self._pixmap.width() or height, height))

        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._phase += 0.09               # ~2.9s per breath
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return
        wave = (math.sin(self._phase) + 1) / 2        # 0..1
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(0.40 + 0.60 * wave)
        scale = 0.92 + 0.08 * wave
        w = self._pixmap.width() * scale
        h = self._pixmap.height() * scale
        p.drawPixmap(int((self.width() - w) / 2), int((self.height() - h) / 2),
                     int(w), int(h), self._pixmap)


class LoadingPage(QWidget):
    """The pulsing mark with a line of text, for a QStackedWidget page."""

    def __init__(self, message="Loading...", height=64, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addStretch()

        self.logo = LogoPulse(height)
        lay.addWidget(self.logo, alignment=Qt.AlignHCenter)

        self.label = QLabel(message)
        self.label.setObjectName("emptyHint")
        lay.addWidget(self.label, alignment=Qt.AlignHCenter)
        lay.addStretch()

    def set_message(self, text):
        self.label.setText(text)


class Splash(QWidget):
    """Frameless card shown while ShotGrid is contacted and the window builds.

    Not QSplashScreen: that paints a fixed pixmap, and the whole ask here is a
    logo that moves. Fades in on show and out on finish() so the window does
    not appear to snap into place.
    """

    def __init__(self, message="Starting ShotDeck..."):
        super().__init__(None, Qt.FramelessWindowHint | Qt.SplashScreen
                         | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(420, 300)

        self.body = LoadingPage(message, height=120, parent=self)
        self.body.setGeometry(0, 0, self.width(), self.height())
        # The splash is up before any window applies theme.STYLE, and it has to
        # stay transparent over the rounded card painted below.
        self.body.setStyleSheet(
            f"QWidget {{ background: transparent; }}"
            f"QLabel {{ color: {theme.TEXT_FAINT}; font-size: 12px; }}")

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(280)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(theme.BORDER))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1),
                          theme.RADIUS, theme.RADIUS)

    def show(self):
        screen = self.screen() or self.parentWidget()
        if screen is not None:
            self.move(screen.geometry().center() - self.rect().center())
        self.setWindowOpacity(0.0)
        super().show()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def set_message(self, text):
        self.body.set_message(text)

    def finish(self, window=None):
        """Fade out, then close. `window` is raised as the splash goes."""
        if window is not None:
            window.raise_()
            window.activateWindow()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self.close)
        self._fade.start()
