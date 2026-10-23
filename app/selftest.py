# -*- coding: utf-8 -*-
"""无界面自检：验证核心图像处理、历史、批处理与主窗口控制器。"""
from __future__ import annotations

import os
import tempfile

import numpy as np
from PIL import Image

from app import imageops
from app.history import HistoryManager


def run(window, app) -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    tmpdir = tempfile.mkdtemp(prefix="chovy_test_")

    # 合成测试图与 logo
    h, w = 150, 200
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([x * 1.2, y * 1.6, (x + y) * 0.5], axis=-1).astype(np.uint8)
    img = Image.fromarray(base, "RGB")
    src_path = os.path.join(tmpdir, "src.png")
    img.save(src_path)

    logo = Image.new("RGBA", (60, 30), (255, 0, 0, 180))
    logo_path = os.path.join(tmpdir, "logo.png")
    logo.save(logo_path)

    # ---- imageops：调整 ----
    for key in ("brightness", "contrast", "saturation", "temperature", "exposure"):
        out = imageops.apply_adjustments(img, {key: 25})
        check(f"adjust_{key}", out.size == img.size)
    out = imageops.auto_white_balance(img)
    check("auto_wb", out.size == img.size)
    out = imageops.auto_contrast(img)
    check("auto_contrast", out.size == img.size)
    out = imageops.auto_sharpen(img)
    check("auto_sharpen", out.size == img.size)

    # ---- imageops：滤镜 ----
    for name in imageops.FILTERS:
        out = imageops.apply_filter(img, name, 50)
        check(f"filter_{name}", out.size == img.size and out.mode == img.mode)

    # ---- imageops：几何 ----
    check("crop", imageops.crop(img, (10, 10, 110, 90)).size == (100, 80))
    check("rotate", imageops.rotate(img, 45).size != img.size)
    check("rotate90", imageops.rotate_90(img).size == (h, w))
    check("flip", imageops.flip(img).size == img.size)
    check("resize", imageops.resize(img, 100, 50, keep_ratio=False).size == (100, 50))

    # ---- imageops：水印 ----
    out = imageops.add_text_watermark(img, "测试", "", 24, (255, 255, 255),
                                      0.8, (10, 10))
    check("text_watermark", out.size == img.size)
    out = imageops.add_image_watermark(img, logo, 0.3, 0.7, (20, 20))
    check("image_watermark", out.size == img.size)

    # ---- imageops：绘制 ----
    prims = [
        {"type": "brush", "points": [(0, 0), (50, 50)], "color": (255, 0, 0),
         "width": 4, "opacity": 255},
        {"type": "erase", "points": [(0, 0), (30, 30)], "width": 8},
        {"type": "rect", "p0": (10, 10), "p1": (80, 60), "color": (0, 255, 0), "width": 3},
        {"type": "ellipse", "p0": (20, 20), "p1": (90, 70), "color": (0, 0, 255), "width": 3},
        {"type": "line", "p0": (0, 0), "p1": (100, 100), "color": (255, 255, 0), "width": 2},
        {"type": "arrow", "p0": (0, 0), "p1": (100, 40), "color": (255, 0, 255), "width": 3},
        {"type": "text", "pos": (5, 5), "text": "标注", "font": "", "size": 20,
         "color": (0, 0, 0)},
    ]
    out = imageops.apply_drawings(img, prims)
    check("drawings", out.size == img.size)

    # ---- 历史 ----
    hist = HistoryManager(20)
    img2 = imageops.rotate_90(img)
    hist.push(img)
    restored = hist.undo(img2)
    check("history_undo", restored.size == img.size and hist.can_redo)
    check("history_redo", hist.redo(restored).size == img2.size)

    # ---- 批处理 ----
    from app.batch import build_output_path, list_images, process_single
    check("batch_list", len(list_images(tmpdir)) >= 2)
    cfg = {"output_dir": os.path.join(tmpdir, "out"), "format": "WEBP",
           "quality": 85, "resize_enabled": True, "resize_width": 100,
           "resize_height": 100, "keep_ratio": True, "resize_mode": "fit",
           "watermark_enabled": False, "naming_prefix": "", "naming_suffix": ""}
    ok, msg = process_single(src_path, cfg)
    check("batch_process", ok and os.path.isfile(msg), msg)
    cfg_wm = dict(cfg)
    cfg_wm.update({"watermark_enabled": True, "watermark_text": "测试水印",
                   "watermark_size": 0.15, "watermark_font": "",
                   "watermark_pos": "bottomright"})
    ok2, msg2 = process_single(src_path, cfg_wm)
    check("batch_watermark", ok2 and os.path.isfile(msg2), msg2)

    # ---- 主窗口控制器 ----
    window.open_image(src_path)
    check("win_open", window.base_image is not None
          and window.base_image.size == (w, h))
    window.set_adjust("brightness", 30)
    check("win_adjust", window.adjust_values["brightness"] == 30)
    window.set_filter("grayscale")
    check("win_filter", window.filter_active == "grayscale")
    window.set_filter_strength(50)
    check("win_filter_strength", window.filter_strength == 50)
    window.on_crop((0, 0, 100, 100))
    check("win_crop", window.base_image.size == (100, 100))
    window.undo()
    check("win_undo", window.base_image.size == (w, h))
    window.rotate90(clockwise=True)
    check("win_rotate", window.base_image.size == (h, w))
    window.set_text_watermark("水印", "", 20, (255, 255, 255), 0.8)
    check("win_overlay", window.overlay is not None)
    window.commit_overlay()
    check("win_overlay_commit", window.overlay is None)
    window.on_draw_committed([{"type": "rect", "p0": (0, 0), "p1": (50, 50),
                               "color": (255, 0, 0), "width": 3}])
    check("win_draw", window.base_image is not None)
    out_path = os.path.join(tmpdir, "export.png")
    window._save_to(out_path, "PNG", 90)
    check("win_save", os.path.isfile(out_path) and os.path.getsize(out_path) > 0)
    window._save_to(os.path.join(tmpdir, "export.jpg"), "JPEG", 85)
    check("win_save_jpg", os.path.isfile(os.path.join(tmpdir, "export.jpg")))

    # ---- 缩略图：直接加载返回线程安全的 QImage ----
    from app.sidebar import _load_thumbnail
    thumb = _load_thumbnail(src_path)
    check("thumb_load", thumb is not None and thumb.width() <= 128
          and thumb.width() > 0 and thumb.height() > 0)

    # ---- 缩略图：跨线程信号送达 + 主线程转 QPixmap 生成图标 ----
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    icon_ok = False
    if window.sidebar._current_tab.count() > 0:
        item = window.sidebar._current_tab.item(0)
        icon_ok = not item.icon().isNull()
    check("thumb_icon_delivery", icon_ok)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n自检完成：{passed}/{total} 通过")
    return 0 if passed == total else 1
