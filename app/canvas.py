# -*- coding: utf-8 -*-
"""图像显示与交互画布：缩放/平移、裁剪、绘制、可拖拽覆盖层（水印/文字）。"""
from __future__ import annotations

import enum

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QImage, QPainter, QPen)
from PySide6.QtWidgets import QWidget


def pil_to_qimage(img: Image.Image) -> QImage:
    """PIL -> QImage（RGBA 保留透明，否则 RGB）。"""
    if img.mode == "RGBA":
        data = img.tobytes("raw", "RGBA")
        q = QImage(data, img.width, img.height, img.width * 4,
                   QImage.Format_RGBA8888)
    else:
        rgb = img.convert("RGB")
        data = rgb.tobytes("raw", "RGB")
        q = QImage(data, rgb.width, rgb.height, rgb.width * 3,
                   QImage.Format_RGB888)
    return q.copy()


class Mode(enum.IntEnum):
    VIEW = 0
    CROP = 1
    DRAW = 2
    OVERLAY_MOVE = 3


class ImageCanvas(QWidget):
    cropCommitted = Signal(tuple)      # (l, t, r, b) 图像坐标
    drawCommitted = Signal(list)       # 图元列表
    overlayMoved = Signal(float, float)  # 覆盖层左上角图像坐标

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 200)

        self._image: QImage | None = None
        self._original: QImage | None = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._mode = Mode.VIEW
        self._compare = False

        # 裁剪
        self._crop_ratio: float | None = None
        self._crop_start: QPointF | None = None
        self._crop_rect: QRectF | None = None

        # 绘制
        self._draw_tool: dict = {}
        self._draw_start: QPointF | None = None
        self._draw_cur: dict | None = None

        # 覆盖层（水印/文字）
        self._overlay_box: QRectF | None = None
        self._overlay_pixmap = None
        self._overlay_drag_start: QPointF | None = None
        self._overlay_start_pos: QPointF | None = None

    # ------------------------------------------------------------------
    # 图像设置
    # ------------------------------------------------------------------
    def set_image(self, pil_image: Image.Image | None):
        self._image = pil_to_qimage(pil_image) if pil_image is not None else None
        self.update()

    def set_original(self, pil_image: Image.Image | None):
        self._original = pil_to_qimage(pil_image) if pil_image is not None else None
        self.update()

    def set_compare(self, on: bool):
        self._compare = on
        self.update()

    def has_image(self) -> bool:
        return self._image is not None

    # ------------------------------------------------------------------
    # 缩放 / 平移
    # ------------------------------------------------------------------
    def _image_rect(self) -> QRectF:
        if self._image is None:
            return QRectF(0, 0, 0, 0)
        return QRectF(self._offset.x(), self._offset.y(),
                      self._image.width() * self._scale,
                      self._image.height() * self._scale)

    def fit(self):
        if self._image is None:
            return
        w = self.width()
        h = self.height()
        self._scale = min(w / self._image.width(), h / self._image.height())
        self._scale = max(1e-3, self._scale)
        self._center()

    def _center(self):
        if self._image is None:
            return
        iw = self._image.width() * self._scale
        ih = self._image.height() * self._scale
        self._offset = QPointF((self.width() - iw) / 2, (self.height() - ih) / 2)
        self.update()

    def zoom(self, factor: float, anchor: QPointF | None = None):
        if self._image is None:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        old_scale = self._scale
        self._scale = max(1e-3, min(64.0, self._scale * factor))
        k = self._scale / old_scale
        self._offset = QPointF(
            anchor.x() - (anchor.x() - self._offset.x()) * k,
            anchor.y() - (anchor.y() - self._offset.y()) * k,
        )
        self.update()

    def reset_view(self):
        self._scale = 1.0
        self._center()

    # ------------------------------------------------------------------
    # 坐标换算
    # ------------------------------------------------------------------
    def widget_to_image(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self._offset.x()) / self._scale,
                       (p.y() - self._offset.y()) / self._scale)

    def image_to_widget(self, p: QPointF) -> QPointF:
        return QPointF(p.x() * self._scale + self._offset.x(),
                       p.y() * self._scale + self._offset.y())

    def _clamp_to_image(self, p: QPointF) -> QPointF:
        if self._image is None:
            return p
        return QPointF(max(0.0, min(p.x(), self._image.width())),
                       max(0.0, min(p.y(), self._image.height())))

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------
    def set_mode(self, mode: Mode):
        self._mode = mode
        self._clear_interaction()
        self.update()

    def get_mode(self) -> Mode:
        return self._mode

    def _clear_interaction(self):
        self._crop_start = None
        self._crop_rect = None
        self._draw_start = None
        self._draw_cur = None
        self._overlay_drag_start = None

    def start_crop(self, ratio: float | None = None):
        self._crop_ratio = ratio
        self._crop_rect = None
        self._crop_start = None
        self.set_mode(Mode.CROP)

    def start_draw(self, tool: dict):
        self._draw_tool = tool
        self.set_mode(Mode.DRAW)

    def update_draw_tool(self, key, value):
        self._draw_tool[key] = value
        self.update()

    def set_overlay(self, box: QRectF | None, pixmap=None):
        """设置可拖拽覆盖层（图像坐标 + 预览图）。"""
        self._overlay_box = box
        self._overlay_pixmap = pixmap
        if box is not None:
            self.set_mode(Mode.OVERLAY_MOVE)
        else:
            if self._mode == Mode.OVERLAY_MOVE:
                self.set_mode(Mode.VIEW)

    def cancel_interaction(self):
        self._clear_interaction()
        self.set_mode(Mode.VIEW)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor(35, 38, 42))

        img = self._original if self._compare and self._original is not None \
            else self._image
        if img is not None:
            target = self._image_rect()
            self._draw_checker(painter, target)
            painter.drawImage(target, img)

        if self._compare:
            painter.setPen(QPen(QColor(255, 200, 60), 2))
            painter.drawText(self.rect().adjusted(8, 8, -8, -8),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                             "原图")

        if self._mode == Mode.CROP:
            self._paint_crop(painter)
        elif self._mode == Mode.DRAW:
            self._paint_draw(painter)

        # 覆盖层（水印/文字）始终显示
        if self._overlay_pixmap is not None and self._overlay_box is not None:
            self._paint_overlay(painter)

        painter.end()

    def _draw_checker(self, painter: QPainter, rect: QRectF):
        # 透明背景棋盘格
        cell = 10
        painter.save()
        painter.setClipRect(rect)
        for y in range(int(rect.top()), int(rect.bottom()), cell):
            for x in range(int(rect.left()), int(rect.right()), cell):
                dark = ((x // cell) + (y // cell)) % 2 == 0
                painter.fillRect(QRectF(x, y, cell, cell),
                                 QColor(200, 200, 200) if dark else QColor(240, 240, 240))
        painter.restore()

    def _paint_crop(self, painter: QPainter):
        if self._crop_rect is None:
            return
        rect = self._image_rect()
        r = QRectF(self.image_to_widget(self._crop_rect.topLeft()),
                   self.image_to_widget(self._crop_rect.bottomRight()))
        # 四周变暗
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(rect.left(), rect.top(), rect.width(), r.top() - rect.top()))
        painter.drawRect(QRectF(rect.left(), r.bottom(), rect.width(), rect.bottom() - r.bottom()))
        painter.drawRect(QRectF(rect.left(), r.top(), r.left() - rect.left(), r.height()))
        painter.drawRect(QRectF(r.right(), r.top(), rect.right() - r.right(), r.height()))
        # 裁剪框
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(255, 255, 255), 1.5)
        painter.setPen(pen)
        painter.drawRect(r)
        painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.PenStyle.DashLine))
        painter.drawRect(r)

    def _paint_draw(self, painter: QPainter):
        tool = self._draw_tool.get("tool", "brush")
        color = QColor(*self._draw_tool.get("color", (255, 0, 0)))
        width = int(self._draw_tool.get("width", 4))
        pen = QPen(color, width * self._scale)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        if tool in ("brush", "erase"):
            if self._draw_cur:
                pts = [self.image_to_widget(QPointF(x, y))
                       for x, y in self._draw_cur.get("points", [])]
                if len(pts) == 1:
                    painter.drawPoint(pts[0])
                elif len(pts) > 1:
                    painter.drawPolyline(pts)
        elif tool in ("rect", "ellipse", "line", "arrow"):
            if self._draw_start is not None and self._draw_cur:
                p0 = self.image_to_widget(self._draw_start)
                p1 = self.image_to_widget(self._draw_cur.get("p1", self._draw_start))
                if tool == "rect":
                    painter.drawRect(QRectF(p0, p1))
                elif tool == "ellipse":
                    painter.drawEllipse(QRectF(p0, p1))
                elif tool == "line":
                    painter.drawLine(p0, p1)
                elif tool == "arrow":
                    self._draw_arrow(painter, p0, p1, width * self._scale)

    def _draw_arrow(self, painter, p0, p1, width):
        import math
        painter.drawLine(p0, p1)
        dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        ux, uy = dx / length, dy / length
        head = max(8.0, width * 3)
        ang = math.radians(25)
        for sgn in (1, -1):
            a = math.atan2(uy, ux) + sgn * (math.pi - ang)
            painter.drawLine(p1, QPointF(p1.x() + head * math.cos(a),
                                         p1.y() + head * math.sin(a)))

    def _paint_overlay(self, painter: QPainter):
        if self._overlay_box is None:
            return
        r = QRectF(self.image_to_widget(self._overlay_box.topLeft()),
                   self.image_to_widget(self._overlay_box.bottomRight()))
        if self._overlay_pixmap is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(r, self._overlay_pixmap,
                               QRectF(0, 0, self._overlay_pixmap.width(),
                                      self._overlay_pixmap.height()))
        if self._mode == Mode.OVERLAY_MOVE:
            pen = QPen(QColor(80, 180, 255), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)

    # ------------------------------------------------------------------
    # 鼠标事件
    # ------------------------------------------------------------------
    def wheelEvent(self, event):
        if self._image is None:
            return
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.zoom(factor, QPointF(event.position()))
        event.accept()

    def mousePressEvent(self, event):
        if self._image is None:
            return
        pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = pos
            self._pan_offset = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == Mode.CROP:
                self._crop_start = self._clamp_to_image(self.widget_to_image(pos))
                self._crop_rect = QRectF(self._crop_start, self._crop_start)
            elif self._mode == Mode.DRAW:
                self._draw_start = self._clamp_to_image(self.widget_to_image(pos))
                tool = self._draw_tool.get("tool", "brush")
                if tool in ("brush", "erase"):
                    self._draw_cur = {"points": [(self._draw_start.x(), self._draw_start.y())]}
                else:
                    self._draw_cur = {"p1": self._draw_start}
            elif self._mode == Mode.OVERLAY_MOVE and self._overlay_box is not None:
                self._overlay_drag_start = self.widget_to_image(pos)
                self._overlay_start_pos = QPointF(self._overlay_box.topLeft())
            elif self._mode == Mode.VIEW:
                self._pan_start = pos
                self._pan_offset = QPointF(self._offset)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()

    def mouseMoveEvent(self, event):
        if self._image is None:
            return
        pos = event.position()
        if hasattr(self, "_pan_start") and event.buttons() & Qt.MouseButton.LeftButton and \
                self._mode == Mode.VIEW:
            self._offset = QPointF(
                self._pan_offset.x() + (pos.x() - self._pan_start.x()),
                self._pan_offset.y() + (pos.y() - self._pan_start.y()))
            self.update()
            return
        if hasattr(self, "_pan_start") and event.buttons() & Qt.MouseButton.MiddleButton:
            self._offset = QPointF(
                self._pan_offset.x() + (pos.x() - self._pan_start.x()),
                self._pan_offset.y() + (pos.y() - self._pan_start.y()))
            self.update()
            return

        if self._mode == Mode.CROP and self._crop_start is not None and \
                event.buttons() & Qt.MouseButton.LeftButton:
            cur = self._clamp_to_image(self.widget_to_image(pos))
            self._crop_rect = self._make_ratio_rect(self._crop_start, cur, self._crop_ratio)
            self.update()
        elif self._mode == Mode.DRAW and self._draw_start is not None and \
                event.buttons() & Qt.MouseButton.LeftButton:
            cur = self._clamp_to_image(self.widget_to_image(pos))
            tool = self._draw_tool.get("tool", "brush")
            if tool in ("brush", "erase"):
                self._draw_cur["points"].append((cur.x(), cur.y()))
            else:
                self._draw_cur["p1"] = cur
            self.update()
        elif self._mode == Mode.OVERLAY_MOVE and self._overlay_drag_start is not None and \
                event.buttons() & Qt.MouseButton.LeftButton:
            cur = self.widget_to_image(pos)
            dx = cur.x() - self._overlay_drag_start.x()
            dy = cur.y() - self._overlay_drag_start.y()
            new_x = self._overlay_start_pos.x() + dx
            new_y = self._overlay_start_pos.y() + dy
            self._move_overlay_to(new_x, new_y)
            self.update()

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_pan_start"):
            del self._pan_start
            self.unsetCursor()
        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == Mode.CROP and self._crop_rect is not None:
                r = self._crop_rect.normalized()
                if r.width() >= 2 and r.height() >= 2:
                    box = (r.left(), r.top(), r.right(), r.bottom())
                    self.cropCommitted.emit(box)
                self.set_mode(Mode.VIEW)
            elif self._mode == Mode.DRAW and self._draw_cur is not None:
                prim = self._build_primitive()
                if prim is not None:
                    self.drawCommitted.emit([prim])
                self._draw_cur = None
                self._draw_start = None
            elif self._mode == Mode.OVERLAY_MOVE:
                if self._overlay_box is not None:
                    self.overlayMoved.emit(self._overlay_box.left(),
                                           self._overlay_box.top())
                self._overlay_drag_start = None
        self.update()

    def _make_ratio_rect(self, start: QPointF, cur: QPointF,
                         ratio: float | None) -> QRectF:
        dx = cur.x() - start.x()
        dy = cur.y() - start.y()
        if ratio is not None and ratio > 0:
            # 锁定宽高比（w/h = ratio）
            if abs(dx) >= abs(dy) * ratio:
                dy = abs(dx) / ratio * (1 if dy >= 0 else -1)
            else:
                dx = abs(dy) * ratio * (1 if dx >= 0 else -1)
        # 约束在图像范围内（保持起点不动，按同一比例收缩偏移量以保住宽高比）
        if self._image is not None:
            w = self._image.width()
            h = self._image.height()
            max_dx = (w - start.x()) if dx >= 0 else start.x()
            max_dy = (h - start.y()) if dy >= 0 else start.y()
            sx = min(1.0, max_dx / abs(dx)) if abs(dx) > 1e-6 else 1.0
            sy = min(1.0, max_dy / abs(dy)) if abs(dy) > 1e-6 else 1.0
            s = min(sx, sy)
            dx *= s
            dy *= s
        return QRectF(start, QPointF(start.x() + dx, start.y() + dy))

    def _build_primitive(self):
        tool = self._draw_tool.get("tool", "brush")
        cur = self._draw_cur
        if cur is None:
            return None
        if tool in ("brush", "erase"):
            if not cur.get("points"):
                return None
            return {"type": tool, "points": cur["points"],
                    "color": self._draw_tool.get("color", (255, 0, 0)),
                    "width": int(self._draw_tool.get("width", 4)),
                    "opacity": int(self._draw_tool.get("opacity", 255))}
        p1 = cur.get("p1", self._draw_start)
        if self._draw_start is None:
            return None
        if abs(p1.x() - self._draw_start.x()) < 1 and \
                abs(p1.y() - self._draw_start.y()) < 1:
            return None
        return {"type": tool,
                "p0": (self._draw_start.x(), self._draw_start.y()),
                "p1": (p1.x(), p1.y()),
                "color": self._draw_tool.get("color", (255, 0, 0)),
                "width": int(self._draw_tool.get("width", 4))}

    def _move_overlay_to(self, x: float, y: float):
        if self._overlay_box is None or self._image is None:
            return
        x = max(0.0, min(x, self._image.width() - self._overlay_box.width()))
        y = max(0.0, min(y, self._image.height() - self._overlay_box.height()))
        self._overlay_box.moveTo(x, y)
