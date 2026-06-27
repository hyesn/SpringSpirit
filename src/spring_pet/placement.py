from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication


SNAP_THRESHOLD = 24


@dataclass(frozen=True)
class EdgeSnap:
    horizontal: str = ""
    vertical: str = ""

    @property
    def is_free(self) -> bool:
        return not self.horizontal and not self.vertical


def screen_for_rect(rect: QRect):
    screen = QGuiApplication.screenAt(rect.center())
    return screen or QGuiApplication.primaryScreen()


def clamp_rect_top_left(rect: QRect) -> QPoint:
    screen = screen_for_rect(rect)
    if screen is None:
        return rect.topLeft()
    available = screen.availableGeometry()
    x = min(max(rect.left(), available.left()), available.right() - rect.width() + 1)
    y = min(max(rect.top(), available.top()), available.bottom() - rect.height() + 1)
    return QPoint(x, y)


def detect_edge_snap(rect: QRect, threshold: int = SNAP_THRESHOLD) -> EdgeSnap:
    screen = screen_for_rect(rect)
    if screen is None:
        return EdgeSnap()
    available = screen.availableGeometry()
    left_gap = abs(rect.left() - available.left())
    right_gap = abs(available.right() - rect.right())
    top_gap = abs(rect.top() - available.top())
    bottom_gap = abs(available.bottom() - rect.bottom())

    horizontal = ""
    if min(left_gap, right_gap) <= threshold:
        horizontal = "left" if left_gap <= right_gap else "right"

    vertical = ""
    if min(top_gap, bottom_gap) <= threshold:
        vertical = "top" if top_gap <= bottom_gap else "bottom"
    return EdgeSnap(horizontal, vertical)


def apply_edge_snap(rect: QRect, snap: EdgeSnap) -> QPoint:
    screen = screen_for_rect(rect)
    if screen is None:
        return rect.topLeft()
    available = screen.availableGeometry()
    x = rect.left()
    y = rect.top()
    if snap.horizontal == "left":
        x = available.left()
    elif snap.horizontal == "right":
        x = available.right() - rect.width() + 1
    if snap.vertical == "top":
        y = available.top()
    elif snap.vertical == "bottom":
        y = available.bottom() - rect.height() + 1
    return clamp_rect_top_left(QRect(QPoint(x, y), rect.size()))


def default_bottom_right(width: int, height: int, margin: int = 24) -> QPoint:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QPoint(0, 0)
    available = screen.availableGeometry()
    return QPoint(
        available.right() - width - margin + 1,
        available.bottom() - height - margin + 1,
    )
