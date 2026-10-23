# -*- coding: utf-8 -*-
"""批量处理：后台线程运行，不阻塞主界面。"""
from __future__ import annotations

import os

from PIL import Image
from PySide6.QtCore import QThread, Signal

from app import imageops


# 支持的格式映射（输出）
_FORMAT_MAP = {
    "keep": None,
    "JPEG": "JPEG",
    "PNG": "PNG",
    "WEBP": "WEBP",
}

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


def list_images(folder: str) -> list[str]:
    out = []
    try:
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and is_image_file(p):
                out.append(p)
    except OSError:
        pass
    return out


def build_output_path(src_path: str, config: dict) -> str:
    """根据命名规则与目标格式计算输出路径。"""
    folder = config.get("output_dir") or os.path.dirname(src_path)
    stem, ext = os.path.splitext(os.path.basename(src_path))
    fmt = config.get("format", "keep")
    if fmt == "keep":
        # 保持原扩展名；无法写出时（如 gif/bmp 转保存）回退为 png
        out_ext = ext.lower() if ext.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".png"
    else:
        out_ext = { "JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp" }[fmt]

    prefix = config.get("naming_prefix", "") or ""
    suffix = config.get("naming_suffix", "") or ""
    name = prefix + stem + suffix + out_ext
    return os.path.join(folder, name)


def _resize(img: Image.Image, config: dict) -> Image.Image:
    if not config.get("resize_enabled"):
        return img
    w = int(config.get("resize_width", 0) or 0)
    h = int(config.get("resize_height", 0) or 0)
    keep = bool(config.get("keep_ratio", True))
    mode = config.get("resize_mode", "fit")
    if mode == "scale" and config.get("scale_percent"):
        pct = float(config["scale_percent"]) / 100.0
        w = max(1, int(img.width * pct))
        h = max(1, int(img.height * pct))
        keep = True
    if w <= 0 or h <= 0:
        return img
    if keep:
        img = img.copy()
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        return img
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _watermark(img: Image.Image, config: dict) -> Image.Image:
    if not config.get("watermark_enabled"):
        return img
    opacity = float(config.get("watermark_opacity", 0.8))
    text = config.get("watermark_text")
    logo_path = config.get("watermark_image")
    pos = config.get("watermark_pos", "center")
    ratio = float(config.get("watermark_size", 0.25))
    if text:
        size = max(8, int(img.width * ratio))
        font_path = config.get("watermark_font")
        tw, th = imageops.measure_text(text, font_path, size)
        x, y = _resolve_pos(pos, img.size, (tw, th))
        return imageops.add_text_watermark(
            img, text, font_path, size, (255, 255, 255), opacity, (x, y),
            stroke=max(1, size // 16), stroke_color=(0, 0, 0))
    if logo_path and os.path.isfile(logo_path):
        logo = Image.open(logo_path)
        lw = int(img.width * ratio)
        lh = max(1, int(logo.height * (lw / max(1, logo.width))))
        x, y = _resolve_pos(pos, img.size, (lw, lh))
        return imageops.add_image_watermark(img, logo, ratio, opacity, (x, y))
    return img


def _resolve_pos(pos, img_size, box_size):
    iw, ih = img_size
    bw, bh = box_size
    if pos == "topleft":
        return (10, 10)
    if pos == "topright":
        return (iw - bw - 10, 10)
    if pos == "bottomleft":
        return (10, ih - bh - 10)
    if pos == "bottomright":
        return (iw - bw - 10, ih - bh - 10)
    # 默认居中
    return ((iw - bw) // 2, (ih - bh) // 2)


def _save(img: Image.Image, path: str, config: dict) -> None:
    fmt = config.get("format", "keep")
    if fmt == "keep":
        ext = os.path.splitext(path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
        elif ext == ".png":
            fmt = "PNG"
        elif ext == ".webp":
            fmt = "WEBP"
        else:
            fmt = "PNG"
    quality = int(config.get("quality", 90))
    kwargs = {}
    if fmt == "JPEG":
        if img.mode in ("RGBA", "LA", "P"):
            img = _flatten_alpha(img)
        img = img.convert("RGB")
        kwargs["quality"] = quality
    elif fmt == "WEBP":
        kwargs["quality"] = quality
    elif fmt == "PNG":
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, fmt, **kwargs)


def _flatten_alpha(img: Image.Image) -> Image.Image:
    bg = Image.new("RGB", img.size, (255, 255, 255))
    if img.mode == "RGBA":
        bg.paste(img, mask=img.getchannel("A"))
    else:
        bg.paste(img.convert("RGB"))
    return bg


def process_single(src_path: str, config: dict) -> tuple[bool, str]:
    """处理单张图片，返回 (成功, 消息)。"""
    try:
        img = Image.open(src_path)
        img.load()
        img = img.convert("RGBA") if (img.mode == "RGBA" or img.mode == "P") else img.convert("RGB")
        img = _resize(img, config)
        img = _watermark(img, config)
        out_path = build_output_path(src_path, config)
        _save(img, out_path, config)
        return True, out_path
    except Exception as exc:  # noqa: BLE001
        return False, f"{os.path.basename(src_path)}: {exc}"


class BatchThread(QThread):
    progress = Signal(int, int, str)   # 当前序号, 总数, 文件名
    file_done = Signal(int, str, bool, str)  # 序号, 路径, 成功, 消息
    finished_all = Signal(int, int)    # 成功数, 失败数

    def __init__(self, files: list[str], config: dict, parent=None):
        super().__init__(parent)
        self._files = list(files)
        self._config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self._files)
        ok = fail = 0
        for i, path in enumerate(self._files, start=1):
            if self._cancelled:
                break
            self.progress.emit(i, total, os.path.basename(path))
            success, msg = process_single(path, self._config)
            if success:
                ok += 1
            else:
                fail += 1
            self.file_done.emit(i, path, success, msg)
        self.finished_all.emit(ok, fail)
