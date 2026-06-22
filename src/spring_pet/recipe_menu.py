from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QMenu,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QWidget,
)


RECIPE_MENU_STYLESHEET = """
QMenu#recipeMenu {
    background-color: #FFF7E8;
    color: #4B342F;
    border: 1px solid #E9B0C4;
    border-left: 4px dashed #E6538D;
    border-radius: 14px;
    padding: 8px 6px 8px 10px;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QMenu#recipeMenu::item {
    min-width: 152px;
    min-height: 22px;
    padding: 7px 30px 7px 28px;
    margin: 2px 4px;
    border-radius: 8px;
}
QMenu#recipeMenu::item:selected {
    background-color: #F8D9E5;
    color: #7C294C;
}
QMenu#recipeMenu::item:disabled {
    color: #B49D96;
    background-color: transparent;
}
QMenu#recipeMenu::indicator {
    width: 14px;
    height: 14px;
    left: 8px;
    border: 1px solid #D69AAF;
    border-radius: 7px;
    background-color: #FFFDF7;
}
QMenu#recipeMenu::indicator:checked {
    background-color: #E6538D;
    border: 3px solid #FFF7E8;
}
"""


class RecipeMenuStyle(QProxyStyle):
    """Draw a crisp submenu chevron at any Windows DPI scale."""

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorArrowRight:
            center = option.rect.center()
            radius = 3.5
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(
                QPen(
                    QColor("#B74B73"),
                    1.6,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(center.x() - radius / 2, center.y() - radius),
                        QPointF(center.x() + radius / 2, center.y()),
                        QPointF(center.x() - radius / 2, center.y() + radius),
                    ]
                )
            )
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)


class RecipeMenu(QMenu):
    """A compact recipe-card menu with a split toggle/submenu action."""

    SUBMENU_ARROW_WIDTH = 30

    def __init__(
        self,
        title: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self.setObjectName("recipeMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._recipe_style = RecipeMenuStyle()
        self.setStyle(self._recipe_style)
        self.setStyleSheet(RECIPE_MENU_STYLESHEET)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(92, 54, 48, 76))
        self.setGraphicsEffect(shadow)

    @staticmethod
    def make_toggle_submenu_action(action: QAction, *, available: bool) -> None:
        action.setCheckable(True)
        action.setProperty("springToggleSubmenu", True)
        action.setProperty("springToggleAvailable", available)

    def activate_text_action(self, action: QAction) -> bool:
        """Toggle a split action as if its text area had been clicked."""
        if not action.property("springToggleSubmenu"):
            return False
        if not action.property("springToggleAvailable"):
            return False
        action.toggle()
        self.close()
        return True

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        action = self.actionAt(event.position().toPoint())
        if action is not None and action.property("springToggleSubmenu"):
            geometry = self.actionGeometry(action)
            arrow_left = geometry.right() - self.SUBMENU_ARROW_WIDTH
            if event.position().x() < arrow_left:
                if self.activate_text_action(action):
                    event.accept()
                    return
        super().mouseReleaseEvent(event)
