# -*- coding: utf-8 -*-
"""撤销 / 重做历史管理（最多 20 步）。

快照以 PNG 字节保存，无损、避免反复撤销导致的代际劣化；压缩级别取较低值
以换取更快的存取速度。
"""
from __future__ import annotations

import io

from PIL import Image


class HistoryManager:
    def __init__(self, max_steps: int = 20):
        self.max_steps = max_steps
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []

    @staticmethod
    def _snapshot(img: Image.Image) -> bytes:
        buf = io.BytesIO()
        img.save(buf, "PNG", compress_level=1)
        return buf.getvalue()

    @staticmethod
    def _restore(data: bytes) -> Image.Image:
        return Image.open(io.BytesIO(data)).copy()

    def push(self, img: Image.Image) -> None:
        """在修改前调用，记录当前状态。"""
        self._undo.append(self._snapshot(img))
        if len(self._undo) > self.max_steps:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self, current: Image.Image) -> Image.Image:
        if not self._undo:
            return current
        self._redo.append(self._snapshot(current))
        return self._restore(self._undo.pop())

    def redo(self, current: Image.Image) -> Image.Image:
        if not self._redo:
            return current
        self._undo.append(self._snapshot(current))
        return self._restore(self._redo.pop())

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
