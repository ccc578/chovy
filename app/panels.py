# -*- coding: utf-8 -*-
"""右侧控制面板：调整 / 滤镜 / 水印 / 绘制 / 批处理。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog,
                               QComboBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QProgressBar, QPushButton, QScrollArea, QSlider,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from app.batch import BatchThread, list_images

# ---------------------------------------------------------------------------
# 通用小部件
# ---------------------------------------------------------------------------

_FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

_FONT_CANDIDATES = [
    ("微软雅黑", "msyh.ttc"),
    ("黑体", "simhei.ttf"),
    ("宋体", "simsun.ttc"),
    ("楷体", "simkai.ttf"),
    ("仿宋", "simfang.ttf"),
    ("Arial", "arial.ttf"),
    ("Times New Roman", "times.ttf"),
    ("Consolas", "consola.ttf"),
    ("Comic Sans MS", "comic.ttf"),
]


def get_fonts() -> list[tuple[str, str]]:
    out = []
    for name, fname in _FONT_CANDIDATES:
        path = os.path.join(_FONT_DIR, fname)
        if os.path.isfile(path):
            out.append((name, path))
    if not out:
        out.append(("默认字体", ""))
    return out


class ColorButton(QPushButton):
    colorChanged = Signal(tuple)

    def __init__(self, color=(255, 0, 0), parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 24)
        self._color = color
        self.clicked.connect(self._pick)
        self._refresh()

    def _refresh(self):
        r, g, b = self._color
        self.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border:1px solid #888;"
            f" border-radius:3px;")

    def _pick(self):
        # 深色主题会影响颜色选择框的显示，打开期间临时移除主题，保证颜色显示正确
        app = QApplication.instance()
        old_qss = app.styleSheet() if app else ""
        if old_qss:
            app.setStyleSheet("")
        try:
            # 不能把 ColorButton 自身作为父级：其内联的背景色样式会级联到颜色选择框，
            # 导致选中红色时整个选择框也被染红。挂到顶层窗口即可避免。
            c = QColorDialog.getColor(QColor(*self._color), self.window(), "选择颜色")
        finally:
            if old_qss and app:
                app.setStyleSheet(old_qss)
        if c.isValid():
            self._color = (c.red(), c.green(), c.blue())
            self._refresh()
            self.colorChanged.emit(self._color)

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = tuple(color)
        self._refresh()


def _slider_row(label_text, minimum, maximum, value, on_change=None):
    row = QHBoxLayout()
    label = QLabel(label_text)
    label.setFixedWidth(46)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    val = QLabel(str(value))
    val.setFixedWidth(36)
    val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _changed(v):
        val.setText(str(v))
        if on_change:
            on_change(v)

    slider.valueChanged.connect(_changed)
    row.addWidget(label)
    row.addWidget(slider, 1)
    row.addWidget(val)
    return row, slider


# ---------------------------------------------------------------------------
# 调整面板
# ---------------------------------------------------------------------------

class AdjustPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.sliders = {}
        self._img_w = 0
        self._img_h = 0
        self._syncing = False
        layout = QVBoxLayout(self)

        # 裁剪
        crop_group = QGroupBox("裁剪")
        crop_layout = QGridLayout(crop_group)
        ratios = [
            ("自由", None), ("1:1", 1.0), ("16:9", 16 / 9), ("4:3", 4 / 3),
            ("3:4", 3 / 4), ("证件照(5:7)", 5 / 7),
        ]
        self._crop_group = QButtonGroup(self)
        for i, (label, ratio) in enumerate(ratios):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, r=ratio: self.app.begin_crop(r))
            self._crop_group.addButton(btn, i)
            crop_layout.addWidget(btn, i // 3, i % 3)
        layout.addWidget(crop_group)

        # 旋转 / 翻转
        rot_group = QGroupBox("旋转 / 翻转")
        rot_layout = QGridLayout(rot_group)
        btn_rot_l = QPushButton("↺ 左转90°")
        btn_rot_r = QPushButton("↻ 右转90°")
        btn_flip_h = QPushButton("水平翻转")
        btn_flip_v = QPushButton("垂直翻转")
        btn_rot_l.clicked.connect(lambda: self.app.rotate90(clockwise=False))
        btn_rot_r.clicked.connect(lambda: self.app.rotate90(clockwise=True))
        btn_flip_h.clicked.connect(lambda: self.app.flip(horizontal=True))
        btn_flip_v.clicked.connect(lambda: self.app.flip(horizontal=False))
        rot_layout.addWidget(btn_rot_l, 0, 0)
        rot_layout.addWidget(btn_rot_r, 0, 1)
        rot_layout.addWidget(btn_flip_h, 1, 0)
        rot_layout.addWidget(btn_flip_v, 1, 1)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("任意角度"))
        self._angle = QSpinBox()
        self._angle.setRange(-360, 360)
        self._angle.setValue(0)
        self._angle.setSuffix("°")
        btn_rot_apply = QPushButton("旋转")
        btn_rot_apply.clicked.connect(lambda: self.app.rotate_arbitrary(self._angle.value()))
        rot_row.addWidget(self._angle)
        rot_row.addWidget(btn_rot_apply)
        rot_layout.addLayout(rot_row, 2, 0, 1, 2)
        layout.addWidget(rot_group)

        # 缩放
        resize_group = QGroupBox("缩放")
        resize_layout = QGridLayout(resize_group)
        resize_layout.addWidget(QLabel("宽"), 0, 0)
        self._rw = QSpinBox()
        self._rw.setRange(1, 20000)
        self._rw.setValue(0)
        resize_layout.addWidget(self._rw, 0, 1)
        resize_layout.addWidget(QLabel("高"), 0, 2)
        self._rh = QSpinBox()
        self._rh.setRange(1, 20000)
        self._rh.setValue(0)
        resize_layout.addWidget(self._rh, 0, 3)
        self._keep_ratio = QCheckBox("等比")
        self._keep_ratio.setChecked(True)
        self._rw.valueChanged.connect(self._on_w_changed)
        self._rh.valueChanged.connect(self._on_h_changed)
        resize_layout.addWidget(self._keep_ratio, 1, 0, 1, 2)
        btn_resize = QPushButton("应用缩放")
        btn_resize.clicked.connect(self._apply_resize)
        resize_layout.addWidget(btn_resize, 1, 2, 1, 2)
        layout.addWidget(resize_group)

        # 参数调节
        adj_group = QGroupBox("参数调节")
        adj_layout = QVBoxLayout(adj_group)
        keys = [
            ("brightness", "亮度"), ("contrast", "对比度"),
            ("saturation", "饱和度"), ("temperature", "色温"),
            ("exposure", "曝光度"),
        ]
        for key, label in keys:
            row, slider = _slider_row(label, -100, 100, 0,
                                      lambda v, k=key: self.app.set_adjust(k, v))
            self.sliders[key] = slider
            adj_layout.addLayout(row)
        btn_reset = QPushButton("重置全部参数")
        btn_reset.clicked.connect(self._reset)
        adj_layout.addWidget(btn_reset)
        layout.addWidget(adj_group)

        # 一键优化
        opt_group = QGroupBox("一键优化")
        opt_layout = QVBoxLayout(opt_group)
        for label, fn in [("自动白平衡", self.app.auto_white_balance),
                          ("自动对比度", self.app.auto_contrast),
                          ("一键锐化", self.app.auto_sharpen)]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            opt_layout.addWidget(b)
        layout.addWidget(opt_group)
        layout.addStretch(1)

    def _apply_resize(self):
        self.app.apply_resize(self._rw.value(), self._rh.value(),
                              self._keep_ratio.isChecked())

    def _on_w_changed(self, w: int):
        if self._syncing or not self._keep_ratio.isChecked():
            return
        if self._img_w <= 0 or self._img_h <= 0:
            return
        self._syncing = True
        self._rh.setValue(max(1, round(w * self._img_h / self._img_w)))
        self._syncing = False

    def _on_h_changed(self, h: int):
        if self._syncing or not self._keep_ratio.isChecked():
            return
        if self._img_w <= 0 or self._img_h <= 0:
            return
        self._syncing = True
        self._rw.setValue(max(1, round(h * self._img_w / self._img_h)))
        self._syncing = False

    def _reset(self):
        for key, slider in self.sliders.items():
            slider.setValue(0)
        self.app.reset_adjustments()

    def sync_size(self, w, h):
        self._img_w = w
        self._img_h = h
        self._syncing = True
        self._rw.setValue(w)
        self._rh.setValue(h)
        self._syncing = False

    def reset(self):
        for slider in self.sliders.values():
            slider.setValue(0)


# ---------------------------------------------------------------------------
# 滤镜面板
# ---------------------------------------------------------------------------

class FilterPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        from app.imageops import FILTERS
        layout = QVBoxLayout(self)

        group = QGroupBox("选择滤镜")
        grid = QGridLayout(group)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._filter_btns = {}
        for i, (key, label) in enumerate(FILTERS.items()):
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.app.set_filter(k))
            self._btn_group.addButton(b)
            self._filter_btns[key] = b
            grid.addWidget(b, i // 2, i % 2)
        layout.addWidget(group)

        self._strength_row, self._strength = _slider_row(
            "强度", 0, 100, 100, lambda v: self.app.set_filter_strength(v))
        layout.addLayout(self._strength_row)

        row = QHBoxLayout()
        btn_apply = QPushButton("应用滤镜")
        btn_apply.clicked.connect(self._apply)
        btn_cancel = QPushButton("取消滤镜")
        btn_cancel.clicked.connect(self._cancel)
        row.addWidget(btn_apply)
        row.addWidget(btn_cancel)
        layout.addLayout(row)
        layout.addStretch(1)

    def _apply(self):
        self.app.apply_filter()
        self._clear_check()

    def _cancel(self):
        self.app.cancel_filter()
        self._clear_check()

    def _clear_check(self):
        checked = self._btn_group.checkedButton()
        if checked:
            self._btn_group.setExclusive(False)
            checked.setChecked(False)
            self._btn_group.setExclusive(True)

    def reset(self):
        self._clear_check()
        self._strength.setValue(100)


# ---------------------------------------------------------------------------
# 水印面板
# ---------------------------------------------------------------------------

class WatermarkPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._logo_path = ""
        layout = QVBoxLayout(self)

        text_group = QGroupBox("文字水印")
        tg = QGridLayout(text_group)
        tg.addWidget(QLabel("内容"), 0, 0)
        self._text = QLineEdit("© Chovy")
        tg.addWidget(self._text, 0, 1, 1, 3)
        tg.addWidget(QLabel("字体"), 1, 0)
        self._font = QComboBox()
        for name, path in get_fonts():
            self._font.addItem(name, path)
        tg.addWidget(self._font, 1, 1, 1, 3)
        tg.addWidget(QLabel("字号"), 2, 0)
        self._tsize = QSpinBox()
        self._tsize.setRange(8, 500)
        self._tsize.setValue(40)
        tg.addWidget(self._tsize, 2, 1)
        tg.addWidget(QLabel("颜色"), 2, 2)
        self._tcolor = ColorButton((255, 255, 255))
        tg.addWidget(self._tcolor, 2, 3)
        tg.addWidget(QLabel("透明度"), 3, 0)
        self._topacity_row, self._topacity = _slider_row("", 5, 100, 80)
        tg.addLayout(self._topacity_row, 3, 1, 1, 3)
        btn_add_text = QPushButton("添加文字水印")
        btn_add_text.clicked.connect(self._add_text)
        tg.addWidget(btn_add_text, 4, 0, 1, 4)
        layout.addWidget(text_group)

        img_group = QGroupBox("图片水印")
        ig = QGridLayout(img_group)
        btn_pick = QPushButton("导入 Logo 图片")
        btn_pick.clicked.connect(self._pick_logo)
        self._logo_label = QLabel("未选择")
        self._logo_label.setStyleSheet("color:#999;")
        ig.addWidget(btn_pick, 0, 0, 1, 2)
        ig.addWidget(self._logo_label, 1, 0, 1, 2)
        ig.addWidget(QLabel("大小%"), 2, 0)
        self._isize = QSpinBox()
        self._isize.setRange(1, 100)
        self._isize.setValue(25)
        ig.addWidget(self._isize, 2, 1)
        ig.addWidget(QLabel("透明度"), 3, 0)
        self._iopacity_row, self._iopacity = _slider_row("", 5, 100, 70)
        ig.addLayout(self._iopacity_row, 3, 1)
        btn_add_img = QPushButton("添加图片水印")
        btn_add_img.clicked.connect(self._add_image)
        ig.addWidget(btn_add_img, 4, 0, 1, 2)
        layout.addWidget(img_group)

        row = QHBoxLayout()
        btn_ok = QPushButton("应用水印")
        btn_ok.clicked.connect(self.app.commit_overlay)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.app.cancel_overlay)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        layout.addLayout(row)
        layout.addStretch(1)

    def _add_text(self):
        text = self._text.text().strip()
        if not text:
            return
        font_path = self._font.currentData() or ""
        self.app.set_text_watermark(
            text, font_path, self._tsize.value(), self._tcolor.color(),
            self._topacity.value() / 100.0)

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Logo 图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if path:
            self._logo_path = path
            self._logo_label.setText(os.path.basename(path))

    def _add_image(self):
        if not self._logo_path:
            return
        self.app.set_image_watermark(
            self._logo_path, self._isize.value() / 100.0,
            self._iopacity.value() / 100.0)


# ---------------------------------------------------------------------------
# 绘制面板
# ---------------------------------------------------------------------------

class DrawPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        layout = QVBoxLayout(self)

        tools = QGroupBox("工具")
        tg = QGridLayout(tools)
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        tools_def = [
            ("brush", "画笔"), ("erase", "橡皮擦"), ("rect", "矩形"),
            ("ellipse", "圆形"), ("line", "直线"), ("arrow", "箭头"),
        ]
        for i, (key, label) in enumerate(tools_def):
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.app.set_draw_tool(k))
            self._tool_group.addButton(b)
            tg.addWidget(b, i // 3, i % 3)
        layout.addWidget(tools)

        props = QGroupBox("属性")
        pg = QGridLayout(props)
        pg.addWidget(QLabel("颜色"), 0, 0)
        self._color = ColorButton((255, 0, 0))
        self._color.colorChanged.connect(lambda c: self.app.set_draw_param("color", c))
        pg.addWidget(self._color, 0, 1)
        pg.addWidget(QLabel("粗细"), 0, 2)
        self._width = QSpinBox()
        self._width.setRange(1, 200)
        self._width.setValue(4)
        self._width.valueChanged.connect(lambda v: self.app.set_draw_param("width", v))
        pg.addWidget(self._width, 0, 3)
        pg.addWidget(QLabel("透明度"), 1, 0)
        self._opacity_row, self._opacity = _slider_row("", 10, 100, 100,
                                                       lambda v: self.app.set_draw_param("opacity", int(v * 2.55)))
        pg.addLayout(self._opacity_row, 1, 1, 1, 3)
        layout.addWidget(props)

        text_group = QGroupBox("文字标注")
        txg = QGridLayout(text_group)
        txg.addWidget(QLabel("文字"), 0, 0)
        self._text = QLineEdit("")
        self._text.setPlaceholderText("输入标注文字")
        txg.addWidget(self._text, 0, 1, 1, 3)
        txg.addWidget(QLabel("字体"), 1, 0)
        self._font = QComboBox()
        for name, path in get_fonts():
            self._font.addItem(name, path)
        txg.addWidget(self._font, 1, 1, 1, 3)
        txg.addWidget(QLabel("字号"), 2, 0)
        self._tsize = QSpinBox()
        self._tsize.setRange(8, 300)
        self._tsize.setValue(24)
        txg.addWidget(self._tsize, 2, 1)
        txg.addWidget(QLabel("颜色"), 2, 2)
        self._tcolor = ColorButton((255, 0, 0))
        txg.addWidget(self._tcolor, 2, 3)
        btn_text = QPushButton("添加文字标注（可拖动）")
        btn_text.clicked.connect(self._add_text)
        txg.addWidget(btn_text, 3, 0, 1, 4)
        layout.addWidget(text_group)

        row = QHBoxLayout()
        btn_ok = QPushButton("应用标注")
        btn_ok.clicked.connect(self.app.commit_overlay)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.app.cancel_overlay)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        layout.addLayout(row)
        layout.addStretch(1)

    def _add_text(self):
        text = self._text.text().strip()
        if not text:
            return
        font_path = self._font.currentData() or ""
        self.app.set_text_annotation(
            text, font_path, self._tsize.value(), self._tcolor.color())

    def clear_tool(self):
        b = self._tool_group.checkedButton()
        if b:
            self._tool_group.setExclusive(False)
            b.setChecked(False)
            self._tool_group.setExclusive(True)

    def reset(self):
        self.clear_tool()


# ---------------------------------------------------------------------------
# 批处理面板
# ---------------------------------------------------------------------------

class BatchPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._files: list[str] = []
        self._thread: BatchThread | None = None

        layout = QVBoxLayout(self)

        src_group = QGroupBox("1. 选择图片")
        sg = QVBoxLayout(src_group)
        btn_row = QHBoxLayout()
        btn_add_files = QPushButton("添加图片…")
        btn_add_files.clicked.connect(self._pick_files)
        btn_add_folder = QPushButton("添加文件夹…")
        btn_add_folder.clicked.connect(self._pick_folder)
        btn_row.addWidget(btn_add_files)
        btn_row.addWidget(btn_add_folder)
        sg.addLayout(btn_row)

        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._file_list.setFixedHeight(90)
        sg.addWidget(self._file_list)

        list_row = QHBoxLayout()
        btn_remove = QPushButton("移除选中")
        btn_remove.clicked.connect(self._remove_selected)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_files)
        self._count_label = QLabel("未选择图片")
        self._count_label.setStyleSheet("color:#999;")
        list_row.addWidget(btn_remove)
        list_row.addWidget(btn_clear)
        list_row.addStretch(1)
        list_row.addWidget(self._count_label)
        sg.addLayout(list_row)
        layout.addWidget(src_group)

        rule_group = QGroupBox("2. 处理规则")
        rg = QVBoxLayout(rule_group)

        self._resize_en = QCheckBox("统一尺寸缩放")
        rg.addWidget(self._resize_en)
        rw = QHBoxLayout()
        rw.addWidget(QLabel("宽"))
        self._rw = QSpinBox()
        self._rw.setRange(1, 10000)
        self._rw.setValue(1280)
        rw.addWidget(self._rw)
        rw.addWidget(QLabel("高"))
        self._rh = QSpinBox()
        self._rh.setRange(1, 10000)
        self._rh.setValue(1280)
        rw.addWidget(self._rh)
        self._keep = QCheckBox("保持比例")
        self._keep.setChecked(True)
        rw.addWidget(self._keep)
        rg.addLayout(rw)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("格式"))
        self._format = QComboBox()
        self._format.addItems(["保持原格式", "JPG", "PNG", "WebP"])
        fmt_row.addWidget(self._format)
        fmt_row.addWidget(QLabel("质量"))
        self._quality = QSlider(Qt.Orientation.Horizontal)
        self._quality.setRange(1, 100)
        self._quality.setValue(90)
        fmt_row.addWidget(self._quality, 1)
        rg.addLayout(fmt_row)

        self._wm_en = QCheckBox("批量添加水印")
        rg.addWidget(self._wm_en)
        wm_row = QHBoxLayout()
        wm_row.addWidget(QLabel("文字"))
        self._wm_text = QLineEdit("© Chovy")
        wm_row.addWidget(self._wm_text)
        wm_row.addWidget(QLabel("大小%"))
        self._wm_size = QSpinBox()
        self._wm_size.setRange(1, 100)
        self._wm_size.setValue(10)
        wm_row.addWidget(self._wm_size)
        rg.addLayout(wm_row)
        layout.addWidget(rule_group)

        out_group = QGroupBox("3. 输出设置")
        og = QVBoxLayout(out_group)
        out_row = QHBoxLayout()
        self._out_dir = QLineEdit()
        self._out_dir.setPlaceholderText("输出文件夹（默认同目录）")
        out_row.addWidget(self._out_dir, 1)
        btn_out = QPushButton("浏览")
        btn_out.clicked.connect(self._pick_out)
        out_row.addWidget(btn_out)
        og.addLayout(out_row)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("前缀"))
        self._prefix = QLineEdit("")
        name_row.addWidget(self._prefix)
        name_row.addWidget(QLabel("后缀"))
        self._suffix = QLineEdit("")
        name_row.addWidget(self._suffix)
        og.addLayout(name_row)
        layout.addWidget(out_group)

        run_row = QHBoxLayout()
        self._btn_run = QPushButton("开始处理")
        self._btn_run.clicked.connect(self._run)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._cancel)
        run_row.addWidget(self._btn_run)
        run_row.addWidget(self._btn_cancel)
        layout.addLayout(run_row)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._result = QListWidget()
        layout.addWidget(self._result, 1)

    def _pick_files(self):
        start = self.app.config.get("last_open_dir", "")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", start,
            "图片文件 (*.jpg *.jpeg *.png *.gif *.bmp *.webp);;所有文件 (*.*)")
        if paths:
            self._add_files(paths)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if folder:
            self._add_files(list_images(folder))
            if not self._out_dir.text():
                self._out_dir.setText(os.path.join(folder, "output"))

    def _add_files(self, paths):
        """把选中的图片追加到批处理列表（按绝对路径去重）。"""
        existing = set(self._files)
        for p in paths:
            ap = os.path.abspath(p)
            if ap in existing:
                continue
            existing.add(ap)
            self._files.append(ap)
            self._file_list.addItem(os.path.basename(ap))
            item = self._file_list.item(self._file_list.count() - 1)
            item.setToolTip(ap)
            item.setData(Qt.ItemDataRole.UserRole, ap)
        self._update_count()

    def _remove_selected(self):
        for item in self._file_list.selectedItems():
            ap = item.data(Qt.ItemDataRole.UserRole)
            if ap in self._files:
                self._files.remove(ap)
            self._file_list.takeItem(self._file_list.row(item))
        self._update_count()

    def _clear_files(self):
        self._files.clear()
        self._file_list.clear()
        self._update_count()

    def _update_count(self):
        self._count_label.setText(f"共 {len(self._files)} 张图片")

    def _pick_out(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if folder:
            self._out_dir.setText(folder)

    def _run(self):
        if not self._files:
            return
        config = {
            "resize_enabled": self._resize_en.isChecked(),
            "resize_width": self._rw.value(),
            "resize_height": self._rh.value(),
            "keep_ratio": self._keep.isChecked(),
            "resize_mode": "fit",
            "format": {0: "keep", 1: "JPEG", 2: "PNG", 3: "WEBP"}[self._format.currentIndex()],
            "quality": self._quality.value(),
            "watermark_enabled": self._wm_en.isChecked(),
            "watermark_text": self._wm_text.text().strip() if self._wm_en.isChecked() else "",
            "watermark_image": "",
            "watermark_size": self._wm_size.value() / 100.0,
            "watermark_opacity": 0.7,
            "watermark_pos": "bottomright",
            "watermark_font": self._default_font(),
            "output_dir": self._out_dir.text().strip(),
            "naming_prefix": self._prefix.text(),
            "naming_suffix": self._suffix.text(),
        }
        self._result.clear()
        self._progress.setMaximum(len(self._files))
        self._progress.setValue(0)
        self._btn_run.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        self._thread = BatchThread(self._files, config)
        self._thread.progress.connect(self._on_progress)
        self._thread.file_done.connect(self._on_file_done)
        self._thread.finished_all.connect(self._on_finished)
        self._thread.start()

    def _default_font(self):
        fonts = get_fonts()
        return fonts[0][1] if fonts else ""

    def _cancel(self):
        if self._thread:
            self._thread.cancel()

    def _on_progress(self, cur, total, name):
        self._progress.setValue(cur)

    def _on_file_done(self, idx, path, success, msg):
        icon = "✔" if success else "✘"
        self._result.addItem(f"{icon} {os.path.basename(path)}")

    def _on_finished(self, ok, fail):
        self._btn_run.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._result.addItem(f"完成：成功 {ok} 张，失败 {fail} 张")


# ---------------------------------------------------------------------------
# 右侧面板容器
# ---------------------------------------------------------------------------

class RightPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setFixedWidth(270)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.adjust = AdjustPanel(app)
        self.filter = FilterPanel(app)
        self.watermark = WatermarkPanel(app)
        self.draw = DrawPanel(app)
        self.batch = BatchPanel(app)
        self.tabs.addTab(self.adjust, "调整")
        self.tabs.addTab(self.filter, "滤镜")
        self.tabs.addTab(self.watermark, "水印")
        self.tabs.addTab(self.draw, "绘制")
        self.tabs.addTab(self.batch, "批处理")
        layout.addWidget(self.tabs)

    def reset(self):
        self.adjust.reset()
        self.filter.reset()
