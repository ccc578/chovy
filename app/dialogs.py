# -*- coding: utf-8 -*-
"""导出 / 保存相关对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QSlider, QVBoxLayout)


class ExportDialog(QDialog):
    """选择导出格式与质量。"""

    def __init__(self, parent=None, allow_overwrite=False):
        super().__init__(parent)
        self.setWindowTitle("导出图片")
        self.format = "PNG"
        self.quality = 90

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("格式"))
        self._fmt = QComboBox()
        self._fmt.addItems(["PNG", "JPG", "WebP"])
        row.addWidget(self._fmt)
        layout.addLayout(row)

        qrow = QHBoxLayout()
        qrow.addWidget(QLabel("质量"))
        self._q = QSlider(Qt.Orientation.Horizontal)
        self._q.setRange(1, 100)
        self._q.setValue(90)
        self._qval = QLabel("90")
        self._q.valueChanged.connect(lambda v: self._qval.setText(str(v)))
        qrow.addWidget(self._q, 1)
        qrow.addWidget(self._qval)
        layout.addLayout(qrow)

        self._fmt.currentTextChanged.connect(self._fmt_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fmt_changed("PNG")

    def _fmt_changed(self, text):
        self._q.setEnabled(text != "PNG")

    def accept(self):
        self.format = self._fmt.currentText()
        self.quality = self._q.value()
        super().accept()
