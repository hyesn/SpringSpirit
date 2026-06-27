from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QMenu,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QStyleOptionMenuItem,
    QWidget,
)

from . import ui_theme as theme


def recipe_font() -> QFont:
    installed = set(QFontDatabase.families())
    family = next(
        (
            name
            for name in (
                "YouYuan",
                "幼圆",
                "华文新魏",
                "FZShuTi",
                "方正舒体",
                "Microsoft YaHei UI",
            )
            if name in installed
        ),
        "Microsoft YaHei UI",
    )
    font = QFont(family)
    font.setPointSizeF(10.0)
    font.setWeight(QFont.Weight.Medium)
    return font


class RecipeMenuStyle(QProxyStyle):
    ITEM_HEIGHT = 28
    TEXT_LEFT = 27
    RIGHT_SPACE = 21
    MIN_WIDTH = 116

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        if metric == QStyle.PixelMetric.PM_MenuHMargin:
            return 7
        if metric == QStyle.PixelMetric.PM_MenuVMargin:
            return 4
        if metric == QStyle.PixelMetric.PM_MenuPanelWidth:
            return 0
        return super().pixelMetric(metric, option, widget)

    def sizeFromContents(
        self,
        content_type: QStyle.ContentsType,
        option: QStyleOption,
        size: QSize,
        widget: QWidget | None = None,
    ) -> QSize:
        if (
            content_type == QStyle.ContentsType.CT_MenuItem
            and isinstance(option, QStyleOptionMenuItem)
        ):
            if option.menuItemType == QStyleOptionMenuItem.MenuItemType.Separator:
                return QSize(8, 5)
            text_width = option.fontMetrics.horizontalAdvance(option.text)
            width = max(
                self.MIN_WIDTH,
                text_width + self.TEXT_LEFT + self.RIGHT_SPACE + 10,
            )
            return QSize(width, self.ITEM_HEIGHT)
        return super().sizeFromContents(content_type, option, size, widget)

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element != QStyle.PrimitiveElement.PE_PanelMenu:
            super().drawPrimitive(element, option, painter, widget)
            return
        rect = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(theme.PINK_BORDER), 1.0))
        painter.setBrush(QColor(theme.CREAM_PAPER))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(
            QPen(
                QColor(theme.LABEL_PINK),
                2.5,
                Qt.PenStyle.DashLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(
            QPointF(rect.left() + 2.2, rect.top() + 7),
            QPointF(rect.left() + 2.2, rect.bottom() - 7),
        )
        painter.restore()

    def drawControl(
        self,
        element: QStyle.ControlElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if (
            element != QStyle.ControlElement.CE_MenuItem
            or not isinstance(option, QStyleOptionMenuItem)
        ):
            super().drawControl(element, option, painter, widget)
            return
        if option.menuItemType == QStyleOptionMenuItem.MenuItemType.Separator:
            return

        rect = option.rect.adjusted(2, 1, -2, -1)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.SOFT_PINK))
            painter.drawRoundedRect(QRectF(rect), 7, 7)

        if option.checkType != QStyleOptionMenuItem.CheckType.NotCheckable:
            self._draw_indicator(painter, rect, option.checked, enabled)

        text_color = (
            QColor(theme.MUTED_COCOA)
            if not enabled
            else QColor(theme.COCOA_DEEP)
            if selected
            else QColor(theme.COCOA_TEXT)
        )
        painter.setPen(text_color)
        painter.setFont(option.font)
        text_rect = rect.adjusted(self.TEXT_LEFT, 0, -self.RIGHT_SPACE, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.text,
        )

        if option.menuItemType == QStyleOptionMenuItem.MenuItemType.SubMenu:
            self._draw_arrow(painter, rect, enabled)
        painter.restore()

    @staticmethod
    def _draw_indicator(
        painter: QPainter,
        rect,
        checked: bool,
        enabled: bool,
    ) -> None:
        center = QPointF(rect.left() + 11.5, rect.center().y())
        color = QColor(theme.LABEL_PINK if enabled else "#CBB7B2")
        painter.setPen(QPen(color, 1.1))
        painter.setBrush(color if checked else QColor(theme.PAPER_LIGHT))
        painter.drawEllipse(center, 5.1, 5.1)
        if checked:
            painter.setPen(
                QPen(
                    QColor(theme.CREAM_PAPER),
                    1.25,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(center.x() - 2.4, center.y()),
                        QPointF(center.x() - 0.5, center.y() + 2.0),
                        QPointF(center.x() + 2.8, center.y() - 2.2),
                    ]
                )
            )

    @staticmethod
    def _draw_arrow(painter: QPainter, rect, enabled: bool) -> None:
        center = QPointF(rect.right() - 10.5, rect.center().y())
        painter.setPen(
            QPen(
                QColor(theme.LABEL_PINK_DARK if enabled else "#CBB7B2"),
                1.5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(center.x() - 1.7, center.y() - 3.2),
                    QPointF(center.x() + 1.7, center.y()),
                    QPointF(center.x() - 1.7, center.y() + 3.2),
                ]
            )
        )


class RecipeMenu(QMenu):
    SUBMENU_ARROW_WIDTH = 23

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
        self.setFont(recipe_font())
        self.setAutoFillBackground(False)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(92, 54, 48, 64))
        self.setGraphicsEffect(shadow)

    @staticmethod
    def make_toggle_submenu_action(action: QAction, *, available: bool) -> None:
        action.setCheckable(True)
        action.setProperty("springToggleSubmenu", True)
        action.setProperty("springToggleAvailable", available)

    def activate_text_action(self, action: QAction) -> bool:
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
