# -*- coding: utf-8 -*-
"""
图像处理核心操作：全部基于 Pillow + numpy，纯本地离线运行。

所有函数均以 PIL.Image 为输入/输出，不修改原图，返回新图。
"""
from __future__ import annotations

import io
import math
from typing import Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

Color = Tuple[int, int, int]


def _rgb_float(img: Image.Image) -> np.ndarray:
    """转换为 HxWx3 的 float32 RGB 数组（[0,255]），忽略 alpha。"""
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA")


def _from_rgb(arr: np.ndarray, ref: Image.Image) -> Image.Image:
    """由 RGB 数组还原图像，保留参考图 alpha 通道。"""
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr, "RGB")
    if _has_alpha(ref):
        rgba = out.convert("RGBA")
        rgba.putalpha(ref.getchannel("A"))
        return rgba
    return out


def _blend_rgb(a: Image.Image, b: Image.Image, alpha: float) -> Image.Image:
    """对两个同尺寸图像的 RGB 做线性混合，保留 a 的 alpha。"""
    alpha = max(0.0, min(1.0, alpha))
    if alpha <= 0.0:
        return a.copy()
    if alpha >= 1.0:
        return b.copy()
    aa = _rgb_float(a)
    bb = _rgb_float(b)
    return _from_rgb(aa * (1 - alpha) + bb * alpha, a)


# ---------------------------------------------------------------------------
# 基础调整
# ---------------------------------------------------------------------------

def adjust_brightness(img: Image.Image, value: float) -> Image.Image:
    """value: [-100, 100]，0 为无变化。"""
    factor = max(0.0, 1.0 + value / 100.0)
    return ImageEnhance.Brightness(img).enhance(factor)


def adjust_contrast(img: Image.Image, value: float) -> Image.Image:
    factor = max(0.0, 1.0 + value / 100.0)
    return ImageEnhance.Contrast(img).enhance(factor)


def adjust_saturation(img: Image.Image, value: float) -> Image.Image:
    factor = max(0.0, 1.0 + value / 100.0)
    return ImageEnhance.Color(img).enhance(factor)


def adjust_exposure(img: Image.Image, value: float) -> Image.Image:
    """曝光度：value [-100,100] 映射为约 ±2EV 的线性增益。"""
    stops = value / 100.0 * 2.0
    mult = 2.0 ** stops
    arr = _rgb_float(img) * mult
    return _from_rgb(arr, img)


def adjust_temperature(img: Image.Image, value: float) -> Image.Image:
    """色温：正=偏暖(增红减蓝)，负=偏冷(减红增蓝)。value [-100,100]。"""
    arr = _rgb_float(img)
    delta = value * 0.6
    arr[..., 0] += delta
    arr[..., 2] -= delta
    return _from_rgb(arr, img)


def auto_white_balance(img: Image.Image) -> Image.Image:
    """灰度世界法自动白平衡。"""
    arr = _rgb_float(img)
    means = arr.mean(axis=(0, 1))
    if means.min() < 1e-3:
        return img.copy()
    gains = means.mean() / means
    gains = np.clip(gains, 0.5, 2.0)
    return _from_rgb(arr * gains, img)


def auto_contrast(img: Image.Image) -> Image.Image:
    """2% 截断的直方图拉伸。"""
    return ImageOps.autocontrast(img, cutoff=2)


def auto_sharpen(img: Image.Image) -> Image.Image:
    """一键锐化（USM）。"""
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))


_ADJUST_ORDER = [
    ("brightness", adjust_brightness),
    ("contrast", adjust_contrast),
    ("saturation", adjust_saturation),
    ("temperature", adjust_temperature),
    ("exposure", adjust_exposure),
]


def apply_adjustments(img: Image.Image, values: dict) -> Image.Image:
    """按顺序应用一组参数调节。values 为 {key: value}，value 为 0 时跳过。"""
    out = img
    for key, fn in _ADJUST_ORDER:
        v = values.get(key, 0)
        if v:
            out = fn(out, v)
    return out


# ---------------------------------------------------------------------------
# 滤镜（返回 100% 强度结果，强度混合由 apply_filter 处理）
# ---------------------------------------------------------------------------

FILTERS: dict[str, str] = {
    "grayscale": "黑白",
    "retro": "复古胶片",
    "cool": "冷色调",
    "warm": "暖色调",
    "blur": "高斯模糊",
    "sharpen": "锐化",
    "mosaic": "马赛克",
    "emboss": "浮雕",
    "nostalgic": "怀旧",
    "highcontrast": "高对比",
}


def _sepia(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    nr = 0.393 * r + 0.769 * g + 0.189 * b
    ng = 0.349 * r + 0.686 * g + 0.168 * b
    nb = 0.272 * r + 0.534 * g + 0.131 * b
    return np.stack([nr, ng, nb], axis=-1)


def _grayscale_arr(arr: np.ndarray) -> np.ndarray:
    g = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    return np.stack([g, g, g], axis=-1)


def _desaturate(arr: np.ndarray, amount: float) -> np.ndarray:
    g = _grayscale_arr(arr)
    return arr * (1 - amount) + g * amount


def filter_grayscale(img: Image.Image) -> Image.Image:
    return _from_rgb(_grayscale_arr(_rgb_float(img)), img)


def filter_retro(img: Image.Image) -> Image.Image:
    arr = _sepia(_rgb_float(img))
    arr = arr * 0.92 + 8.0  # 轻微提亮、降对比的胶片感
    arr[..., 0] += 6
    return _from_rgb(arr, img)


def filter_cool(img: Image.Image) -> Image.Image:
    arr = _rgb_float(img)
    arr = _desaturate(arr, 0.15)
    arr[..., 0] -= 15
    arr[..., 2] += 25
    return _from_rgb(arr, img)


def filter_warm(img: Image.Image) -> Image.Image:
    arr = _rgb_float(img)
    arr[..., 0] += 25
    arr[..., 2] -= 15
    return _from_rgb(arr, img)


def filter_blur(img: Image.Image) -> Image.Image:
    radius = max(1.0, min(img.size) / 180.0)
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def filter_sharpen(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))


def filter_mosaic(img: Image.Image) -> Image.Image:
    block = max(2, min(img.size) // 40)
    small = img.resize(
        (max(1, img.width // block), max(1, img.height // block)),
        Image.Resampling.NEAREST,
    )
    return small.resize(img.size, Image.Resampling.NEAREST)


def filter_emboss(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.EMBOSS)


def filter_nostalgic(img: Image.Image) -> Image.Image:
    arr = _rgb_float(img)
    arr = _desaturate(arr, 0.55)
    arr[..., 0] += 20
    arr[..., 1] += 8
    arr[..., 2] -= 12
    arr = arr * 0.9 + 18.0  # 褪色发旧
    return _from_rgb(arr, img)


def filter_highcontrast(img: Image.Image) -> Image.Image:
    arr = _rgb_float(img)
    mean = arr.mean()
    arr = (arr - mean) * 1.8 + mean
    arr = _desaturate(arr, -0.15)  # 略微提高饱和
    return _from_rgb(arr, img)


_FILTER_FN = {
    "grayscale": filter_grayscale,
    "retro": filter_retro,
    "cool": filter_cool,
    "warm": filter_warm,
    "blur": filter_blur,
    "sharpen": filter_sharpen,
    "mosaic": filter_mosaic,
    "emboss": filter_emboss,
    "nostalgic": filter_nostalgic,
    "highcontrast": filter_highcontrast,
}


def apply_filter(img: Image.Image, name: str, strength: float) -> Image.Image:
    """应用指定滤镜并按 0~100 强度与原图混合。"""
    fn = _FILTER_FN.get(name)
    if fn is None:
        return img.copy()
    filtered = fn(img)
    return _blend_rgb(img, filtered, strength / 100.0)


# ---------------------------------------------------------------------------
# 几何变换
# ---------------------------------------------------------------------------

def crop(img: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
    l, t, r, b = [int(round(v)) for v in box]
    l = max(0, min(l, img.width))
    t = max(0, min(t, img.height))
    r = max(l + 1, min(r, img.width))
    b = max(t + 1, min(b, img.height))
    return img.crop((l, t, r, b))


def rotate(img: Image.Image, angle: float, expand: bool = True) -> Image.Image:
    fill = (0, 0, 0, 0) if _has_alpha(img) else (255, 255, 255)
    return img.rotate(-angle, resample=Image.Resampling.BICUBIC,
                      expand=expand, fillcolor=fill)


def rotate_90(img: Image.Image, clockwise: bool = True) -> Image.Image:
    return img.transpose(Image.Transpose.ROTATE_270 if clockwise
                         else Image.Transpose.ROTATE_90)


def flip(img: Image.Image, horizontal: bool = True) -> Image.Image:
    return img.transpose(Image.Transpose.FLIP_LEFT_RIGHT if horizontal
                         else Image.Transpose.FLIP_TOP_BOTTOM)


def resize(img: Image.Image, width: int, height: int,
           keep_ratio: bool = True) -> Image.Image:
    if keep_ratio:
        # 等比缩放：缩放到给定宽高之内并保持比例（允许放大）
        scale = min(width / img.width, height / img.height)
        new_w = max(1, round(img.width * scale))
        new_h = max(1, round(img.height * scale))
        return img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img.resize((width, height), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# 水印
# ---------------------------------------------------------------------------

def _apply_alpha_overlay(base: Image.Image, overlay: Image.Image,
                         opacity: float) -> Image.Image:
    """把带 alpha 的 overlay 按 opacity 合成到 base 上。"""
    opacity = max(0.0, min(1.0, opacity))
    if opacity <= 0.0:
        return base.copy()
    base_rgba = base.convert("RGBA")
    overlay_rgba = overlay.convert("RGBA")
    if opacity < 1.0:
        a = overlay_rgba.getchannel("A").point(lambda v: int(v * opacity))
        overlay_rgba.putalpha(a)
    out = Image.alpha_composite(base_rgba, overlay_rgba)
    return out.convert(base.mode) if base.mode != "RGBA" else out


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font, stroke_width=0)


def add_text_watermark(img: Image.Image, text: str, font_path: str,
                       size: int, color: Color, opacity: float,
                       pos: Tuple[int, int], stroke: int = 0,
                       stroke_color: Color = (0, 0, 0)) -> Image.Image:
    """在 pos（文字左上角，图像坐标）处添加文字水印。"""
    if not text:
        return img.copy()
    try:
        font = ImageFont.truetype(font_path, size)
    except OSError:
        font = ImageFont.load_default()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.text(pos, text, font=font, fill=color + (255,),
           stroke_width=stroke, stroke_fill=stroke_color + (255,) if stroke else None)
    return _apply_alpha_overlay(img, overlay, opacity)


def measure_text(text: str, font_path: str, size: int) -> Tuple[int, int]:
    try:
        font = ImageFont.truetype(font_path, size)
    except OSError:
        font = ImageFont.load_default()
    tmp = Image.new("RGB", (8, 8))
    d = ImageDraw.Draw(tmp)
    box = d.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def add_image_watermark(img: Image.Image, logo: Image.Image,
                        width_ratio: float, opacity: float,
                        pos: Tuple[int, int]) -> Image.Image:
    """在 pos（logo 左上角）处添加图片水印。width_ratio 为相对底图宽度的比例。"""
    base = img.convert("RGBA")
    logo_rgba = logo.convert("RGBA")
    target_w = max(1, int(img.width * width_ratio))
    ratio = target_w / max(1, logo_rgba.width)
    target_h = max(1, int(logo_rgba.height * ratio))
    logo_rgba = logo_rgba.resize((target_w, target_h), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x = int(pos[0])
    y = int(pos[1])
    overlay.alpha_composite(logo_rgba, (x, y))
    out = _apply_alpha_overlay(base, overlay, opacity)
    return out.convert(img.mode) if img.mode != "RGBA" else out


# ---------------------------------------------------------------------------
# 绘制与标注（栅格化到图像）
# ---------------------------------------------------------------------------

def apply_drawings(img: Image.Image,
                   primitives: Sequence[dict]) -> Image.Image:
    """把一组绘制图元栅格化到图像上。

    图元类型：
      brush   {'type':'brush','points':[(x,y)...],'color':(r,g,b),
               'width':w,'opacity':o}
      erase   {'type':'erase','points':[(x,y)...],'width':w}
      rect    {'type':'rect','p0':(x,y),'p1':(x,y),'color':(r,g,b),'width':w}
      ellipse {'type':'ellipse', ...同上}
      line    {'type':'line', ...同上}
      arrow   {'type':'arrow', ...同上}
      text    {'type':'text','pos':(x,y),'text':s,'font':path,'size':n,
               'color':(r,g,b)}
    """
    if not primitives:
        return img.copy()

    has_alpha = _has_alpha(img)
    base = img.convert("RGBA")

    # 画笔/形状画在彩色图层；橡皮擦在透明图上走 alpha 遮罩、在不透明图上走白色
    color_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(color_layer)
    mask = Image.new("L", base.size, 0)
    md = ImageDraw.Draw(mask)

    for p in primitives:
        t = p.get("type")
        if t == "brush":
            pts = [(float(x), float(y)) for x, y in p["points"]]
            col = tuple(int(c) for c in p["color"])
            width = max(1, int(p.get("width", 4)))
            opacity = max(0, min(255, int(p.get("opacity", 255))))
            cd.line(pts, fill=col + (opacity,), width=width, joint="curve")
            # 首尾补圆点，避免单点/端点缺失
            if len(pts) == 1:
                cd.ellipse([pts[0][0] - width / 2, pts[0][1] - width / 2,
                            pts[0][0] + width / 2, pts[0][1] + width / 2],
                           fill=col + (opacity,))
        elif t == "erase":
            pts = [(float(x), float(y)) for x, y in p["points"]]
            width = max(1, int(p.get("width", 12)))
            if has_alpha:
                md.line(pts, fill=255, width=width, joint="curve")
                if len(pts) == 1:
                    md.ellipse([pts[0][0] - width / 2, pts[0][1] - width / 2,
                                pts[0][0] + width / 2, pts[0][1] + width / 2],
                               fill=255)
            else:
                cd.line(pts, fill=(255, 255, 255, 255), width=width, joint="curve")
                if len(pts) == 1:
                    cd.ellipse([pts[0][0] - width / 2, pts[0][1] - width / 2,
                                pts[0][0] + width / 2, pts[0][1] + width / 2],
                               fill=(255, 255, 255, 255))
        elif t in ("rect", "ellipse", "line", "arrow"):
            col = tuple(int(c) for c in p["color"])
            width = max(1, int(p.get("width", 3)))
            p0 = (float(p["p0"][0]), float(p["p0"][1]))
            p1 = (float(p["p1"][0]), float(p["p1"][1]))
            if t == "rect":
                cd.rectangle([p0, p1], outline=col + (255,), width=width)
            elif t == "ellipse":
                cd.ellipse([p0, p1], outline=col + (255,), width=width)
            elif t == "line":
                cd.line([p0, p1], fill=col + (255,), width=width)
            elif t == "arrow":
                _draw_arrow(cd, p0, p1, col, width)
        elif t == "text":
            _draw_text_primitive(color_layer, p)

    # 合成彩色图层
    out = Image.alpha_composite(base, color_layer)
    # 应用橡皮擦遮罩
    if mask.getextrema()[1] > 0:
        alpha = out.getchannel("A")
        alpha = ImageChops.subtract(alpha, mask)
        out.putalpha(alpha)

    return out.convert(img.mode) if img.mode != "RGBA" else out


def _draw_arrow(d: ImageDraw.ImageDraw, p0, p1, color, width):
    import math as _m
    d.line([p0, p1], fill=color + (255,), width=width)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = _m.hypot(dx, dy)
    if length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    head = max(8.0, width * 3.0)
    angle = _m.radians(25)
    for sgn in (1, -1):
        a = _m.atan2(uy, ux) + sgn * (_m.pi - angle)
        ex = p1[0] + head * _m.cos(a)
        ey = p1[1] + head * _m.sin(a)
        d.line([p1, (ex, ey)], fill=color + (255,), width=width)


def _draw_text_primitive(layer: Image.Image, p: dict):
    text = p.get("text", "")
    if not text:
        return
    size = int(p.get("size", 20))
    try:
        font = ImageFont.truetype(p.get("font"), size)
    except (OSError, TypeError):
        font = ImageFont.load_default()
    col = tuple(int(c) for c in p.get("color", (255, 0, 0)))
    d = ImageDraw.Draw(layer)
    d.text((float(p["pos"][0]), float(p["pos"][1])), text,
           font=font, fill=col + (255,))
