# -*- coding: utf-8 -*-
"""左侧浏览栏：两个标签页 ——「当前图片」与「最近」。

- 当前图片：仅显示当前打开的这张图片（单张缩略图）。
- 最近：最近打开过的图片列表，点击某张即替换为当前图片。
"""
from __future__ import annotations

import os

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QLabel, QListWidget, QListWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from app.canvas import pil_to_qimage

_THUMB_SIZE = 128
_GRID_W = _THUMB_SIZE + 16
_GRID_H = _THUMB_SIZE + 32

# 跨标签页共享的缩略图缓存：重复填充时直接复用，避免缩略图闪烁/重复加载
_THUMB_CACHE: dict[str, QIcon] = {}


def _load_thumbnail(path: str) -> QImage | None:
    """在工作线程中加载缩略图；返回统一尺寸的方形 QImage（线程安全）。"""
    try:
        img = Image.open(path)
        img.load()
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA")
        # 中心裁切为正方形并缩放，避免上下/左右出现留白边框
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_THUMB_SIZE, _THUMB_SIZE), Image.Resampling.LANCZOS)
        return pil_to_qimage(img)
    except Exception:  # noqa: BLE001
        return None


class _Signals(QObject):
    thumb = Signal(str, QImage)


class _ThumbTask(QRunnable):
    def __init__(self, path: str, signals: _Signals):
        super().__init__()
        self.path = path
        self.signals = signals

    def run(self):
        qimg = _load_thumbnail(self.path)
        if qimg is not None:
            try:
                self.signals.thumb.emit(self.path, qimg)
            except RuntimeError:
                # 应用退出时信号源可能已被销毁，忽略即可
                pass


class _ThumbList(QListWidget):
    """带统一网格与后台缩略图加载的图片列表。"""

    activateImage = Signal(str)

    def __init__(self, pool: QThreadPool, signals: _Signals, parent=None):
        super().__init__(parent)
        self._pool = pool
        self._signals = signals
        self._thumb_map: dict[str, QListWidgetItem] = {}
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(_THUMB_SIZE, _THUMB_SIZE))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSpacing(4)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(_GRID_W, _GRID_H))
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.itemClicked.connect(self._on_item_clicked)

    def populate(self, files: list[str]):
        self.clear()
        self._thumb_map = {}
        for path in files:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            icon = _THUMB_CACHE.get(path)
            if icon is not None:
                item.setIcon(icon)
            self.addItem(item)
            self._thumb_map[path] = item
            if icon is None:
                self._pool.start(_ThumbTask(path, self._signals))

    def set_thumbnail(self, path: str, qimg: QImage):
        icon = QIcon(QPixmap.fromImage(qimg))
        _THUMB_CACHE[path] = icon
        item = self._thumb_map.get(path)
        if item is not None:
            item.setIcon(icon)

    def select_path(self, path: str | None):
        item = self._thumb_map.get(path)
        if item is not None:
            self.setCurrentItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self.activateImage.emit(path)


class Sidebar(QWidget):
    openRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(190)

        self._pool = QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.thumb.connect(self._on_thumb)

        self._current_path: str | None = None

        self._current_tab = _ThumbList(self._pool, self._signals)
        self._recent_tab = _ThumbList(self._pool, self._signals)
        self._current_tab.activateImage.connect(self.openRequested)
        self._recent_tab.activateImage.connect(self.openRequested)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._current_tab, "当前图片")
        self.tabs.addTab(self._recent_tab, "最近")

        self._path_label = QLabel("未打开文件")
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("color:#888; font-size:11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self._path_label)

    def set_current(self, path: str | None):
        """「当前图片」标签页：只显示当前这一张。"""
        self._current_path = path
        self._current_tab.populate([path] if path else [])
        self._recent_tab.select_path(path)
        self._path_label.setText(path or "未打开文件")

    def set_recent(self, files: list[str]):
        """「最近」标签页：显示最近打开过的图片，并高亮当前图片。"""
        self._recent_tab.populate(files)
        self._recent_tab.select_path(self._current_path)

    def _on_thumb(self, path: str, qimg: QImage):
        self._current_tab.set_thumbnail(path, qimg)
        self._recent_tab.set_thumbnail(path, qimg)
