# -*- coding: utf-8 -*-
"""主窗口：串联各模块，承载编辑状态、预览/提交与撤销重做逻辑。"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (QFileDialog, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QSpinBox, QComboBox, QWidget)

from app import imageops, recent
from app.canvas import ImageCanvas, Mode, pil_to_qimage
from app.dialogs import ExportDialog
from app.history import HistoryManager
from app.panels import RightPanel
from app.sidebar import Sidebar

_SAVE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_FORMAT_BY_EXT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = recent.load()

        # ---- 编辑状态 ----
        self.history = HistoryManager(20)
        self.base_image: Image.Image | None = None      # 已提交的基础图
        self.original_image: Image.Image | None = None  # 载入原图（用于对比）
        self.current_path: str | None = None
        self.current_folder: str | None = None
        self.folder_files: list[str] = []

        self.adjust_values = {"brightness": 0, "contrast": 0,
                              "saturation": 0, "temperature": 0, "exposure": 0}
        self.filter_active: str | None = None
        self.filter_strength = 100

        self.overlay: dict | None = None
        self.overlay_pos = (0, 0)

        self.draw_tool_key: str | None = None
        self.draw_color = (255, 0, 0)
        self.draw_width = 4
        self.draw_opacity = 255

        self._build_ui()
        self._update_recent_sidebar()
        self._update_actions()
        self.setWindowTitle("Chovy —— 离线图像处理")
        self.resize(1320, 820)

    # ==================================================================
    # UI 构建
    # ==================================================================
    def _build_ui(self):
        # 画布
        self.canvas = ImageCanvas()
        self.canvas.cropCommitted.connect(self.on_crop)
        self.canvas.drawCommitted.connect(self.on_draw_committed)
        self.canvas.overlayMoved.connect(self.on_overlay_moved)
        self.canvas.setMinimumSize(300, 300)

        # 侧边栏
        self.sidebar = Sidebar()
        self.sidebar.openRequested.connect(self.open_image)

        # 右侧面板
        self.panels = RightPanel(self)

        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.panels)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        self.setCentralWidget(splitter)

        self._build_menus()
        self._build_toolbar()
        self.statusBar().showMessage("就绪 —— 打开图片或拖拽图片到窗口")
        self.setAcceptDrops(True)

    def _build_menus(self):
        menubar = self.menuBar()

        m_file = menubar.addMenu("文件(&F)")
        self.act_open = self._action("打开图片…", "Ctrl+O", self.open_image_dialog)
        self.act_open_folder = self._action("打开文件夹…", "Ctrl+Shift+O", self.open_folder_dialog)
        m_file.addAction(self.act_open)
        m_file.addAction(self.act_open_folder)
        self.recent_menu = m_file.addMenu("最近打开")
        m_file.addSeparator()
        self.act_save = self._action("保存", "Ctrl+S", self.save)
        self.act_export = self._action("导出 / 另存为…", "Ctrl+Shift+S", self.save_as)
        m_file.addAction(self.act_save)
        m_file.addAction(self.act_export)
        m_file.addSeparator()
        m_file.addAction(self._action("退出", "Ctrl+Q", self.close))

        m_edit = menubar.addMenu("编辑(&E)")
        self.act_undo = self._action("撤销", "Ctrl+Z", self.undo)
        self.act_redo = self._action("重做", "Ctrl+Y", self.redo)
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])

        m_view = menubar.addMenu("视图(&V)")
        m_view.addAction(self._action("适应窗口", "Ctrl+0", lambda: self.canvas.fit()))
        m_view.addAction(self._action("放大", "Ctrl+=", lambda: self.canvas.zoom(1.25)))
        m_view.addAction(self._action("缩小", "Ctrl+-", lambda: self.canvas.zoom(0.8)))
        m_view.addAction(self._action("100%", "Ctrl+1", self.canvas.reset_view))

        m_help = menubar.addMenu("帮助(&H)")
        m_help.addAction(self._action("使用说明", None, self._show_help))

    def _build_toolbar(self):
        tb = self.addToolBar("主工具栏")
        tb.setMovable(False)
        tb.addAction(self.act_open)
        tb.addAction(self.act_open_folder)
        tb.addAction(self.act_save)
        tb.addAction(self.act_export)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self._action("适应窗口", None, lambda: self.canvas.fit()))
        tb.addAction(self._action("放大", None, lambda: self.canvas.zoom(1.25)))
        tb.addAction(self._action("缩小", None, lambda: self.canvas.zoom(0.8)))
        tb.addSeparator()
        self.act_compare = self._action("原图对比(空格)", None, self._toggle_compare)
        self.act_compare.setCheckable(True)
        tb.addAction(self.act_compare)

    def _action(self, text, shortcut, slot) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        return a

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_initial_fit_done", False):
            self._initial_fit_done = True
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._initial_fit)

    def _initial_fit(self):
        if self.canvas.has_image():
            self.canvas.fit()

    # ==================================================================
    # 打开 / 载入
    # ==================================================================
    def open_image_dialog(self):
        start = self.config.get("last_open_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", start,
            "图片文件 (*.jpg *.jpeg *.png *.gif *.bmp *.webp);;所有文件 (*.*)")
        if path:
            self.config["last_open_dir"] = os.path.dirname(path)
            self.open_image(path)

    def open_folder_dialog(self):
        start = self.config.get("last_open_dir", "")
        folder = QFileDialog.getExistingDirectory(self, "打开文件夹", start)
        if folder:
            self.config["last_open_dir"] = folder
            self.open_folder(folder)

    @staticmethod
    def _load_pil(path: str) -> Image.Image:
        img = Image.open(path)
        img.load()
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "PA"):
            return img.convert("RGBA")
        return img.convert("RGB")

    def open_image(self, path: str):
        if not os.path.isfile(path):
            return
        try:
            img = self._load_pil(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "无法打开", f"打开失败：\n{path}\n{exc}")
            return
        self.current_path = path
        self.base_image = img
        self.original_image = img.copy()
        self.history.clear()
        self._reset_live_state()

        # 更新所在文件夹上下文
        folder = os.path.dirname(path)
        if folder != self.current_folder:
            self.current_folder = folder
            self.folder_files = _list_images(folder)

        # 侧边栏「当前图片」标签页只显示当前这一张
        self.sidebar.set_current(path)

        self.config = recent.add_recent_file(self.config, path)
        recent.save(self.config)
        self._update_recent_sidebar()
        self._sync_size_fields()
        self.refresh_display()
        self.canvas.fit()  # 必须在设置新图像后再适应窗口
        self.statusBar().showMessage(f"已打开：{path}")

    def open_folder(self, folder: str):
        files = _list_images(folder)
        if not files:
            QMessageBox.information(self, "提示", "该文件夹内没有支持的图片文件。")
            return
        self.current_folder = folder
        self.folder_files = files
        self.config = recent.add_recent_folder(self.config, folder)
        recent.save(self.config)
        self.open_image(files[0])

    def _update_recent_sidebar(self):
        paths = recent.recent_file_paths(self.config)
        # 过滤掉已不存在的文件，并同步清理配置
        existing = [p for p in paths if os.path.isfile(p)]
        if len(existing) != len(paths):
            self.config["recent_files"] = [
                (p, t) for p, t in self.config.get("recent_files", [])
                if os.path.isfile(p)
            ]
            recent.save(self.config)
        self.sidebar.set_recent(existing)
        self.recent_menu.clear()
        if not existing:
            self.recent_menu.addAction("（暂无）").setEnabled(False)
        for p in existing[:12]:
            name = os.path.basename(p)
            a = self.recent_menu.addAction(name)
            a.setToolTip(p)
            a.triggered.connect(lambda _=False, path=p: self.open_image(path))

    def _sync_size_fields(self):
        if self.base_image is not None:
            self.panels.adjust.sync_size(self.base_image.width, self.base_image.height)
        self.panels.reset()

    # ==================================================================
    # 渲染管线
    # ==================================================================
    def _render_base(self) -> Image.Image | None:
        """基础 + 调节 + 滤镜（不含覆盖层）。"""
        if self.base_image is None:
            return None
        img = imageops.apply_adjustments(self.base_image, self.adjust_values)
        if self.filter_active:
            img = imageops.apply_filter(img, self.filter_active, self.filter_strength)
        return img

    def _bake_live(self) -> Image.Image:
        """纯函数：把当前实时状态（调节+滤镜+覆盖层）合成到基础图，返回新图。"""
        img = self._render_base()
        if img is None:
            return self.base_image
        if self.overlay is not None:
            img = self._apply_overlay_pil(img)
        return img

    def _reset_live_state(self):
        self.adjust_values = {k: 0 for k in self.adjust_values}
        self.filter_active = None
        self.filter_strength = 100
        self.overlay = None
        self.overlay_pos = (0, 0)
        self.canvas.set_overlay(None, None)

    def refresh_display(self):
        self.canvas.set_image(self._render_base())
        self.canvas.set_original(self.original_image)
        self._update_overlay_canvas()
        self._update_actions()

    def commit_destructive(self, op):
        """提交一次破坏性操作：合成实时状态 -> 记录历史 -> 应用 op -> 复位。"""
        if self.base_image is None:
            return
        baked = self._bake_live()
        self.history.push(self.base_image)
        old_size = self.base_image.size
        self.base_image = op(baked)
        self._reset_live_state()
        self.panels.adjust.reset()
        self.panels.filter.reset()
        self.refresh_display()
        # 裁剪/旋转/缩放会改变图像尺寸，此时重新适配窗口，避免结果缩在角落
        if self.base_image.size != old_size:
            self.canvas.fit()

    # ==================================================================
    # 调整
    # ==================================================================
    def set_adjust(self, key, value):
        if self.base_image is None:
            return
        self.adjust_values[key] = value
        self.refresh_display()

    def reset_adjustments(self):
        if self.base_image is None:
            return
        self.adjust_values = {k: 0 for k in self.adjust_values}
        self.refresh_display()

    def auto_white_balance(self):
        self.commit_destructive(imageops.auto_white_balance)

    def auto_contrast(self):
        self.commit_destructive(imageops.auto_contrast)

    def auto_sharpen(self):
        self.commit_destructive(imageops.auto_sharpen)

    # ==================================================================
    # 滤镜
    # ==================================================================
    def set_filter(self, name):
        if self.base_image is None:
            return
        self.filter_active = name
        self.refresh_display()

    def set_filter_strength(self, value):
        if self.base_image is None:
            return
        self.filter_strength = value
        self.refresh_display()

    def apply_filter(self):
        if self.filter_active is not None:
            self.commit_destructive(lambda img: img)

    def cancel_filter(self):
        self.filter_active = None
        self.refresh_display()

    # ==================================================================
    # 几何变换
    # ==================================================================
    def begin_crop(self, ratio):
        if self.base_image is None:
            return
        self.canvas.start_crop(ratio)
        self.statusBar().showMessage("拖拽选择裁剪区域，Esc 取消")

    def on_crop(self, box):
        self.commit_destructive(lambda img: imageops.crop(img, box))
        self.statusBar().showMessage("已裁剪")

    def rotate90(self, clockwise=True):
        self.commit_destructive(lambda img: imageops.rotate_90(img, clockwise))

    def rotate_arbitrary(self, angle):
        if angle == 0:
            return
        self.commit_destructive(lambda img: imageops.rotate(img, angle))

    def flip(self, horizontal=True):
        self.commit_destructive(lambda img: imageops.flip(img, horizontal))

    def apply_resize(self, w, h, keep_ratio):
        if self.base_image is None or w <= 0 or h <= 0:
            return
        self.commit_destructive(lambda img: imageops.resize(img, w, h, keep_ratio))
        self._sync_size_fields()

    # ==================================================================
    # 水印 / 文字标注（覆盖层）
    # ==================================================================
    def set_text_watermark(self, text, font, size, color, opacity):
        self._set_overlay({"kind": "text", "text": text, "font": font,
                           "size": size, "color": tuple(color), "opacity": opacity})
        self.statusBar().showMessage("拖动水印调整位置，点击「应用水印」确认")

    def set_image_watermark(self, logo_path, ratio, opacity):
        try:
            logo = Image.open(logo_path).convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "无法打开", f"Logo 打开失败：{exc}")
            return
        self._set_overlay({"kind": "image", "logo": logo,
                           "ratio": ratio, "opacity": opacity})
        self.statusBar().showMessage("拖动水印调整位置，点击「应用水印」确认")

    def set_text_annotation(self, text, font, size, color):
        self._set_overlay({"kind": "text", "text": text, "font": font,
                           "size": size, "color": tuple(color), "opacity": 1.0})
        self.statusBar().showMessage("拖动标注调整位置，点击「应用标注」确认")

    def _set_overlay(self, overlay):
        if self.base_image is None:
            return
        self.overlay = overlay
        bw, bh = self._overlay_size(overlay)
        self.overlay_pos = ((self.base_image.width - bw) // 2,
                            (self.base_image.height - bh) // 2)
        self._update_overlay_canvas()

    def _overlay_size(self, overlay) -> tuple[int, int]:
        if overlay["kind"] == "text":
            return imageops.measure_text(overlay["text"], overlay["font"], overlay["size"])
        logo = overlay["logo"]
        w = max(1, int(self.base_image.width * overlay["ratio"]))
        h = max(1, int(logo.height * (w / max(1, logo.width))))
        return w, h

    def _update_overlay_canvas(self):
        if self.overlay is None:
            self.canvas.set_overlay(None, None)
            return
        bw, bh = self._overlay_size(self.overlay)
        pm = self._overlay_pixmap(self.overlay, bw, bh)
        self.canvas.set_overlay(
            QRectF(self.overlay_pos[0], self.overlay_pos[1], bw, bh), pm)

    def _overlay_pixmap(self, overlay, bw, bh) -> QPixmap:
        if overlay["kind"] == "text":
            img = Image.new("RGBA", (max(1, bw), max(1, bh)), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(overlay["font"], overlay["size"])
            except OSError:
                font = ImageFont.load_default()
            d.text((0, 0), overlay["text"], font=font,
                   fill=overlay["color"] + (255,))
            opacity = overlay.get("opacity", 1.0)
            if opacity < 1.0:
                img.putalpha(img.getchannel("A").point(lambda a: int(a * opacity)))
            return QPixmap.fromImage(pil_to_qimage(img))
        logo = overlay["logo"].convert("RGBA").resize((bw, bh), Image.Resampling.LANCZOS)
        opacity = overlay.get("opacity", 1.0)
        if opacity < 1.0:
            logo.putalpha(logo.getchannel("A").point(lambda a: int(a * opacity)))
        return QPixmap.fromImage(pil_to_qimage(logo))

    def _apply_overlay_pil(self, img):
        ov = self.overlay
        x, y = int(self.overlay_pos[0]), int(self.overlay_pos[1])
        if ov["kind"] == "text":
            return imageops.add_text_watermark(
                img, ov["text"], ov["font"], ov["size"], ov["color"],
                ov.get("opacity", 1.0), (x, y))
        return imageops.add_image_watermark(
            img, ov["logo"], ov["ratio"], ov.get("opacity", 1.0), (x, y))

    def on_overlay_moved(self, x, y):
        self.overlay_pos = (x, y)

    def commit_overlay(self):
        if self.overlay is not None:
            self.commit_destructive(lambda img: img)

    def cancel_overlay(self):
        self.overlay = None
        self.canvas.set_overlay(None, None)
        self.refresh_display()

    # ==================================================================
    # 绘制
    # ==================================================================
    def set_draw_tool(self, key):
        if self.base_image is None:
            return
        if key == self.draw_tool_key and self.canvas.get_mode() == Mode.DRAW:
            self.draw_tool_key = None
            self.canvas.set_mode(Mode.VIEW)
            self.panels.draw.clear_tool()
            return
        self.draw_tool_key = key
        self.canvas.start_draw({"tool": key, "color": self.draw_color,
                                "width": self.draw_width,
                                "opacity": self.draw_opacity})
        self.statusBar().showMessage("在画布上拖拽绘制，Esc 退出绘制")

    def set_draw_param(self, key, value):
        if key == "color":
            self.draw_color = tuple(value)
        elif key == "width":
            self.draw_width = int(value)
        elif key == "opacity":
            self.draw_opacity = int(value)
        if self.canvas.get_mode() == Mode.DRAW:
            self.canvas.update_draw_tool(key, value if key != "color" else tuple(value))

    def on_draw_committed(self, primitives):
        self.commit_destructive(lambda img: imageops.apply_drawings(img, primitives))

    # ==================================================================
    # 撤销 / 重做
    # ==================================================================
    def undo(self):
        if not self.history.can_undo:
            return
        self._reset_live_state()
        self.panels.adjust.reset()
        self.panels.filter.reset()
        self.base_image = self.history.undo(self.base_image)
        self._sync_size_fields()
        self.refresh_display()

    def redo(self):
        if not self.history.can_redo:
            return
        self._reset_live_state()
        self.panels.adjust.reset()
        self.panels.filter.reset()
        self.base_image = self.history.redo(self.base_image)
        self._sync_size_fields()
        self.refresh_display()

    # ==================================================================
    # 保存 / 导出
    # ==================================================================
    def save(self):
        if self.base_image is None:
            return
        if self.current_path and \
                os.path.splitext(self.current_path)[1].lower() in _SAVE_EXTS:
            fmt = _FORMAT_BY_EXT[os.path.splitext(self.current_path)[1].lower()]
            self._save_to(self.current_path, fmt, 90)
        else:
            self.save_as()

    def save_as(self):
        if self.base_image is None:
            return
        dlg = ExportDialog(self)
        if not dlg.exec():
            return
        fmt = dlg.format
        default = os.path.basename(self.current_path) if self.current_path else "未命名"
        stem, _ = os.path.splitext(default)
        ext = {"PNG": ".png", "JPG": ".jpg", "WebP": ".webp"}[fmt]
        start_dir = self.config.get("last_save_dir", self.current_folder or "")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出图片", os.path.join(start_dir, stem + ext),
            {"PNG": "PNG 图片 (*.png)", "JPG": "JPEG 图片 (*.jpg *.jpeg)",
             "WebP": "WebP 图片 (*.webp)"}[fmt])
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ext
        self.config["last_save_dir"] = os.path.dirname(path)
        recent.save(self.config)
        self._save_to(path, fmt, dlg.quality)

    def _save_to(self, path, fmt, quality):
        img = self._bake_live()
        try:
            if fmt == "JPEG":
                if img.mode in ("RGBA", "LA", "P"):
                    img = _flatten_alpha(img)
                img = img.convert("RGB")
                img.save(path, "JPEG", quality=quality)
            elif fmt == "WEBP":
                img.save(path, "WEBP", quality=quality)
            else:
                img.save(path, "PNG")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.statusBar().showMessage(f"已保存：{path}")

    # ==================================================================
    # 视图 / 对比 / 快捷键
    # ==================================================================
    def _toggle_compare(self, checked):
        self.canvas.set_compare(checked)

    def _update_actions(self):
        has = self.base_image is not None
        self.act_save.setEnabled(has)
        self.act_export.setEnabled(has)
        self.act_undo.setEnabled(self.history.can_undo)
        self.act_redo.setEnabled(self.history.can_redo)

    def _is_text_input_focus(self) -> bool:
        w = self.focusWidget()
        return isinstance(w, (QLineEdit, QSpinBox, QComboBox))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self._is_text_input_focus():
                self.canvas.set_compare(True)
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_interaction()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.canvas.set_compare(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _cancel_interaction(self):
        self.canvas.cancel_interaction()
        self.draw_tool_key = None
        self.panels.draw.clear_tool()
        if self.overlay is not None:
            self.cancel_overlay()
        self.statusBar().showMessage("已取消")

    # ==================================================================
    # 拖拽打开
    # ==================================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        files = [p for p in paths if os.path.isfile(p)]
        dirs = [p for p in paths if os.path.isdir(p)]
        if dirs:
            self.open_folder(dirs[0])
            return
        if files:
            self.open_image(files[0])

    # ==================================================================
    # 其它
    # ==================================================================
    def _show_help(self):
        QMessageBox.information(
            self, "使用说明",
            "打开：文件菜单 / 工具栏 / 拖拽图片到窗口\n"
            "裁剪：调整面板选择比例后在画布拖拽\n"
            "实时调节：拖动亮度/对比度等滑块\n"
            "滤镜：选择滤镜后调节强度，点「应用滤镜」生效\n"
            "水印/标注：添加后可拖拽定位，点「应用」生效\n"
            "绘制：选择工具后在画布拖拽，Esc 退出\n"
            "对比原图：按住空格键\n"
            "撤销/重做：Ctrl+Z / Ctrl+Y（最多 20 步）\n"
            "导出：Ctrl+Shift+S 选择格式与质量\n"
            "批量处理：右侧「批处理」标签页")

    def closeEvent(self, event):
        recent.save(self.config)
        super().closeEvent(event)


def _list_images(folder: str) -> list[str]:
    exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    out = []
    try:
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and os.path.splitext(name)[1].lower() in exts:
                out.append(p)
    except OSError:
        pass
    return out


def _flatten_alpha(img: Image.Image) -> Image.Image:
    bg = Image.new("RGB", img.size, (255, 255, 255))
    if img.mode == "RGBA":
        bg.paste(img, mask=img.getchannel("A"))
    else:
        bg.paste(img.convert("RGB"))
    return bg
