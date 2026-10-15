"""Bounded camera snapshot decoding. Runs in a worker thread; returns a small QImage (never a full-size frame)."""
from PyQt5.QtCore import QBuffer, QByteArray, QSize
from PyQt5.QtGui import QImageReader

MAX_DIM = (1920, 1080)
MAX_PIXELS = 2073600
TARGET = (640, 360)


def decode_bounded(data, max_pixels=MAX_PIXELS, max_dim=MAX_DIM, target=TARGET):
    """Read the header first; refuse oversized images; decode straight to a scaled-down QImage."""
    if not data:
        raise ValueError('Empty snapshot')
    ba = QByteArray(bytes(data))
    buf = QBuffer(ba)
    buf.open(QBuffer.ReadOnly)
    rd = QImageReader(buf)
    size = rd.size()
    if not size.isValid() or size.width() <= 0 or size.height() <= 0:
        raise ValueError('Unreadable snapshot')
    w, h = size.width(), size.height()
    if w > max_dim[0] or h > max_dim[1] or w * h > max_pixels:
        raise ValueError('Snapshot dimensions too large')
    scale = min(target[0] / w, target[1] / h, 1.0)
    rd.setScaledSize(QSize(max(1, int(w * scale)), max(1, int(h * scale))))
    img = rd.read()
    if img.isNull():
        raise ValueError('Invalid snapshot format')
    return img
