#!/usr/bin/env python3
"""
鍥剧墖澶勭悊宸ュ叿 - 姘村嵃銆佹墦鐮併€佽秴鍒?"""

import argparse
import io
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Optional, Tuple, List

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
import numpy as np


def _hidden_subprocess_kwargs() -> dict:
    """Hide child console windows when the GUI launches CLI helpers on Windows."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


# ============== 瓒呭垎閰嶇疆 ==============

UPSCALE_ENGINES = {
    "realesrgan": "Real-ESRGAN",
    "realcugan": "Real-CUGAN",
    "apisr": "APISR",
}

UPSCALE_MODELS = {
    "realesrgan": [
        "RealESRGAN_x4plus_anime_6B.pth",
        "RealESRGAN_x4plus.pth",
        "RealESRGAN_x2plus.pth",
    ],
    "realcugan": [
        "RealCUGAN-se",
        "RealCUGAN-pro",
    ],
    "apisr": [
        "APISR-RRDB",
    ],
}

UPSCALE_SCALE_OPTIONS = {
    "realesrgan": [2, 4],
    "realcugan": [2, 3, 4],
    "apisr": [2, 4],
}


def normalize_upscale_engine(engine: Optional[str]) -> str:
    """鏍囧噯鍖栬秴鍒嗗紩鎿庡悕绉般€?"""
    if not engine:
        return "realesrgan"

    value = engine.strip().lower().replace("_", "-")
    aliases = {
        "realesrgan": "realesrgan",
        "real-esrgan": "realesrgan",
        "esrgan": "realesrgan",
        "realcugan": "realcugan",
        "real-cugan": "realcugan",
        "cugan": "realcugan",
        "apisr": "apisr",
    }
    if value not in aliases:
        raise ValueError(f"涓嶆敮鎸佺殑瓒呭垎寮曟搸: {engine}")
    return aliases[value]


def get_upscale_models(engine: str) -> List[str]:
    """杩斿洖鎸囧畾寮曟搸鏀寔鐨勬ā鍨嬪垪琛ㄣ€?"""
    normalized = normalize_upscale_engine(engine)
    return UPSCALE_MODELS[normalized]


def get_upscale_scale_options(engine: str) -> List[int]:
    """杩斿洖鎸囧畾寮曟搸鏀寔鐨勫€嶇巼鍒楄〃銆?"""
    normalized = normalize_upscale_engine(engine)
    return UPSCALE_SCALE_OPTIONS[normalized]


def get_default_upscale_model(engine: str) -> str:
    """杩斿洖鎸囧畾寮曟搸鐨勯粯璁ゆā鍨嬨€?"""
    return get_upscale_models(engine)[0]


# ============== 閰嶇疆 ==============

CONFIG = {
    # 瀛椾綋閰嶇疆
    "font_url": "https://github.com/google/fonts/raw/main/ofl/dancingscript/DancingScript%5Bwght%5D.ttf",
    "font_name": "DancingScript.ttf",

    # 榫欏浘鏍?(浣跨敤 Twemoji 鐨勯緳 SVG)
    "dragon_icon_url": "https://raw.githubusercontent.com/twitter/twemoji/master/assets/svg/1f409.svg",
    "dragon_icon_name": "dragon.svg",

    # 榛樿姘村嵃閰嶇疆
    "watermark_defaults": {
        "text": "YourName",
        "font_size": 48,
        "color": [255, 255, 255],
        "opacity": 0.6,
        "position": "bottom-right",  # center, top-left, top-right, bottom-left, bottom-right
        "margin": 30,
        "rotation_range": [-10, 10],  # 闅忔満鏃嬭浆瑙掑害鑼冨洿
        "offset_range": [-15, 15],    # 闅忔満鍋忕Щ鑼冨洿锛堝儚绱狅級
        "icon_scale": 0.8,            # icon/text size ratio
    },

    # 鐩綍閰嶇疆
    "assets_dir": Path(__file__).parent / "assets",
    "fonts_dir": Path(__file__).parent / "fonts",
}

FONT_FILE_SUFFIXES = {".ttf", ".otf", ".ttc"}
COMMON_WATERMARK_FONTS = [
    ("Microsoft YaHei", Path("C:/Windows/Fonts/msyh.ttc")),
    ("DengXian", Path("C:/Windows/Fonts/Deng.ttf")),
    ("SimHei", Path("C:/Windows/Fonts/simhei.ttf")),
    ("SimSun", Path("C:/Windows/Fonts/simsun.ttc")),
    ("KaiTi", Path("C:/Windows/Fonts/simkai.ttf")),
    ("FangSong", Path("C:/Windows/Fonts/simfang.ttf")),
    ("Segoe UI", Path("C:/Windows/Fonts/segoeui.ttf")),
    ("Bahnschrift", Path("C:/Windows/Fonts/bahnschrift.ttf")),
    ("Arial", Path("C:/Windows/Fonts/arial.ttf")),
    ("Georgia", Path("C:/Windows/Fonts/georgia.ttf")),
]


# ============== 宸ュ叿鍑芥暟 ==============

def ensure_dir(path: Path):
    """纭繚鐩綍瀛樺湪"""
    path.mkdir(parents=True, exist_ok=True)


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> bool:
    """涓嬭浇鏂囦欢"""
    if dest.exists():
        return True

    print(f"[涓嬭浇] {url} -> {dest}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"[閿欒] 涓嬭浇澶辫触: {e}")
        if dest.exists():
            dest.unlink()
        return False


def get_font_path() -> Optional[Path]:
    """鑾峰彇瀛椾綋璺緞锛屼笉瀛樺湪鍒欎笅杞?"""
    ensure_dir(CONFIG["fonts_dir"])
    font_path = CONFIG["fonts_dir"] / CONFIG["font_name"]

    if not font_path.exists():
        success = download_file(CONFIG["font_url"], font_path)
        if not success:
            # 浣跨敤绯荤粺榛樿瀛椾綋浣滀负鍚庡
            return None

    return font_path


def resolve_watermark_font_path(font_value: Optional[str] = None, fallback: Optional[Path] = None) -> Optional[Path]:
    """Resolve watermark font path from custom value or fallback default."""
    raw = str(font_value or "").strip()
    if not raw:
        return fallback if fallback is not None else get_font_path()

    candidate = Path(raw).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(f"找不到字体文件: {candidate}")
    if candidate.suffix.lower() not in FONT_FILE_SUFFIXES:
        raise ValueError("仅支持 TTF / OTF / TTC 字体文件")
    return candidate


def get_watermark_font_options() -> List[dict]:
    """Return selectable watermark font options for GUI/frontends."""
    ensure_dir(CONFIG["fonts_dir"])
    options: List[dict] = [{"value": "", "label": "默认：Dancing Script"}]
    seen = {""}

    for path in sorted(CONFIG["fonts_dir"].glob("*")):
        if path.is_file() and path.suffix.lower() in FONT_FILE_SUFFIXES:
            value = str(path)
            if value not in seen:
                options.append({"value": value, "label": f"项目字体：{path.stem}"})
                seen.add(value)

    for label, path in COMMON_WATERMARK_FONTS:
        if path.exists():
            value = str(path)
            if value not in seen:
                options.append({"value": value, "label": label})
                seen.add(value)

    return options


def get_dragon_icon_path() -> Optional[Path]:
    """鑾峰彇榫欏浘鏍囪矾寰勶紝涓嶅瓨鍦ㄥ垯涓嬭浇"""
    ensure_dir(CONFIG["assets_dir"])
    icon_path = CONFIG["assets_dir"] / CONFIG["dragon_icon_name"]

    if not icon_path.exists():
        success = download_file(CONFIG["dragon_icon_url"], icon_path)
        if not success:
            return None

    return icon_path


def svg_to_png(svg_path: Path, size: Tuple[int, int]) -> Optional[Image.Image]:
    """Render the SVG icon to a PNG image, falling back gracefully when Cairo is unavailable."""
    try:
        import cairosvg
        png_data = cairosvg.svg2png(url=str(svg_path), output_width=size[0], output_height=size[1])
        return Image.open(io.BytesIO(png_data))
    except ImportError:
        return render_emoji_dragon(size)
    except Exception as e:
        try:
            print(f"[WARN] SVG icon fallback: {e}")
        except Exception:
            print("[WARN] SVG icon fallback")
        return render_emoji_dragon(size)


def render_emoji_dragon(size: Tuple[int, int]) -> Image.Image:
    """浣跨敤 emoji 娓叉煋榫欏浘鏍囦綔涓哄悗澶?"""
    # 鍒涘缓涓€涓€忔槑鍥惧儚
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 灏濊瘯浣跨敤绯荤粺瀛椾綋娓叉煋 馃悏 emoji
    emoji_size = min(size)
    try:
        # 灏濊瘯浣跨敤绯荤粺 emoji 瀛椾綋
        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  # Linux
            "/System/Library/Fonts/Apple Color Emoji.ttc",         # macOS
            "C:/Windows/Fonts/seguiemj.ttf",                       # Windows
        ]
        font = None
        for fp in font_paths:
            if os.path.exists(fp):
                font = ImageFont.truetype(fp, emoji_size)
                break

        if font is None:
            # 浣跨敤榛樿瀛椾綋
            font = ImageFont.load_default()

        # 缁樺埗 emoji
        bbox = draw.textbbox((0, 0), "馃悏", font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2
        draw.text((x, y), "馃悏", font=font, embedded_color=True)
    except Exception:
        # 濡傛灉澶辫触锛岀粯鍒朵竴涓畝鍗曠殑榫欏舰鍥炬
        draw_dragon_shape(draw, size)

    return img


def draw_dragon_shape(draw: ImageDraw.ImageDraw, size: Tuple[int, int]):
    """缁樺埗绠€鍗曠殑榫欏舰鐘朵綔涓烘渶鍚庣殑鍚庡"""
    w, h = size
    # 绠€鍖栫殑榫欒韩鏇茬嚎
    color = (255, 100, 50, 200)
    # 韬綋
    draw.ellipse([w*0.2, h*0.4, w*0.8, h*0.7], fill=color)
    # 澶?
    draw.ellipse([w*0.6, h*0.2, w*0.9, h*0.5], fill=color)
    # 灏惧反
    draw.polygon([(w*0.2, h*0.55), (0, h*0.3), (w*0.1, h*0.6)], fill=color)
    # 瑙?
    draw.polygon([(w*0.75, h*0.25), (w*0.7, h*0.1), (w*0.8, h*0.2)], fill=(255, 150, 50, 200))


def create_dragon_icon(size: int) -> Optional[Image.Image]:
    """鍒涘缓榫欏浘鏍?"""
    icon_path = get_dragon_icon_path()
    if icon_path and icon_path.exists():
        return svg_to_png(icon_path, (size, size))
    return render_emoji_dragon((size, size))


# ============== 鏍稿績鍔熻兘 ==============

class WatermarkProcessor:
    """姘村嵃澶勭悊鍣?"""

    def __init__(self, config: dict = None):
        self.config = {**CONFIG["watermark_defaults"], **(config or {})}
        self.default_font_path = get_font_path()

    def process(self, input_path: Path, output_path: Path, **overrides):
        """澶勭悊鍗曞紶鍥剧墖"""
        config = {**self.config, **overrides}

        # 鎵撳紑鍥剧墖
        img = Image.open(input_path)

        # 杞崲涓?RGBA 浠ユ敮鎸侀€忔槑搴?
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # 鑾峰彇鍥剧墖灏哄
        img_width, img_height = img.size

        # 璁＄畻瀛椾綋澶у皬锛堝熀浜庡浘鐗囬珮搴︼級
        font_size = config.get('font_size', 48)
        if isinstance(font_size, float) and font_size <= 1.0:
            font_size = int(img_height * font_size)

        # 鍔犺浇瀛椾綋
        selected_font_path = resolve_watermark_font_path(config.get('font_path'), self.default_font_path)
        try:
            font = ImageFont.truetype(str(selected_font_path), font_size) if selected_font_path else ImageFont.load_default()
        except OSError:
            font = ImageFont.load_default()

        # 鑾峰彇鏂囧瓧灏哄
        text = config['text']
        temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # 纯文字水印：不再尝试加载龙图标，避免 Cairo / emoji 环境差异影响主功能
        total_width = text_width
        total_height = text_height

        # 计算基础位置
        margin = config['margin']
        position = config['position']

        if position == 'center':
            base_x = (img_width - total_width) // 2
            base_y = (img_height - total_height) // 2
        elif position == 'top-left':
            base_x = margin
            base_y = margin
        elif position == 'top-right':
            base_x = img_width - total_width - margin
            base_y = margin
        elif position == 'bottom-left':
            base_x = margin
            base_y = img_height - total_height - margin
        else:  # bottom-right
            base_x = img_width - total_width - margin
            base_y = img_height - total_height - margin

        # 添加随机偏移
        offset_range = config.get('offset_range', [-15, 15])
        offset_x = random.randint(offset_range[0], offset_range[1])
        offset_y = random.randint(offset_range[0], offset_range[1])
        final_x = max(0, min(img_width - total_width, base_x + offset_x))
        final_y = max(0, min(img_height - total_height, base_y + offset_y))

        # 创建水印层
        watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)

        # 绘制文字
        color = tuple(config['color']) + (int(255 * config['opacity']),)
        draw.text((final_x, final_y), text, font=font, fill=color)

        # 鏃嬭浆
        rotation_range = config.get('rotation_range', [-10, 10])
        rotation = random.uniform(rotation_range[0], rotation_range[1])
        if rotation != 0:
            watermark = watermark.rotate(rotation, expand=False, resample=Image.BICUBIC)

        # 鍚堝苟
        img = Image.alpha_composite(img, watermark)

        # 杞崲鍥?RGB锛堝幓闄ら€忔槑閫氶亾锛?
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background

        # 淇濆瓨锛堝幓闄ゆ墍鏈?metadata锛?
        img.save(output_path, 'JPEG', quality=95, optimize=True)
        print(f"[瀹屾垚] 姘村嵃宸叉坊鍔? {output_path}")

        return output_path


class MosaicProcessor:
    """椹禌鍏?妯＄硦澶勭悊鍣?"""

    @staticmethod
    def _normalize_region(region, default_mode: str, kwargs: dict) -> dict:
        if isinstance(region, dict):
            mode = str(region.get("mode") or default_mode or "pixelate").lower()
            shape = str(region.get("shape") or "rect").lower()
            pixel_size = int(region.get("pixel_size") or kwargs.get("pixel_size", 10))
            blur_radius = int(region.get("blur_radius") or kwargs.get("radius", 15))
            brush_size = int(region.get("brush_size") or 32)
            points = []
            if shape == "brush" and isinstance(region.get("points"), list):
                for point in region.get("points", []):
                    if isinstance(point, dict):
                        points.append((int(point.get("x", 0)), int(point.get("y", 0))))
                    else:
                        px, py = point
                        points.append((int(px), int(py)))
            if points:
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                x1 = min(xs) - brush_size
                y1 = min(ys) - brush_size
                x2 = max(xs) + brush_size
                y2 = max(ys) + brush_size
            else:
                x1 = int(region.get("x1", 0))
                y1 = int(region.get("y1", 0))
                x2 = int(region.get("x2", 0))
                y2 = int(region.get("y2", 0))
        else:
            x1, y1, x2, y2 = (int(v) for v in region)
            mode = default_mode
            shape = "rect"
            pixel_size = int(kwargs.get("pixel_size", 10))
            blur_radius = int(kwargs.get("radius", 15))
            brush_size = 32
            points = []

        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if shape not in {"rect", "rounded", "ellipse", "triangle", "brush"}:
            shape = "rect"
        if mode not in {"pixelate", "blur"}:
            mode = default_mode if default_mode in {"pixelate", "blur"} else "pixelate"
        return {
            "box": (left, top, right, bottom),
            "mode": mode,
            "shape": shape,
            "pixel_size": max(2, pixel_size),
            "blur_radius": max(1, blur_radius),
            "brush_size": max(1, brush_size),
            "points": points,
        }

    @staticmethod
    def _paste_region(img: Image.Image, region_img: Image.Image, box: Tuple[int, int, int, int], shape: str,
                      points=None, brush_size: int = 32) -> None:
        x1, y1, x2, y2 = box
        if shape == "rect":
            img.paste(region_img, (x1, y1))
            return

        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        if shape == "ellipse":
            draw.ellipse((0, 0, width - 1, height - 1), fill=255)
        elif shape == "triangle":
            draw.polygon(((width // 2, 0), (width - 1, height - 1), (0, height - 1)), fill=255)
        elif shape == "brush":
            relative_points = [(int(px - x1), int(py - y1)) for px, py in (points or [])]
            if len(relative_points) >= 2:
                draw.line(relative_points, fill=255, width=max(1, int(brush_size)), joint="curve")
            for px, py in relative_points:
                radius = max(1, int(brush_size) // 2)
                draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=255)
        else:
            radius = max(4, int(min(width, height) * 0.18))
            draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        img.paste(region_img, (x1, y1), mask)

    @staticmethod
    def pixelate(img: Image.Image, region: Tuple[int, int, int, int], pixel_size: int = 10, shape: str = "rect",
                 points=None, brush_size: int = 32) -> Image.Image:
        """鍍忕礌椹禌鍏?"""
        x1, y1, x2, y2 = region
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.width, x2), min(img.height, y2)
        if x2 <= x1 or y2 <= y1:
            return img
        region_img = img.crop((x1, y1, x2, y2))

        # 缂╁皬鍐嶆斁澶?
        small = region_img.resize(
            (max(1, (x2 - x1) // pixel_size), max(1, (y2 - y1) // pixel_size)),
            Image.NEAREST
        )
        pixelated = small.resize((x2 - x1, y2 - y1), Image.NEAREST)

        MosaicProcessor._paste_region(img, pixelated, (x1, y1, x2, y2), shape, points=points, brush_size=brush_size)
        return img

    @staticmethod
    def gaussian_blur(img: Image.Image, region: Tuple[int, int, int, int], radius: int = 15, shape: str = "rect",
                      points=None, brush_size: int = 32) -> Image.Image:
        """楂樻柉妯＄硦"""
        x1, y1, x2, y2 = region
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.width, x2), min(img.height, y2)
        if x2 <= x1 or y2 <= y1:
            return img
        region_img = img.crop((x1, y1, x2, y2))
        blurred = region_img.filter(ImageFilter.GaussianBlur(radius=radius))
        MosaicProcessor._paste_region(img, blurred, (x1, y1, x2, y2), shape, points=points, brush_size=brush_size)
        return img

    def process(self, input_path: Path, output_path: Path,
                regions: List,
                mode: str = "pixelate", **kwargs):
        """澶勭悊鍗曞紶鍥剧墖

        Args:
            regions: 鍒楄〃 [(x1, y1, x2, y2), ...]
            mode: "pixelate" 鎴?"blur"
        """
        img = Image.open(input_path)

        if img.mode != 'RGB':
            img = img.convert('RGB')

        for raw_region in regions:
            region = self._normalize_region(raw_region, mode, kwargs)
            if region["box"][2] <= region["box"][0] or region["box"][3] <= region["box"][1]:
                continue
            if region["mode"] == "pixelate":
                img = self.pixelate(
                    img, region["box"], region["pixel_size"], shape=region["shape"],
                    points=region["points"], brush_size=region["brush_size"],
                )
            elif region["mode"] == "blur":
                img = self.gaussian_blur(
                    img, region["box"], region["blur_radius"], shape=region["shape"],
                    points=region["points"], brush_size=region["brush_size"],
                )

        # 淇濆瓨锛堝幓闄?metadata锛?
        img.save(output_path, 'JPEG', quality=95, optimize=True)
        print(f"[瀹屾垚] 鎵撶爜宸插簲鐢? {output_path}")

        return output_path


class RealESRGANUpscaler:
    """Real-ESRGAN 瓒呭垎澶勭悊鍣?- 鑷姩涓嬭浇妯″瀷锛屾敮鎸?8GB 鏄惧瓨"""

    MODEL_URLS = {
        "RealESRGAN_x4plus.pth": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "RealESRGAN_x4plus_anime_6B.pth": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        "RealESRGAN_x2plus.pth": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
    }
    MODEL_DIR_ENV_VARS = (
        "REAL_ESRGAN_MODEL_DIR",
        "UPSCALE_MODEL_DIR",
        "COMFYUI_MODEL_DIR",
        "COMFYUI_PATH",
    )
    COMMON_MODEL_SUBDIRS = (
        Path("models"),
        Path("models/upscale_models"),
        Path("models/ESRGAN"),
        Path("models/RealESRGAN"),
        Path("ComfyUI/models/upscale_models"),
        Path("ComfyUI/models/ESRGAN"),
        Path("ComfyUI/models/RealESRGAN"),
    )

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = Path(models_dir) if models_dir else Path(__file__).parent / "models"
        ensure_dir(self.models_dir)
        self.model = None
        self.upsampler = None
        self.current_model_name = None
        self._resolved_model_cache = {}

    def _ensure_torchvision_compat(self):
        """Provide the legacy torchvision.functional_tensor module expected by older basicsr builds."""
        if importlib.util.find_spec("torchvision.transforms.functional_tensor") is not None:
            return

        try:
            import torchvision.transforms.functional as tv_functional
        except Exception:
            return

        shim = types.ModuleType("torchvision.transforms.functional_tensor")
        shim.rgb_to_grayscale = tv_functional.rgb_to_grayscale
        sys.modules["torchvision.transforms.functional_tensor"] = shim

    def _dedupe_paths(self, paths: List[Path]) -> List[Path]:
        unique = []
        seen = set()
        for raw_path in paths:
            if raw_path is None:
                continue

            try:
                path = Path(raw_path).expanduser()
                key = str(path.resolve(strict=False)).lower()
            except Exception:
                continue

            if key in seen:
                continue

            seen.add(key)
            unique.append(path)

        return unique

    def _iter_search_roots(self) -> List[Path]:
        roots = [
            self.models_dir,
            Path.cwd() / "models",
            Path(__file__).resolve().parent / "models",
            Path.home() / "ComfyUI",
            Path("D:/comfyui"),
        ]

        for env_name in self.MODEL_DIR_ENV_VARS:
            raw_value = os.environ.get(env_name, "")
            if not raw_value:
                continue
            for part in raw_value.split(os.pathsep):
                part = part.strip()
                if part:
                    roots.append(Path(part))

        return self._dedupe_paths(roots)

    def _iter_candidate_model_dirs(self) -> List[Path]:
        directories = []
        recursive_roots = []

        for root in self._iter_search_roots():
            directories.append(root)
            for subdir in self.COMMON_MODEL_SUBDIRS:
                directories.append(root / subdir)

            root_name = root.name.lower()
            if "comfyui" in root_name:
                recursive_roots.append(root)

        for root in self._dedupe_paths(recursive_roots):
            if not root.exists() or not root.is_dir():
                continue

            for folder_name in ("upscale_models", "ESRGAN", "RealESRGAN"):
                try:
                    directories.extend(path for path in root.rglob(folder_name) if path.is_dir())
                except OSError:
                    continue

        return [path for path in self._dedupe_paths(directories) if path.exists() and path.is_dir()]

    def resolve_model_path(self, model_name: str) -> Optional[Path]:
        if model_name in self._resolved_model_cache:
            return self._resolved_model_cache[model_name]

        candidate = Path(model_name).expanduser()
        direct_candidates = [candidate]
        if not candidate.is_absolute():
            direct_candidates.append(Path.cwd() / candidate)
            direct_candidates.append(Path(__file__).resolve().parent / candidate)

        for path in self._dedupe_paths(direct_candidates):
            if path.exists() and path.is_file():
                resolved = path.resolve()
                self._resolved_model_cache[model_name] = resolved
                return resolved

        model_filename = candidate.name
        for directory in self._iter_candidate_model_dirs():
            path = directory / model_filename
            if path.exists() and path.is_file():
                resolved = path.resolve()
                self._resolved_model_cache[model_name] = resolved
                return resolved

        self._resolved_model_cache[model_name] = None
        return None

    def _print_model_search_hint(self, model_name: str):
        search_dirs = self._iter_candidate_model_dirs()
        preview_dirs = [str(path) for path in search_dirs[:5]]
        print("[Hint] Put the Real-ESRGAN .pth file in one of these folders, or pass a full local path with -m/--model:")
        for path in preview_dirs:
            print(f"  - {path}")
        if len(search_dirs) > len(preview_dirs):
            print(f"  - ... and {len(search_dirs) - len(preview_dirs)} more detected model folders")
        print(f"[Hint] Expected filename: {Path(model_name).name}")

    def download_model(self, model_name: str) -> Optional[Path]:
        """涓嬭浇妯″瀷鏂囦欢"""
        resolved_model_path = self.resolve_model_path(model_name)
        if resolved_model_path is not None:
            if resolved_model_path.parent != self.models_dir.resolve():
                print(f"[Info] Using local Real-ESRGAN weights: {resolved_model_path}")
            return resolved_model_path

        candidate = Path(model_name).expanduser()
        is_explicit_path = candidate.is_absolute() or len(candidate.parts) > 1
        if is_explicit_path:
            print(f"[Error] Local model file not found: {candidate}")
            self._print_model_search_hint(model_name)
            return None

        if model_name not in self.MODEL_URLS:
            print(f"[閿欒] 鏈煡妯″瀷: {model_name}")
            self._print_model_search_hint(model_name)
            return None

        model_path = self.models_dir / Path(model_name).name
        url = self.MODEL_URLS[model_name]
        print(f"[涓嬭浇] {model_name}...")

        try:
            import urllib.request
            import ssl

            # 绂佺敤 SSL 楠岃瘉锛堟煇浜?Windows 鐜闇€瑕侊級
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ssl_context)
            )
            urllib.request.install_opener(opener)

            def report_hook(block_num, block_size, total_size):
                downloaded = block_num * block_size
                percent = min(downloaded * 100 / total_size, 100)
                print(f"\r杩涘害: {percent:.1f}%", end="")

            urllib.request.urlretrieve(url, model_path, reporthook=report_hook)
            print()
            print(f"[瀹屾垚] 妯″瀷宸蹭繚瀛? {model_path}")
            return model_path

        except Exception as e:
            print(f"\n[閿欒] 涓嬭浇澶辫触: {e}")
            if model_path.exists():
                model_path.unlink()
            self._print_model_search_hint(model_name)
            return None

    def load_model(self, model_name: str = "RealESRGAN_x4plus_anime_6B.pth", device: str = "cuda"):
        """鍔犺浇妯″瀷"""
        self._ensure_torchvision_compat()

        try:
            from basicsr.archs.rrdbnet_arch import RRDBNet
            from realesrgan import RealESRGANer
        except ImportError:
            print("[瀹夎] 姝ｅ湪瀹夎 Real-ESRGAN...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "realesrgan", "basicsr"],
                **_hidden_subprocess_kwargs(),
            )
            self._ensure_torchvision_compat()
            from basicsr.archs.rrdbnet_arch import RRDBNet
            from realesrgan import RealESRGANer

        model_path = self.download_model(model_name)
        if not model_path:
            return False

        model_key = str(model_path.resolve())
        if self.upsampler is not None and self.current_model_name == model_key:
            return True

        print(f"[鍔犺浇] {model_name}...")

        if "anime_6B" in model_name:
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
            netscale = 4
        elif "x2" in model_name:
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
            netscale = 2
        else:
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
            netscale = 4

        self.upsampler = RealESRGANer(
            scale=netscale,
            model_path=str(model_path),
            model=model,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=True,
            device=device,
        )

        self.current_model_name = model_key
        self.netscale = netscale
        print(f"[瀹屾垚] 妯″瀷鍔犺浇鎴愬姛")
        return True

    def process(self, input_path: Path, output_path: Path,
                scale: int = None, model_name: str = None) -> Optional[Path]:
        """杩涜瓒呭垎"""

        # 閫夋嫨妯″瀷
        if model_name is None:
            # 鏍规嵁鍥剧墖绫诲瀷鑷姩閫夋嫨
            model_name = "RealESRGAN_x4plus_anime_6B.pth"  # 浜屾鍏冧笓鐢?
        # 鍔犺浇妯″瀷
        if not self.load_model(model_name):
            return None

        try:
            # 璇诲彇鍥剧墖
            img = Image.open(input_path).convert('RGB')

            print(f"[澶勭悊] {input_path.name} ({img.size[0]}x{img.size[1]}) -> 瓒呭垎涓?..")

            # 瓒呭垎
            output_img, _ = self.upsampler.enhance(
                np.array(img),
                outscale=scale or self.netscale
            )

            # 淇濆瓨
            output_img = Image.fromarray(output_img)
            output_path = Path(output_path)

            if output_path.suffix.lower() in ['.jpg', '.jpeg']:
                output_img.save(output_path, 'JPEG', quality=95, optimize=True)
            else:
                output_img.save(output_path, 'PNG')

            print(f"[瀹屾垚] 瓒呭垎瀹屾垚: {output_path} ({output_img.size[0]}x{output_img.size[1]})")
            return output_path

        except Exception as e:
            print(f"[閿欒] 瓒呭垎澶辫触: {e}")
            import traceback
            traceback.print_exc()
            return None

    def process_batch(self, input_dir: Path, output_dir: Path,
                      pattern: str = "*"):
        """鎵归噺澶勭悊"""
        ensure_dir(output_dir)

        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        images = [f for f in input_dir.iterdir()
                  if f.is_file() and f.suffix.lower() in image_extensions]

        print(f"[Info] Found {len(images)} image(s)")

        for i, img_path in enumerate(images, 1):
            print(f"\n[{i}/{len(images)}] 澶勭悊: {img_path.name}")
            output_path = output_dir / f"{img_path.stem}_upscaled.png"
            self.process(img_path, output_path)

        print(f"\n[瀹屾垚] 鎵€鏈夊浘鐗囧凡淇濆瓨鍒? {output_dir}")

class Final2xUpscaler:
    """Final2x-core 灏佽锛氭敮鎸?Real-CUGAN / APISR銆?"""

    SUPPORTED_MODELS = {"RealCUGAN-se", "RealCUGAN-pro", "APISR-RRDB"}

    REALCUGAN_MODEL_MAP = {
        "RealCUGAN-se": {
            2: {
                -1: "RealCUGAN_Conservative_2x.pth",
                0: "RealCUGAN_No_Denoise_2x.pth",
                1: "RealCUGAN_Denoise1x_2x.pth",
                2: "RealCUGAN_Denoise2x_2x.pth",
                3: "RealCUGAN_Denoise3x_2x.pth",
            },
            3: {
                -1: "RealCUGAN_Conservative_3x.pth",
                0: "RealCUGAN_No_Denoise_3x.pth",
                3: "RealCUGAN_Denoise3x_3x.pth",
            },
            4: {
                -1: "RealCUGAN_Conservative_4x.pth",
                0: "RealCUGAN_No_Denoise_4x.pth",
                3: "RealCUGAN_Denoise3x_4x.pth",
            },
        },
        "RealCUGAN-pro": {
            2: {
                -1: "RealCUGAN_Pro_Conservative_2x.pth",
                0: "RealCUGAN_Pro_No_Denoise_2x.pth",
                3: "RealCUGAN_Pro_Denoise3x_2x.pth",
            },
            3: {
                -1: "RealCUGAN_Pro_Conservative_3x.pth",
                0: "RealCUGAN_Pro_No_Denoise_3x.pth",
                3: "RealCUGAN_Pro_Denoise3x_3x.pth",
            },
        },
    }

    APISR_MODEL_MAP = {
        2: "RealESRGAN_APISR_RRDB_GAN_generator_2x.pth",
        4: "RealESRGAN_APISR_RRDB_GAN_generator_4x.pth",
    }

    def __init__(self):
        self.runner_cmd = None
        self._direct_model = None
        self._direct_model_key = None

    def ensure_ready(self) -> bool:
        """纭繚 Final2x-core 鍙敤銆?"""
        if importlib.util.find_spec("Final2x_core") is None and importlib.util.find_spec("cccv") is None:
            print("[瀹夎] 姝ｅ湪瀹夎 Final2x-core锛圧eal-CUGAN/APISR 鍚庣锛?..")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "Final2x-core"],
                **_hidden_subprocess_kwargs(),
            )

        self.runner_cmd = self._resolve_runner()
        return importlib.util.find_spec("cccv") is not None or self.runner_cmd is not None

    def _resolve_runner(self) -> Optional[List[str]]:
        """鎺㈡祴鍙墽琛屽叆鍙ｏ紙Windows 鑴氭湰鎴?python -m锛夈€?"""
        if self.runner_cmd:
            return self.runner_cmd

        script_dir = Path(sys.executable).parent
        candidates = [
            [str(script_dir / "Final2x-core.exe")],
            [str(script_dir / "Final2x-core")],
            ["Final2x-core"],
            ["final2x-core"],
            [sys.executable, "-m", "Final2x_core"],
        ]

        for cmd in candidates:
            try:
                result = subprocess.run(
                    cmd + ["--help"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    **_hidden_subprocess_kwargs(),
                )
                if result.returncode in (0, 1):
                    return cmd
            except (FileNotFoundError, OSError):
                continue

        return None

    def _resolve_pretrained_model_name(self, model_name: str, scale: int, noise: int) -> str:
        """鏍规嵁 UI 鍙嬪ソ鍙傛暟鏄犲皠鍒?Final2x-core 鐨?ConfigType 鍚嶇О銆?"""
        if model_name == "APISR-RRDB":
            if scale not in self.APISR_MODEL_MAP:
                raise ValueError("APISR-RRDB 浠呮敮鎸?2x/4x")
            return self.APISR_MODEL_MAP[scale]

        if model_name.startswith("RealCUGAN"):
            if model_name not in self.REALCUGAN_MODEL_MAP:
                raise ValueError(f"鏈煡 Real-CUGAN 妯″瀷: {model_name}")

            scale_map = self.REALCUGAN_MODEL_MAP[model_name]
            if scale not in scale_map:
                supported_scales = sorted(scale_map.keys())
                raise ValueError(f"{model_name} 浠呮敮鎸佸€嶇巼: {supported_scales}")

            noise_map = scale_map[scale]
            if noise not in noise_map:
                supported_noise = sorted(noise_map.keys())
                raise ValueError(
                    f"{model_name} 鍦?{scale}x 涓嬩粎鏀寔闄嶅櫔: {supported_noise}"
                )

            return noise_map[noise]

        raise ValueError(f"Final2x 涓嶆敮鎸佹ā鍨? {model_name}")

    def _resolve_device(self) -> str:
        """閫夋嫨鍙敤鐨勬帹鐞嗚澶囥€?"""
        device = "cpu"
        try:
            import torch  # 鍙€変緷璧?
            if torch.cuda.is_available():
                try:
                    cap_major, cap_minor = torch.cuda.get_device_capability(0)
                    current_arch = f"sm_{cap_major}{cap_minor}"
                    supported_arches = [a for a in torch.cuda.get_arch_list() if a.startswith("sm_")]

                    if current_arch in supported_arches:
                        device = "cuda"
                    else:
                        print(
                            f"[Warn] GPU arch {current_arch} is not supported by this PyTorch build {supported_arches}; falling back to CPU."
                        )
                        device = "cpu"
                except Exception:
                    # 鏃犳硶鍒ゅ畾鏃讹紝灏介噺灏濊瘯 CUDA
                    device = "cuda"
        except Exception:
            device = "cpu"

        return device

    def _should_use_tile(self, model_name: str, device: str) -> bool:
        # Both Real-CUGAN and APISR become dramatically slower on this GPU
        # when they run as a single full-frame CUDA inference.
        return device == "cuda" and (
            model_name.startswith("RealCUGAN") or model_name == "APISR-RRDB"
        )

    def _load_direct_model(self, pretrained_model_name: str, device: str, use_tile: bool):
        """浼樺厛璧?cccv 杩涚▼鍐呮帹鐞嗭紝鍑忓皯 Final2x CLI 鍜屼复鏃舵枃浠跺紑閿€銆?"""
        import torch
        from cccv.auto.model import AutoModel

        model_key = (pretrained_model_name, device, use_tile)
        if self._direct_model is not None and self._direct_model_key == model_key:
            return self._direct_model

        tile = (128, 128) if use_tile else None
        self._direct_model = AutoModel.from_pretrained(
            pretrained_model_name,
            device=torch.device(device),
            fp16=False,
            tile=tile,
        )
        self._direct_model_key = model_key
        return self._direct_model

    def _save_direct_output(self, image: Image.Image, output_path: Path) -> Path:
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        if output_path.suffix.lower() in [".jpg", ".jpeg"]:
            image.convert("RGB").save(output_path, "JPEG", quality=95, optimize=True)
        elif output_path.suffix:
            image.save(output_path)
        else:
            output_path = output_path.with_suffix(".png")
            image.save(output_path)

        return output_path

    def _process_direct(
        self,
        input_path: Path,
        output_path: Path,
        pretrained_model_name: str,
        model_name: str,
        scale: int,
        device: str,
    ) -> Optional[Path]:
        source = Image.open(input_path)
        use_tile = self._should_use_tile(model_name, device)
        model = self._load_direct_model(pretrained_model_name, device, use_tile)
        resample = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR

        if source.mode in ("RGBA", "LA") or (source.mode == "P" and "transparency" in source.info):
            rgba_image = source.convert("RGBA")
            alpha_channel = np.array(rgba_image.getchannel("A"))
            rgb_image = rgba_image.convert("RGB")
        else:
            alpha_channel = None
            rgb_image = source.convert("RGB")

        target_size = (
            math.ceil(rgb_image.width * scale),
            math.ceil(rgb_image.height * scale),
        )

        rgb_array = np.array(rgb_image)
        bgr_array = rgb_array[:, :, ::-1].copy()
        result_bgr = model.inference_image(bgr_array)
        result_image = Image.fromarray(result_bgr[:, :, ::-1], "RGB")

        if result_image.size != target_size:
            result_image = result_image.resize(target_size, resample=resample)

        if alpha_channel is not None:
            alpha_rgb = np.repeat(alpha_channel[:, :, None], 3, axis=2)
            alpha_bgr = alpha_rgb[:, :, ::-1].copy()
            alpha_upscaled = model.inference_image(alpha_bgr)
            alpha_image = Image.fromarray(alpha_upscaled[:, :, 0], "L")

            if alpha_image.size != target_size:
                alpha_image = alpha_image.resize(target_size, resample=resample)

            result_image.putalpha(alpha_image)

        output_path = self._save_direct_output(result_image, output_path)
        print(f"[瀹屾垚] 瓒呭垎瀹屾垚: {output_path}")
        return output_path

    def _process_via_cli(
        self,
        input_path: Path,
        output_path: Path,
        pretrained_model_name: str,
        model_name: str,
        scale: int,
        device: str,
    ) -> Optional[Path]:
        use_tile = self._should_use_tile(model_name, device)

        with tempfile.TemporaryDirectory(prefix="final2x_in_") as input_tmp, tempfile.TemporaryDirectory(prefix="final2x_out_") as output_tmp:
            tmp_input = Path(input_tmp) / input_path.name
            shutil.copy2(input_path, tmp_input)

            config = {
                "pretrained_model_name": pretrained_model_name,
                "device": device,
                "input_path": [str(tmp_input)],
                "output_path": str(output_tmp),
                "target_scale": float(scale),
            }
            if use_tile:
                # Real-CUGAN is significantly faster on this GPU when Final2x uses tiled inference.
                config["use_tile"] = True

            cmd = self.runner_cmd + ["-j", json.dumps(config, ensure_ascii=False), "-n"]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                **_hidden_subprocess_kwargs(),
            )
            if result.stdout:
                print(result.stdout.strip())
            if result.returncode != 0:
                raise RuntimeError(f"Final2x execution failed (exit code {result.returncode})")

            image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
            generated = [
                p for p in Path(output_tmp).rglob("*")
                if p.is_file() and p.suffix.lower() in image_exts
            ]
            if not generated:
                raise RuntimeError("Final2x did not produce any output image")

            produced = max(generated, key=lambda p: p.stat().st_mtime)
            output_path = Path(output_path)
            ensure_dir(output_path.parent)

            if output_path.suffix.lower() in [".jpg", ".jpeg"]:
                out_img = Image.open(produced).convert("RGB")
                out_img.save(output_path, "JPEG", quality=95, optimize=True)
            elif output_path.suffix:
                shutil.copy2(produced, output_path)
            else:
                output_path = output_path.with_suffix(produced.suffix or ".png")
                shutil.copy2(produced, output_path)

            print(f"[瀹屾垚] 瓒呭垎瀹屾垚: {output_path}")
            return output_path

    def process(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str,
        scale: int = 4,
        noise: int = -1,
    ) -> Optional[Path]:
        """璋冪敤 Final2x-core / cccv 鎵ц瓒呭垎銆?"""
        if model_name not in self.SUPPORTED_MODELS:
            raise ValueError(f"Final2x 涓嶆敮鎸佹ā鍨? {model_name}")

        if not self.ensure_ready():
            raise RuntimeError("Final2x-core or cccv is not available")

        scale = int(scale)
        noise = int(noise)

        pretrained_model_name = self._resolve_pretrained_model_name(model_name, scale, noise)
        device = self._resolve_device()

        if importlib.util.find_spec("cccv") is not None:
            try:
                return self._process_direct(
                    input_path=input_path,
                    output_path=output_path,
                    pretrained_model_name=pretrained_model_name,
                    model_name=model_name,
                    scale=scale,
                    device=device,
                )
            except Exception as exc:
                print(f"[璀﹀憡] 杩涚▼鍐呰秴鍒嗗け璐ワ紝鍥為€€ Final2x 鍛戒护琛屾ā寮? {exc}")

        if self.runner_cmd is None:
            self.runner_cmd = self._resolve_runner()
        if self.runner_cmd is None:
            raise RuntimeError("Final2x-core executable is not available")

        return self._process_via_cli(
            input_path=input_path,
            output_path=output_path,
            pretrained_model_name=pretrained_model_name,
            model_name=model_name,
            scale=scale,
            device=device,
        )


class UpscaleProcessor:
    """缁熶竴瓒呭垎澶勭悊鍣細Real-ESRGAN / Real-CUGAN / APISR銆?"""

    def __init__(
        self,
        engine: str = "realesrgan",
        model_name: Optional[str] = None,
        realcugan_noise: int = -1,
    ):
        self.engine = normalize_upscale_engine(engine)
        self.model_name = model_name or get_default_upscale_model(self.engine)
        self.realcugan_noise = int(realcugan_noise)

        allow_custom_realesrgan_weights = (
            self.engine == "realesrgan"
            and str(self.model_name).strip().lower().endswith(".pth")
        )
        if not allow_custom_realesrgan_weights and self.model_name not in get_upscale_models(self.engine):
            raise ValueError(
                f"妯″瀷 {self.model_name} 涓嶅睘浜庡紩鎿?{UPSCALE_ENGINES[self.engine]}"
            )

        if self.engine == "realesrgan":
            self.backend = RealESRGANUpscaler()
        else:
            self.backend = Final2xUpscaler()

    def prepare(self) -> bool:
        """棰勭儹渚濊禆/妯″瀷銆?"""
        if self.engine == "realesrgan":
            return self.backend.download_model(self.model_name) is not None
        return self.backend.ensure_ready()

    def process(self, input_path: Path, output_path: Path, scale: int = 4) -> Optional[Path]:
        """鎵ц瓒呭垎銆?"""
        scale = int(scale)

        allowed_scales = get_upscale_scale_options(self.engine)
        if scale not in allowed_scales:
            raise ValueError(
                f"{UPSCALE_ENGINES[self.engine]} 涓嶆敮鎸?{scale}x锛屾敮鎸? {allowed_scales}"
            )

        if self.engine == "realesrgan":
            return self.backend.process(
                input_path,
                output_path,
                scale=scale,
                model_name=self.model_name,
            )

        noise = self.realcugan_noise if self.engine == "realcugan" else -1
        return self.backend.process(
            input_path,
            output_path,
            model_name=self.model_name,
            scale=scale,
            noise=noise,
        )

# ============== 鎵归噺澶勭悊 ==============

def batch_process(input_dir: Path, output_dir: Path,
                  watermark_config: dict = None,
                  mosaic_regions: List = None,
                  mosaic_mode: str = None,
                  do_upscale: bool = False,
                  upscale_engine: str = "realesrgan",
                  upscale_model: Optional[str] = None,
                  upscale_scale: int = 4,
                  upscale_noise: int = -1,
                  order: List[str] = None):
    """鎵归噺澶勭悊鍥剧墖

    Args:
        order: 澶勭悊椤哄簭锛屽 ['upscale', 'mosaic', 'watermark']
    """
    ensure_dir(output_dir)

    # 鏌ユ壘鎵€鏈夊浘鐗?
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    images = [f for f in input_dir.iterdir()
              if f.is_file() and f.suffix.lower() in image_extensions]

    if not images:
        print(f"[璀﹀憡] 鍦?{input_dir} 涓湭鎵惧埌鍥剧墖")
        return

    print(f"[Info] Found {len(images)} image(s)")

    # 鍒濆鍖栧鐞嗗櫒
    processors = {}
    if watermark_config:
        processors['watermark'] = WatermarkProcessor(watermark_config)
    if mosaic_regions:
        processors['mosaic'] = MosaicProcessor()
    if do_upscale:
        processors['upscale'] = UpscaleProcessor(
            engine=upscale_engine,
            model_name=upscale_model,
            realcugan_noise=upscale_noise,
        )

    # 榛樿澶勭悊椤哄簭
    order = order or ['upscale', 'mosaic', 'watermark']

    for img_path in images:
        print(f"\n[澶勭悊] {img_path.name}")

        current_path = img_path
        temp_paths = []

        for step in order:
            if step not in processors:
                continue

            if step == 'upscale':
                output_path = output_dir / f"{img_path.stem}_upscaled.png"
                result = processors[step].process(
                    current_path,
                    output_path,
                    scale=upscale_scale,
                )
                if result:
                    temp_paths.append(current_path)
                    current_path = Path(result)

            elif step == 'mosaic':
                output_path = output_dir / f"{img_path.stem}_mosaic.jpg"
                processors[step].process(
                    current_path, output_path,
                    regions=mosaic_regions,
                    mode=mosaic_mode
                )
                temp_paths.append(current_path)
                current_path = output_path

            elif step == 'watermark':
                output_path = output_dir / f"{img_path.stem}_watermarked.jpg"
                processors[step].process(current_path, output_path)
                temp_paths.append(current_path)
                current_path = output_path

        # 最终文件名跟随实际产物格式，避免“后缀是 PNG / 内容却是 JPEG”。
        final_suffix = current_path.suffix if current_path != img_path and current_path.suffix else img_path.suffix
        final_path = output_dir / f"{img_path.stem}{final_suffix}"

        if current_path == img_path:
            shutil.copy2(current_path, final_path)
        elif current_path != final_path:
            os.replace(current_path, final_path)

        # 娓呯悊涓存椂鏂囦欢
        for temp in temp_paths:
            if temp != img_path and temp.exists():
                temp.unlink()

        print(f"[瀹屾垚] 杈撳嚭: {final_path}")
# ============== 鍛戒护琛屾帴鍙?==============

def main():
    parser = argparse.ArgumentParser(description='鍥剧墖澶勭悊宸ュ叿')
    subparsers = parser.add_subparsers(dest='command', help='鍙敤鍛戒护')

    # 姘村嵃鍛戒护
    wm_parser = subparsers.add_parser('watermark', help='娣诲姞姘村嵃')
    wm_parser.add_argument('-i', '--input', required=True, help='杈撳叆鍥剧墖璺緞')
    wm_parser.add_argument('-o', '--output', required=True, help='杈撳嚭鍥剧墖璺緞')
    wm_parser.add_argument('-t', '--text', default='YourName', help='姘村嵃鏂囧瓧')
    wm_parser.add_argument('--font-size', type=int, default=48, help='瀛椾綋澶у皬')
    wm_parser.add_argument('--font-path', default='', help='TTF / OTF / TTC 瀛椾綋璺緞')
    wm_parser.add_argument('--color', nargs=3, type=int, default=[255, 255, 255], help='鏂囧瓧棰滆壊 RGB')
    wm_parser.add_argument('--opacity', type=float, default=0.6, help='閫忔槑搴?0-1')
    wm_parser.add_argument('--position', default='bottom-right',
                          choices=['center', 'top-left', 'top-right', 'bottom-left', 'bottom-right'],
                          help='姘村嵃浣嶇疆')
    wm_parser.add_argument('--rotation', type=float, nargs=2, default=[-10, 10], help='鏃嬭浆瑙掑害鑼冨洿')

    # 鎵撶爜鍛戒护
    mosaic_parser = subparsers.add_parser('mosaic', help='鎵撶爜澶勭悊')
    mosaic_parser.add_argument('-i', '--input', required=True, help='杈撳叆鍥剧墖璺緞')
    mosaic_parser.add_argument('-o', '--output', required=True, help='杈撳嚭鍥剧墖璺緞')
    mosaic_parser.add_argument('-r', '--region', action='append', required=True,
                              help="mosaic region x1,y1,x2,y2 (repeatable)")
    mosaic_parser.add_argument('-m', '--mode', default='pixelate', choices=['pixelate', 'blur'], help='鎵撶爜鏂瑰紡')
    mosaic_parser.add_argument("--pixel-size", type=int, default=10, help="pixel block size")
    mosaic_parser.add_argument('--blur-radius', type=int, default=15, help='妯＄硦鍗婂緞')

    # 瓒呭垎鍛戒护
    upscale_parser = subparsers.add_parser("upscale", help="image upscaling (Real-ESRGAN / Real-CUGAN / APISR)")
    upscale_parser.add_argument('-i', '--input', required=True, help='杈撳叆鍥剧墖璺緞')
    upscale_parser.add_argument('-o', '--output', required=True, help='杈撳嚭鍥剧墖璺緞')
    upscale_parser.add_argument('-e', '--engine', default='realesrgan', choices=list(UPSCALE_ENGINES.keys()),
                               help='瓒呭垎寮曟搸锛歳ealesrgan / realcugan / apisr')
    upscale_parser.add_argument("-s", "--scale", type=int, default=4, help="scale factor (realesrgan:2/4, realcugan:2/3/4, apisr:2/4)")
    upscale_parser.add_argument('-m', '--model', default=None,
                               help='妯″瀷鍚嶇О鎴栨湰鍦? .pth 璺緞')
    upscale_parser.add_argument('--noise', type=int, default=-1,
                               help='Real-CUGAN 闄嶅櫔绛夌骇 (-1/0/1/2/3)')

    # 鎵归噺娴佹按绾?
    pipeline_parser = subparsers.add_parser("pipeline", help="batch pipeline processing")
    pipeline_parser.add_argument('-i', '--input-dir', required=True, help='杈撳叆鐩綍')
    pipeline_parser.add_argument('-o', '--output-dir', required=True, help='杈撳嚭鐩綍')
    pipeline_parser.add_argument('--watermark', action='store_true', help='鍚敤姘村嵃')
    pipeline_parser.add_argument('--watermark-text', default='YourName', help='姘村嵃鏂囧瓧')
    pipeline_parser.add_argument('--watermark-font-path', default='', help='姘村嵃瀛椾綋璺緞')
    pipeline_parser.add_argument('--mosaic', action='store_true', help='鍚敤鎵撶爜')
    pipeline_parser.add_argument('--mosaic-region', action='append', help='鎵撶爜鍖哄煙')
    pipeline_parser.add_argument('--mosaic-mode', default='pixelate', choices=['pixelate', 'blur'])
    pipeline_parser.add_argument('--upscale', action='store_true', help='鍚敤瓒呭垎')
    pipeline_parser.add_argument('--upscale-engine', default='realesrgan', choices=list(UPSCALE_ENGINES.keys()),
                                help='瓒呭垎寮曟搸锛歳ealesrgan / realcugan / apisr')
    pipeline_parser.add_argument('--upscale-model', default=None, help='瓒呭垎妯″瀷鍚嶇О鎴栨湰鍦? .pth 璺緞')
    pipeline_parser.add_argument('--upscale-scale', type=int, default=4, help='瓒呭垎鍊嶇巼')
    pipeline_parser.add_argument('--upscale-noise', type=int, default=-1, help='Real-CUGAN 闄嶅櫔绛夌骇')
    pipeline_parser.add_argument('--order', nargs='+', default=['upscale', 'mosaic', 'watermark'],
                                help='澶勭悊椤哄簭')

    args = parser.parse_args()

    if args.command == 'watermark':
        processor = WatermarkProcessor({
            'text': args.text,
            'font_size': args.font_size,
            'font_path': args.font_path,
            'color': args.color,
            'opacity': args.opacity,
            'position': args.position,
            'rotation_range': args.rotation,
        })
        processor.process(Path(args.input), Path(args.output))

    elif args.command == 'mosaic':
        regions = []
        for r in args.region:
            coords = list(map(int, r.split(',')))
            if len(coords) == 4:
                regions.append(tuple(coords))

        processor = MosaicProcessor()
        kwargs = {}
        if args.mode == 'pixelate':
            kwargs['pixel_size'] = args.pixel_size
        else:
            kwargs['radius'] = args.blur_radius

        processor.process(Path(args.input), Path(args.output), regions, args.mode, **kwargs)

    elif args.command == 'upscale':
        processor = UpscaleProcessor(
            engine=args.engine,
            model_name=args.model,
            realcugan_noise=args.noise,
        )
        processor.process(Path(args.input), Path(args.output), scale=args.scale)

    elif args.command == 'pipeline':
        watermark_config = None
        if args.watermark:
            watermark_config = {
                'text': args.watermark_text,
                'font_path': args.watermark_font_path,
            }

        mosaic_regions = None
        if args.mosaic and args.mosaic_region:
            mosaic_regions = []
            for r in args.mosaic_region:
                coords = list(map(int, r.split(',')))
                if len(coords) == 4:
                    mosaic_regions.append(tuple(coords))

        batch_process(
            Path(args.input_dir),
            Path(args.output_dir),
            watermark_config=watermark_config,
            mosaic_regions=mosaic_regions,
            mosaic_mode=args.mosaic_mode,
            do_upscale=args.upscale,
            upscale_engine=args.upscale_engine,
            upscale_model=args.upscale_model,
            upscale_scale=args.upscale_scale,
            upscale_noise=args.upscale_noise,
            order=args.order
        )

    else:
        parser.print_help()


if __name__ == '__main__':
    main()


