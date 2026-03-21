#!/usr/bin/env python3
"""
PyWebView frontend for the image processor workbench.
"""

from __future__ import annotations

import base64
import io
import json
import re
import shutil
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

try:
    import webview
except ImportError:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "缺少依赖",
        "未检测到 pywebview。\n\n请先在项目环境里安装：\npython -m pip install pywebview",
    )
    raise SystemExit(1)

from main import (
    MosaicProcessor,
    UPSCALE_ENGINES,
    UPSCALE_MODELS,
    UPSCALE_SCALE_OPTIONS,
    UpscaleProcessor,
    WatermarkProcessor,
    get_watermark_font_options,
    normalize_upscale_engine,
    resolve_watermark_font_path,
)
from pixiv_llm import (
    DEFAULT_PIXIV_LLM_SYSTEM_PROMPT,
    DEFAULT_PIXIV_LLM_VISION_PROMPT,
    OpenAICompatiblePixivTagger,
    fetch_openai_compatible_models,
)
from pixiv_uploader import (
    PIXIV_AGE_OPTIONS,
    PIXIV_BROWSER_CHANNELS,
    PIXIV_UPLOAD_MODE_OPTIONS,
    PIXIV_VISIBILITY_OPTIONS,
    PixivUploader,
)


BASE_DIR = Path(__file__).parent
WEBUI_DIR = BASE_DIR / "webui"
CONFIG_PATH = BASE_DIR / "webview_config.json"
BOOT_LOG_PATH = BASE_DIR / "webview_boot.log"
IMAGE_FILTER = "Images (*.png;*.jpg;*.jpeg;*.webp;*.bmp)"
WEIGHT_FILTER = "PyTorch Weights (*.pth)"
FONT_FILTER = "Fonts (*.ttf;*.otf;*.ttc)"
FONT_MIME_TYPES = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".ttc": "font/ttf",
}
GOOGLE_FONTS_API_URL = "https://www.googleapis.com/webfonts/v1/webfonts"
GOOGLE_FONTS_DEFAULT_LIMIT = 80
WATERMARK_SAMPLE_MODE_OPTIONS = [
    {"value": "current", "label": "跟随水印文字"},
    {"value": "mixed", "label": "中英混排"},
    {"value": "zh", "label": "纯中文"},
    {"value": "en", "label": "纯英文"},
]
ORDER_OPTIONS = [
    "upscale -> mosaic -> watermark",
    "mosaic -> upscale -> watermark",
    "watermark -> mosaic",
]
WATERMARK_POSITIONS = [
    "center",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PIXIV_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif"}
PIXIV_UPLOAD_MAX_BYTES = 32 * 1024 * 1024
PIXIV_TAG_LIMIT = 10
QUALITY_BLACKLIST = {
    "masterpiece",
    "best quality",
    "high quality",
    "highres",
    "absurdres",
    "newest",
    "official art",
    "supreme masterpiece",
    "cinematic",
    "visual impact",
    "ultra-high resolution",
    "sharp focus",
    "intricate details",
    "high-end texture",
    "dramatic lighting",
    "dramatic",
    "colorful",
    "emotional",
    "very aesthetic",
    "extreme aesthetic",
    "detail background",
    "incredibly absurdres",
    "very awa",
    "fashion photography style",
    "hashtag-only commentary",
}
PIXIV_TAG_LANGUAGE_OPTIONS = [
    {"value": "raw", "label": "原样"},
    {"value": "ja_priority", "label": "日文优先"},
    {"value": "dual_compact", "label": "双语精简"},
]
PIXIV_SENSITIVE_FIELDS = ("cookie", "csrf_token", "llm_api_key")
PIXIV_SAFETY_MODE_OPTIONS = [
    {"value": "off", "label": "关闭"},
    {"value": "auto", "label": "自动分级 + 高风险拦截"},
    {"value": "strict", "label": "严格拦截"},
]
PIXIV_AGE_RANK = {"all": 0, "R-18": 1, "R-18G": 2}
PIXIV_SEXUAL_KEYWORDS = {
    "nsfw",
    "nude",
    "nudity",
    "裸体",
    "全裸",
    "乳首",
    "nipples",
    "pussy",
    "vagina",
    "penis",
    "sex",
    "性交",
    "cum",
    "精液",
    "orgasm",
    "masturbation",
    "anal",
    "fellatio",
    "フェラ",
    "paizuri",
    "パイズリ",
    "裸",
    "topless",
}
PIXIV_GRAPHIC_KEYWORDS = {
    "gore",
    "guro",
    "グロ",
    "bloodbath",
    "dismemberment",
    "decapitation",
    "entrails",
    "内臓",
    "流血",
    "切断",
    "欠損",
    "corpse",
    "死体",
}
PIXIV_MINOR_KEYWORDS = {
    "loli",
    "lolita",
    "ロリ",
    "幼女",
    "shota",
    "ショタ",
    "underage",
    "child",
}
PIXIV_TAG_MAP_JA = {
    "1girl": "女の子",
    "1boy": "男の子",
    "solo": "ソロ",
    "original": "オリジナル",
    "smile": "笑顔",
    "blush": "赤面",
    "open mouth": "口を開けた表情",
    "closed mouth": "口閉じ",
    "long hair": "ロングヘア",
    "short hair": "ショートヘア",
    "very long hair": "スーパーロングヘア",
    "messy hair": "乱れ髪",
    "twintails": "ツインテール",
    "ponytail": "ポニーテール",
    "braid": "三つ編み",
    "ahoge": "アホ毛",
    "animal ears": "獣耳",
    "cat ears": "猫耳",
    "fox ears": "狐耳",
    "wolf ears": "狼耳",
    "elf ears": "エルフ耳",
    "horns": "角",
    "tail": "しっぽ",
    "bare shoulders": "肩出し",
    "off shoulder": "オフショルダー",
    "dress": "ドレス",
    "armor": "鎧",
    "kimono": "着物",
    "school uniform": "制服",
    "gloves": "手袋",
    "thighhighs": "ニーハイ",
    "boots": "ブーツ",
    "simple background": "シンプル背景",
    "white background": "白背景",
    "sky": "空",
    "cloud": "雲",
    "outdoors": "屋外",
    "fantasy": "ファンタジー",
    "looking at viewer": "正面視",
    "upper body": "上半身",
    "cowboy shot": "カウボーイショット",
    "full body": "全身",
    "portrait": "ポートレート",
    "two-tone hair": "ツートンヘア",
    "multicolored hair": "マルチカラー髪",
    "multicolors hair": "マルチカラー髪",
}
PIXIV_COLOR_MAP_JA = {
    "black": "黒",
    "white": "白",
    "red": "赤",
    "blue": "青",
    "green": "緑",
    "yellow": "黄",
    "purple": "紫",
    "pink": "ピンク",
    "orange": "オレンジ",
    "silver": "銀",
    "gray": "灰",
    "grey": "灰",
    "brown": "茶",
    "blonde": "金",
}
PIXIV_DEFAULTS = {
    "enabled": False,
    "upload_mode": "browser",
    "browser_channel": "msedge",
    "profile_dir": str(BASE_DIR / ".pixiv_profile"),
    "cookie": "",
    "csrf_token": "",
    "llm_enabled": False,
    "llm_image_enabled": False,
    "llm_base_url": "https://api.openai.com/v1",
    "llm_api_key": "",
    "llm_model": "",
    "llm_temperature": 0.1,
    "llm_timeout": 60,
    "llm_metadata_prompt": "",
    "llm_image_prompt": "",
    "title_template": "{stem}",
    "caption": "",
    "tags": "",
    "tag_language": "ja_priority",
    "safety_mode": "auto",
    "use_metadata_tags": True,
    "include_lora_tags": True,
    "add_original_tag": True,
    "ai_generated": False,
    "add_upscale_tag": True,
    "add_engine_tag": True,
    "add_model_tag": False,
    "add_scale_tag": True,
    "visibility": "public",
    "age_restriction": "all",
    "auto_submit": True,
    "lock_tags": False,
}


def _resampling() -> int:
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _write_boot_log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with BOOT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


class WebviewBridge:
    def __init__(self):
        self._window = None
        self._lock = threading.RLock()
        self._current_image_path: Optional[Path] = None
        self._current_preview_kind = "source"
        self._dropped_image_dir = Path(tempfile.mkdtemp(prefix="pywebview_drop_"))
        self._loaded_sensitive_config = False
        self._session_pixiv_secrets = {field: "" for field in PIXIV_SENSITIVE_FIELDS}
        self._config = self._load_config()
        self._batch_state = self._empty_batch_state()
        self._batch_thread: Optional[threading.Thread] = None
        self._batch_job_counter = 0
        self._pixiv_llm_cache: Dict[str, List[str]] = {}

        if self._loaded_sensitive_config:
            self._save_config()

        last_image = self._config.get("last_image", "")
        if last_image:
            candidate = Path(last_image)
            if candidate.exists():
                self._current_image_path = candidate

    def _attach_window(self, window):
        self._window = window

    def get_bootstrap_data(self) -> Dict[str, Any]:
        with self._lock:
            payload: Dict[str, Any] = {
                "ok": True,
                "config": self._config,
                "engines": UPSCALE_ENGINES,
                "models": UPSCALE_MODELS,
                "scaleOptions": UPSCALE_SCALE_OPTIONS,
                "watermarkPositions": WATERMARK_POSITIONS,
                "watermarkFonts": get_watermark_font_options(),
                "watermarkSampleModes": WATERMARK_SAMPLE_MODE_OPTIONS,
                "orderOptions": ORDER_OPTIONS,
                "pixivBrowserChannels": PIXIV_BROWSER_CHANNELS,
                "pixivVisibilityOptions": PIXIV_VISIBILITY_OPTIONS,
                "pixivAgeOptions": PIXIV_AGE_OPTIONS,
                "pixivUploadModeOptions": PIXIV_UPLOAD_MODE_OPTIONS,
                "pixivTagLanguageOptions": PIXIV_TAG_LANGUAGE_OPTIONS,
                "pixivSafetyModeOptions": PIXIV_SAFETY_MODE_OPTIONS,
                "source": None,
                "preview": None,
                "recentImages": self._recent_image_items(),
                "recentDownloadedFonts": self._recent_downloaded_font_items(),
                "batch": self._batch_snapshot(0),
                "message": "准备就绪",
            }
            if self._current_image_path and self._current_image_path.exists():
                source = self._build_image_payload(self._current_image_path, label="源图")
                payload["source"] = source
                payload["preview"] = source
                payload["message"] = f"已恢复最近图片：{self._current_image_path.name}"
            return payload

    def open_image_dialog(self) -> Dict[str, Any]:
        try:
            if self._window is None:
                raise RuntimeError("窗口尚未初始化")
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=(IMAGE_FILTER,),
            )
            path = self._first_path(result)
            if not path:
                return {"ok": False, "cancelled": True}

            with self._lock:
                return self._load_image_from_path(Path(path), message_prefix="已加载图片")
        except Exception as exc:
            return self._error_response(exc)

    def open_image_path(self, path: str) -> Dict[str, Any]:
        try:
            raw_path = str(path or "").strip()
            if not raw_path:
                raise RuntimeError("未提供图片路径")
            with self._lock:
                return self._load_image_from_path(Path(raw_path), message_prefix="已加载图片")
        except Exception as exc:
            return self._error_response(exc)

    def open_image_blob(self, file_name: str = "", data_url: str = "") -> Dict[str, Any]:
        try:
            raw_name = Path(str(file_name or "").strip() or "dropped-image").name
            raw_data = str(data_url or "").strip()
            if not raw_data:
                raise RuntimeError("未提供拖拽图片数据")
            with self._lock:
                dropped_path = self._write_dropped_image(raw_name, raw_data)
                return self._load_image_from_path(dropped_path, message_prefix="已加载拖拽图片")
        except Exception as exc:
            return self._error_response(exc)

    def choose_model_dialog(self) -> Dict[str, Any]:
        try:
            if self._window is None:
                raise RuntimeError("窗口尚未初始化")
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=(WEIGHT_FILTER,),
            )
            path = self._first_path(result)
            if not path:
                return {"ok": False, "cancelled": True}
            return {"ok": True, "path": path}
        except Exception as exc:
            return self._error_response(exc)

    def choose_font_dialog(self) -> Dict[str, Any]:
        try:
            if self._window is None:
                raise RuntimeError("窗口尚未初始化")
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=(FONT_FILTER,),
            )
            path = self._first_path(result)
            if not path:
                return {"ok": False, "cancelled": True}
            return {"ok": True, "path": path}
        except Exception as exc:
            return self._error_response(exc)

    def get_watermark_font_preview(self, font_value: str = "") -> Dict[str, Any]:
        try:
            font_path = resolve_watermark_font_path(font_value)
            payload = base64.b64encode(font_path.read_bytes()).decode("ascii")
            mime = FONT_MIME_TYPES.get(font_path.suffix.lower(), "application/octet-stream")
            return {
                "ok": True,
                "path": str(font_path),
                "data_url": f"data:{mime};base64,{payload}",
            }
        except Exception as exc:
            return self._error_response(exc)

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        request = Request(url, headers={"User-Agent": "ImageWorkbench/1.0"})
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _pick_google_font_variant(self, item: Dict[str, Any]) -> Optional[str]:
        files = item.get("files") or {}
        for candidate in ("regular", "400", "500", "300", "700", "italic"):
            if candidate in files:
                return candidate
        for candidate in item.get("variants") or []:
            if candidate in files:
                return candidate
        return next(iter(files), None)

    def _compact_google_font_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        family = str(item.get("family") or "").strip()
        files = item.get("files") or {}
        variant = self._pick_google_font_variant(item)
        if not family or not variant or variant not in files:
            return None
        subsets = [str(value) for value in (item.get("subsets") or [])[:3]]
        subset_label = ", ".join(subsets)
        if item.get("subsets") and len(item.get("subsets")) > 3:
            subset_label += " +"
        return {
            "family": family,
            "category": str(item.get("category") or ""),
            "variant": variant,
            "last_modified": str(item.get("lastModified") or ""),
            "subset_label": subset_label,
        }

    def fetch_google_fonts_catalog(self, api_key: str = "", query: str = "") -> Dict[str, Any]:
        try:
            token = str(api_key or "").strip()
            if not token:
                raise RuntimeError("请先填写 Google Fonts API Key")
            keyword = str(query or "").strip().lower()
            url = f"{GOOGLE_FONTS_API_URL}?key={quote(token)}&sort=popularity"
            payload = self._fetch_json(url)
            items: List[Dict[str, Any]] = []
            for raw in payload.get("items") or []:
                compact = self._compact_google_font_item(raw)
                if not compact:
                    continue
                haystack = " ".join([
                    compact["family"],
                    compact["category"],
                    compact["subset_label"],
                ]).lower()
                if keyword and keyword not in haystack:
                    continue
                items.append(compact)
                if len(items) >= GOOGLE_FONTS_DEFAULT_LIMIT:
                    break
            return {
                "ok": True,
                "items": items,
                "message": f"已读取 {len(items)} 款 Google Fonts 字体",
            }
        except HTTPError as exc:
            return self._error_response(RuntimeError(f"Google Fonts 请求失败：HTTP {exc.code}"))
        except URLError as exc:
            return self._error_response(RuntimeError(f"Google Fonts 连接失败：{exc.reason}"))
        except Exception as exc:
            return self._error_response(exc)

    def download_google_font(self, api_key: str = "", family: str = "") -> Dict[str, Any]:
        try:
            token = str(api_key or "").strip()
            family_name = str(family or "").strip()
            if not token:
                raise RuntimeError("请先填写 Google Fonts API Key")
            if not family_name:
                raise RuntimeError("请先选择要下载的在线字体")

            url = f"{GOOGLE_FONTS_API_URL}?key={quote(token)}&family={quote(family_name)}"
            payload = self._fetch_json(url)
            items = payload.get("items") or []
            if not items:
                raise RuntimeError(f"未找到字体：{family_name}")

            target = next((item for item in items if str(item.get("family") or "") == family_name), items[0])
            compact = self._compact_google_font_item(target)
            files = target.get("files") or {}
            if not compact or compact["variant"] not in files:
                raise RuntimeError("该字体没有可下载的常规字重文件")

            download_url = str(files[compact["variant"]])
            parsed = urlparse(download_url)
            suffix = Path(parsed.path).suffix.lower() or ".ttf"
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", family_name).strip("-").lower() or "google-font"
            destination = BASE_DIR / "fonts" / f"google-{safe_name}-{compact['variant']}{suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            request = Request(download_url, headers={"User-Agent": "ImageWorkbench/1.0"})
            with urlopen(request, timeout=30) as response:
                destination.write_bytes(response.read())

            recent_downloads = self._remember_downloaded_font(family_name, destination, compact["variant"])
            self._save_config()

            return {
                "ok": True,
                "savedPath": str(destination),
                "fontOptions": get_watermark_font_options(),
                "recentDownloadedFonts": recent_downloads,
                "message": f"已下载字体：{family_name} ({compact['variant']})",
            }
        except HTTPError as exc:
            return self._error_response(RuntimeError(f"Google Fonts 下载失败：HTTP {exc.code}"))
        except URLError as exc:
            return self._error_response(RuntimeError(f"Google Fonts 连接失败：{exc.reason}"))
        except Exception as exc:
            return self._error_response(exc)

    def choose_directory_dialog(self, current_path: str = "") -> Dict[str, Any]:
        try:
            if self._window is None:
                raise RuntimeError("窗口尚未初始化")
            directory = current_path.strip() if current_path else ""
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                directory=directory,
                allow_multiple=False,
            )
            path = self._first_path(result)
            if not path:
                return {"ok": False, "cancelled": True}
            return {"ok": True, "path": path}
        except Exception as exc:
            return self._error_response(exc)

    def preview_pixiv_submission(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with self._lock:
                normalized = self._normalize_settings(settings)
                batch_settings = self._normalize_batch_settings((settings or {}).get("batch", {}))
                pixiv_settings = self._normalize_pixiv_settings((settings or {}).get("pixiv", {}))
                preview_source = self._resolve_pixiv_preview_source(batch_settings)
                self._config.update(normalized)
                self._config["pixiv"] = pixiv_settings
                self._save_config()

            preview = self._build_pixiv_submission_preview(
                preview_source,
                normalized,
                pixiv_settings,
                batch_settings,
            )
            return {
                "ok": True,
                "preview": preview,
                "message": "已生成 Pixiv 投稿预览",
            }
        except Exception as exc:
            return self._error_response(exc)

    def fetch_pixiv_llm_models(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        try:
            pixiv_settings = self._normalize_pixiv_settings((settings or {}).get("pixiv", settings or {}))
            if not pixiv_settings.get("llm_base_url"):
                raise RuntimeError("请先填写 LLM Base URL")
            items = fetch_openai_compatible_models(
                pixiv_settings.get("llm_base_url", ""),
                pixiv_settings.get("llm_api_key", ""),
                timeout=min(int(pixiv_settings.get("llm_timeout", 60)), 60),
            )
            selected = str(pixiv_settings.get("llm_model") or "").strip()
            return {
                "ok": True,
                "items": items,
                "selected": selected,
                "message": f"已从提供商读取 {len(items)} 个模型",
            }
        except Exception as exc:
            return self._error_response(exc)

    def test_pixiv_llm(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        try:
            pixiv_settings = self._normalize_pixiv_settings((settings or {}).get("pixiv", settings or {}))
            info_messages: List[str] = []
            warning_messages: List[str] = []
            sample_tags = ["1girl", "elf ears", "blue eyes", "solo", "long hair", "fantasy"]
            image_tags: List[str] = []
            if pixiv_settings.get("llm_image_enabled", False):
                current_image = None
                with self._lock:
                    if self._current_image_path and self._current_image_path.exists():
                        current_image = Path(self._current_image_path)
                if current_image:
                    image_tags = self._generate_llm_pixiv_image_tags(
                        current_image,
                        pixiv_settings,
                        info_messages=info_messages,
                        warning_messages=warning_messages,
                        use_cache=False,
                    )
                else:
                    warning_messages.append("已启用 LLM 看图打标，但当前还没有加载图片，已跳过图像测试。")
            llm_tags = self._generate_llm_pixiv_tags(
                sample_tags,
                pixiv_settings,
                image_tags=image_tags,
                info_messages=info_messages,
                warning_messages=warning_messages,
                use_cache=False,
            )
            if not llm_tags:
                raise RuntimeError("LLM 没有返回测试标签，请检查模型输出格式")
            return {
                "ok": True,
                "tags": llm_tags,
                "imageTags": image_tags,
                "infos": info_messages,
                "warnings": warning_messages,
                "message": "LLM 连接成功，已生成 Pixiv 风格测试标签",
            }
        except Exception as exc:
            return self._error_response(exc)

    def reset_preview(self) -> Dict[str, Any]:
        try:
            with self._lock:
                if not self._current_image_path or not self._current_image_path.exists():
                    raise RuntimeError("请先加载图片")
                self._current_preview_kind = "source"
                source = self._build_image_payload(self._current_image_path, label="源图")
                return {
                    "ok": True,
                    "source": source,
                    "preview": source,
                    "message": "已恢复到源图预览",
                }
        except Exception as exc:
            return self._error_response(exc)

    def render_preview(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with self._lock:
                input_path = self._ensure_input_image()
                normalized = self._normalize_settings(settings)
                self._config.update(normalized)
                self._save_config()

            with tempfile.TemporaryDirectory(prefix="pywebview_preview_") as tmp_dir:
                preview_path = Path(tmp_dir) / self._suggest_suffix(normalized)
                result_path, logs = self._run_pipeline(input_path, preview_path, normalized)
                source = self._build_image_payload(input_path, label="源图")
                preview = self._build_image_payload(result_path, label="处理预览")
                with self._lock:
                    self._current_preview_kind = "processed"
                return {
                    "ok": True,
                    "source": source,
                    "preview": preview,
                    "logs": logs,
                    "message": logs[-1] if logs else "预览已更新",
                }
        except Exception as exc:
            return self._error_response(exc)

    def export_result(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if self._window is None:
                raise RuntimeError("窗口尚未初始化")

            with self._lock:
                input_path = self._ensure_input_image()
                normalized = self._normalize_settings(settings)
                self._config.update(normalized)
                self._save_config()
                suggested_name = f"{input_path.stem}_processed{self._preferred_extension(normalized)}"

            dialog_result = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=suggested_name,
                file_types=(
                    "PNG (*.png)",
                    "JPEG (*.jpg;*.jpeg)",
                    "WebP (*.webp)",
                    "Bitmap (*.bmp)",
                ),
            )
            output_path = self._first_path(dialog_result)
            if not output_path:
                return {"ok": False, "cancelled": True}

            destination = Path(output_path)
            with tempfile.TemporaryDirectory(prefix="pywebview_export_") as tmp_dir:
                temp_output = Path(tmp_dir) / self._suggest_suffix(normalized)
                result_path, logs = self._run_pipeline(input_path, temp_output, normalized)
                self._write_final_output(result_path, destination)

            preview = self._build_image_payload(destination, label="导出结果")
            return {
                "ok": True,
                "preview": preview,
                "exportedPath": str(destination),
                "logs": logs + [f"已导出到：{destination}"],
                "message": f"已导出到：{destination.name}",
            }
        except Exception as exc:
            return self._error_response(exc)

    def start_batch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with self._lock:
                if self._batch_state["running"]:
                    raise RuntimeError("已有批量任务正在运行")

                normalized = self._normalize_settings(payload)
                active_order = self._resolve_active_order(normalized)
                if not active_order:
                    raise RuntimeError("请至少启用一个处理步骤")
                normalized["order"] = " -> ".join(active_order)

                batch_settings = self._normalize_batch_settings(payload.get("batch", {}))
                pixiv_settings = self._normalize_pixiv_settings(payload.get("pixiv", {}))

                input_dir = Path(batch_settings["input_dir"]).expanduser()
                output_dir = Path(batch_settings["output_dir"]).expanduser()
                if not input_dir.exists() or not input_dir.is_dir():
                    raise RuntimeError("输入目录不存在")
                output_dir.mkdir(parents=True, exist_ok=True)
                if pixiv_settings["enabled"] and pixiv_settings["upload_mode"] == "direct":
                    if not pixiv_settings["cookie"]:
                        raise RuntimeError("Pixiv 直传模式缺少 Cookie")
                    if not pixiv_settings["csrf_token"]:
                        raise RuntimeError("Pixiv 直传模式缺少 CSRF Token")

                self._config.update(normalized)
                self._config["last_input_dir"] = str(input_dir)
                self._config["last_output_dir"] = str(output_dir)
                self._config["pixiv"] = pixiv_settings
                self._save_config()

                self._batch_job_counter += 1
                job_id = self._batch_job_counter
                self._batch_state = {
                    "jobId": job_id,
                    "running": True,
                    "completed": False,
                    "cancelRequested": False,
                    "processed": 0,
                    "total": 0,
                    "errors": 0,
                    "successes": 0,
                    "status": "正在准备批量任务",
                    "message": "批量任务已创建",
                    "currentFile": "",
                    "inputDir": str(input_dir),
                    "outputDir": str(output_dir),
                    "logs": ["批量任务已创建"],
                }

                self._batch_thread = threading.Thread(
                    target=self._run_batch_job,
                    args=(job_id, normalized, batch_settings, pixiv_settings),
                    daemon=True,
                )
                self._batch_thread.start()
                return self._batch_snapshot(0)
        except Exception as exc:
            return self._error_response(exc)

    def stop_batch(self) -> Dict[str, Any]:
        try:
            with self._lock:
                if not self._batch_state.get("running", False):
                    raise RuntimeError("当前没有正在运行的批量任务")
                if self._batch_state.get("cancelRequested", False):
                    return self._batch_snapshot(0)

                self._batch_state["cancelRequested"] = True
                self._batch_state["status"] = "正在停止（等待当前图片完成）"
                self._batch_state["message"] = self._batch_state["status"]
                self._batch_state["logs"].append("已收到停止请求，将在当前图片处理完成后结束任务")
                return self._batch_snapshot(0)
        except Exception as exc:
            return self._error_response(exc)

    def poll_batch_status(self, offset: int = 0) -> Dict[str, Any]:
        with self._lock:
            return self._batch_snapshot(offset)

    def _batch_cancel_requested(self, job_id: int) -> bool:
        with self._lock:
            return self._batch_state.get("jobId") == job_id and bool(self._batch_state.get("cancelRequested", False))

    def _load_image_from_path(self, path: Path, message_prefix: str) -> Dict[str, Any]:
        candidate = path.expanduser()
        if not candidate.exists():
            raise FileNotFoundError(f"找不到图片：{candidate}")
        if candidate.suffix.lower() not in IMAGE_SUFFIXES:
            raise RuntimeError("仅支持 PNG / JPG / JPEG / WEBP / BMP 图片")

        self._current_image_path = candidate
        self._current_preview_kind = "source"
        self._config["last_image"] = str(candidate)
        self._remember_recent_image(candidate)
        self._save_config()

        source = self._build_image_payload(candidate, label="源图")
        return {
            "ok": True,
            "source": source,
            "preview": source,
            "recentImages": self._recent_image_items(),
            "message": f"{message_prefix}：{candidate.name}",
        }

    def _write_dropped_image(self, file_name: str, data_url: str) -> Path:
        match = re.match(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$", data_url, re.DOTALL)
        if not match:
            raise RuntimeError("拖拽图片数据格式无效")

        mime = str(match.group("mime") or "").lower()
        encoded = re.sub(r"\s+", "", match.group("data") or "")
        payload = base64.b64decode(encoded, validate=True)

        source_name = Path(file_name).name or "dropped-image"
        suffix = Path(source_name).suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            suffix = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/webp": ".webp",
                "image/bmp": ".bmp",
            }.get(mime, "")
        if suffix not in IMAGE_SUFFIXES:
            raise RuntimeError("拖拽图片格式不受支持，仅支持 PNG / JPG / JPEG / WEBP / BMP")

        stem = Path(source_name).stem or "dropped-image"
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "dropped-image"
        token = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = self._dropped_image_dir / f"{safe_stem}_{token}{suffix}"
        target.write_bytes(payload)
        return target

    def _remember_recent_image(self, path: Path) -> None:
        value = str(path)
        recent = [item for item in self._config.get("recent_images", []) if item != value]
        self._config["recent_images"] = [value, *recent][:8]

    def _recent_image_items(self) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        seen = set()
        for raw in self._config.get("recent_images", []):
            candidate = Path(str(raw)).expanduser()
            key = str(candidate)
            if key in seen:
                continue
            if not candidate.exists() or candidate.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            seen.add(key)
            items.append({
                "path": key,
                "fileName": candidate.name,
                "parent": str(candidate.parent),
            })
            if len(items) >= 8:
                break
        return items

    def _remember_downloaded_font(self, family: str, path: Path, variant: str) -> List[Dict[str, str]]:
        entry = {
            "family": str(family),
            "path": str(path),
            "fileName": path.name,
            "variant": str(variant),
        }
        recent = []
        for raw in self._config.get("recent_downloaded_fonts", []):
            if not isinstance(raw, dict):
                continue
            if str(raw.get("path") or "") == entry["path"]:
                continue
            recent.append({
                "family": str(raw.get("family") or ""),
                "path": str(raw.get("path") or ""),
                "fileName": str(raw.get("fileName") or Path(str(raw.get("path") or "")).name),
                "variant": str(raw.get("variant") or ""),
            })
        self._config["recent_downloaded_fonts"] = [entry, *recent][:8]
        return self._recent_downloaded_font_items()

    def _recent_downloaded_font_items(self) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        seen = set()
        for raw in self._config.get("recent_downloaded_fonts", []):
            if not isinstance(raw, dict):
                continue
            candidate = Path(str(raw.get("path") or "")).expanduser()
            key = str(candidate)
            if not key or key in seen:
                continue
            if not candidate.exists() or candidate.suffix.lower() not in FONT_MIME_TYPES:
                continue
            seen.add(key)
            items.append({
                "family": str(raw.get("family") or candidate.stem),
                "path": key,
                "fileName": str(raw.get("fileName") or candidate.name),
                "variant": str(raw.get("variant") or ""),
            })
            if len(items) >= 8:
                break
        return items

    def _run_batch_job(
        self,
        job_id: int,
        settings: Dict[str, Any],
        batch_settings: Dict[str, str],
        pixiv_settings: Dict[str, Any],
    ) -> None:
        pixiv_uploader: Optional[PixivUploader] = None
        try:
            input_dir = Path(batch_settings["input_dir"]).expanduser()
            output_dir = Path(batch_settings["output_dir"]).expanduser()
            image_files = sorted(
                [
                    path
                    for path in input_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
                ],
                key=lambda item: item.name.lower(),
            )

            with self._lock:
                if self._batch_state.get("jobId") != job_id:
                    return
                self._batch_state["total"] = len(image_files)
                self._batch_state["status"] = "正在处理中"
                self._batch_state["message"] = "正在处理中"

            if not image_files:
                self._batch_log(job_id, "输入目录中没有可处理的图片")
                self._finish_batch(job_id, message="未找到可处理的图片")
                return

            if pixiv_settings["enabled"]:
                pixiv_uploader = PixivUploader(
                    pixiv_settings,
                    log_fn=lambda message: self._batch_log(job_id, message),
                )
                upload_mode = pixiv_settings.get("upload_mode", "browser")
                upload_mode_label = "直传模式" if upload_mode == "direct" else "浏览器模式"
                self._batch_log(job_id, f"[Pixiv] 自动上传已启用（{upload_mode_label}）")
                if upload_mode == "direct" and not pixiv_settings["auto_submit"]:
                    self._batch_log(job_id, "[Pixiv] 直传模式不支持停留在投稿页，将按自动投稿执行。")
                if upload_mode != "direct" and not pixiv_settings["auto_submit"] and len(image_files) > 1:
                    self._batch_log(job_id, "[Pixiv] 当前为手动投稿模式，建议先确认首张流程是否符合预期。")

            for index, image_path in enumerate(image_files, 1):
                if self._batch_cancel_requested(job_id):
                    self._finish_batch(job_id, message="批量任务已停止")
                    return
                self._set_batch_current(job_id, image_path.name, index - 1)
                self._batch_log(job_id, f"[{index}/{len(image_files)}] 处理: {image_path.name}")

                try:
                    final_path = output_dir / image_path.name
                    result_path, logs = self._run_pipeline(image_path, final_path, settings)
                    for line in logs[1:]:
                        self._batch_log(job_id, f"[{image_path.name}] {line}")

                    if self._batch_cancel_requested(job_id):
                        self._batch_log(job_id, "[Pixiv] 已收到停止请求，本张处理结果会保留，但不会继续自动上传。")
                    elif pixiv_uploader is not None:
                        with tempfile.TemporaryDirectory(prefix="pywebview_pixiv_upload_") as pixiv_tmp_dir:
                            upload_path, upload_note = self._prepare_pixiv_upload_image(
                                result_path,
                                Path(pixiv_tmp_dir),
                            )
                            if upload_note:
                                self._batch_log(job_id, f"[Pixiv] {upload_note}")
                            upload_size = upload_path.stat().st_size
                            if upload_size > PIXIV_UPLOAD_MAX_BYTES:
                                raise RuntimeError(
                                    f"Pixiv 上传文件超过 32MB 限制：{upload_path.name} ({self._format_bytes(upload_size)})"
                                )
                            tag_bundle = self._build_pixiv_tag_bundle(image_path, pixiv_settings, settings)
                            pixiv_tags = tag_bundle["tags"]
                            effective_age_restriction = tag_bundle["safety"]["effective_age"]
                            for message in tag_bundle["infos"]:
                                self._batch_log(job_id, f"[Pixiv] {message}")
                            for message in tag_bundle["warnings"]:
                                self._batch_log(job_id, f"[Pixiv] {message}")
                            for message in tag_bundle["errors"]:
                                self._batch_log(job_id, f"[Pixiv] {message}")
                            if tag_bundle["safety"]["blocked"]:
                                raise RuntimeError("Pixiv 安全护栏已拦截当前图片的自动投稿")

                            pixiv_uploader.upload_image(
                                upload_path,
                                title=self._build_pixiv_title(result_path, pixiv_settings),
                                caption=pixiv_settings["caption"],
                                tags=pixiv_tags,
                                visibility=pixiv_settings["visibility"],
                                age_restriction=effective_age_restriction,
                                ai_generated=pixiv_settings["ai_generated"],
                                auto_submit=pixiv_settings["auto_submit"],
                                lock_tags=pixiv_settings["lock_tags"],
                            )

                    with self._lock:
                        if self._batch_state.get("jobId") != job_id:
                            return
                        self._batch_state["successes"] += 1
                    if self._batch_cancel_requested(job_id):
                        self._finish_batch(job_id, message="批量任务已停止")
                        return
                except Exception as exc:
                    with self._lock:
                        if self._batch_state.get("jobId") != job_id:
                            return
                        self._batch_state["errors"] += 1
                    self._batch_log(job_id, f"[{image_path.name}] 错误: {exc}")
                finally:
                    with self._lock:
                        if self._batch_state.get("jobId") == job_id:
                            self._batch_state["processed"] = index
                            self._batch_state["currentFile"] = image_path.name if index < len(image_files) else ""

            self._finish_batch(job_id, message="批量处理已完成")
        except Exception as exc:
            self._batch_log(job_id, f"批量任务异常: {exc}")
            self._finish_batch(job_id, message=f"批量任务失败: {exc}")
        finally:
            try:
                if pixiv_uploader is not None and (
                    pixiv_settings.get("upload_mode") == "direct" or pixiv_settings.get("auto_submit", True)
                ):
                    pixiv_uploader.close()
            except Exception:
                pass

    def _set_batch_current(self, job_id: int, file_name: str, processed: int) -> None:
        with self._lock:
            if self._batch_state.get("jobId") != job_id:
                return
            self._batch_state["currentFile"] = file_name
            self._batch_state["processed"] = processed
            self._batch_state["status"] = f"处理中: {file_name}"
            self._batch_state["message"] = self._batch_state["status"]

    def _finish_batch(self, job_id: int, *, message: str) -> None:
        with self._lock:
            if self._batch_state.get("jobId") != job_id:
                return
            self._batch_state["running"] = False
            self._batch_state["completed"] = True
            self._batch_state["currentFile"] = ""
            self._batch_state["status"] = message
            self._batch_state["message"] = message

    def _batch_log(self, job_id: int, message: str) -> None:
        with self._lock:
            if self._batch_state.get("jobId") != job_id:
                return
            self._batch_state["logs"].append(str(message))
            self._batch_state["message"] = str(message)

    def _batch_snapshot(self, offset: int) -> Dict[str, Any]:
        offset = max(0, int(offset or 0))
        logs = list(self._batch_state.get("logs", []))
        return {
            "ok": True,
            "jobId": self._batch_state.get("jobId", 0),
            "running": bool(self._batch_state.get("running", False)),
            "completed": bool(self._batch_state.get("completed", False)),
            "cancelRequested": bool(self._batch_state.get("cancelRequested", False)),
            "processed": int(self._batch_state.get("processed", 0)),
            "total": int(self._batch_state.get("total", 0)),
            "errors": int(self._batch_state.get("errors", 0)),
            "successes": int(self._batch_state.get("successes", 0)),
            "status": self._batch_state.get("status", "未开始"),
            "message": self._batch_state.get("message", "未开始"),
            "currentFile": self._batch_state.get("currentFile", ""),
            "inputDir": self._batch_state.get("inputDir", ""),
            "outputDir": self._batch_state.get("outputDir", ""),
            "logs": logs[offset:],
            "nextOffset": len(logs),
        }

    def _empty_batch_state(self) -> Dict[str, Any]:
        return {
            "jobId": 0,
            "running": False,
            "completed": False,
            "cancelRequested": False,
            "processed": 0,
            "total": 0,
            "errors": 0,
            "successes": 0,
            "status": "未开始",
            "message": "未开始",
            "currentFile": "",
            "inputDir": "",
            "outputDir": "",
            "logs": [],
        }

    def _ensure_input_image(self) -> Path:
        if not self._current_image_path or not self._current_image_path.exists():
            raise RuntimeError("请先加载图片")
        return self._current_image_path

    def _load_config(self) -> Dict[str, Any]:
        defaults = {
            "last_image": "",
            "recent_images": [],
            "recent_downloaded_fonts": [],
            "last_input_dir": "",
            "last_output_dir": "",
            "order": ORDER_OPTIONS[0],
            "watermark": {
                "enabled": True,
                "text": "YourName",
                "font_size": 48,
                "font_path": "",
                "sample_mode": "current",
                "opacity": 0.6,
                "position": "bottom-right",
                "rotation_min": -10,
                "rotation_max": 10,
                "random_offset": True,
                "color": "#ffffff",
            },
            "mosaic": {
                "enabled": False,
                "mode": "pixelate",
                "pixel_size": 10,
                "blur_radius": 15,
            },
            "upscale": {
                "enabled": False,
                "engine": "realesrgan",
                "model": UPSCALE_MODELS["realesrgan"][0],
                "custom_model_path": "",
                "scale": 4,
                "noise": -1,
            },
            "pixiv": dict(PIXIV_DEFAULTS),
        }

        if CONFIG_PATH.exists():
            try:
                loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                loaded_pixiv = loaded.get("pixiv", {})
                if isinstance(loaded_pixiv, dict):
                    self._loaded_sensitive_config = any(
                        bool(str(loaded_pixiv.get(field) or "").strip())
                        for field in PIXIV_SENSITIVE_FIELDS
                    )
                for key, value in loaded.items():
                    if isinstance(value, dict) and isinstance(defaults.get(key), dict):
                        defaults[key].update(value)
                    else:
                        defaults[key] = value
            except Exception:
                pass

        for field in PIXIV_SENSITIVE_FIELDS:
            defaults["pixiv"][field] = ""
        return defaults

    def _save_config(self) -> None:
        persisted = dict(self._config)
        pixiv_settings = persisted.get("pixiv", {})
        if isinstance(pixiv_settings, dict):
            persisted["pixiv"] = dict(pixiv_settings)
            for field in PIXIV_SENSITIVE_FIELDS:
                persisted["pixiv"][field] = ""
        CONFIG_PATH.write_text(json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        settings = settings or {}
        watermark = settings.get("watermark", {})
        mosaic = settings.get("mosaic", {})
        upscale = settings.get("upscale", {})

        engine = normalize_upscale_engine(upscale.get("engine", self._config["upscale"]["engine"]))
        custom_model = str(upscale.get("custom_model_path", "")).strip()
        model_name = custom_model or upscale.get("model") or UPSCALE_MODELS[engine][0]
        scale = int(upscale.get("scale", self._config["upscale"]["scale"]))
        noise = int(upscale.get("noise", self._config["upscale"]["noise"]))
        sample_mode = str(watermark.get("sample_mode", self._config["watermark"].get("sample_mode", "current")) or "current")
        if sample_mode not in {item["value"] for item in WATERMARK_SAMPLE_MODE_OPTIONS}:
            sample_mode = "current"

        return {
            "order": settings.get("order") or self._config["order"],
            "regions": [tuple(int(v) for v in region) for region in settings.get("regions", [])],
            "watermark": {
                "enabled": bool(watermark.get("enabled", self._config["watermark"].get("enabled", True))),
                "text": str(watermark.get("text", self._config["watermark"]["text"]) or "YourName"),
                "font_size": int(watermark.get("font_size", self._config["watermark"]["font_size"])),
                "font_path": str(watermark.get("font_path", self._config["watermark"].get("font_path", "")) or "").strip(),
                "sample_mode": sample_mode,
                "opacity": float(watermark.get("opacity", self._config["watermark"]["opacity"])),
                "position": watermark.get("position", self._config["watermark"]["position"]),
                "rotation_min": int(watermark.get("rotation_min", self._config["watermark"]["rotation_min"])),
                "rotation_max": int(watermark.get("rotation_max", self._config["watermark"]["rotation_max"])),
                "random_offset": bool(watermark.get("random_offset", self._config["watermark"]["random_offset"])),
                "color": str(watermark.get("color", self._config["watermark"]["color"])),
            },
            "mosaic": {
                "enabled": bool(mosaic.get("enabled", self._config["mosaic"].get("enabled", False))),
                "mode": mosaic.get("mode", self._config["mosaic"]["mode"]),
                "pixel_size": int(mosaic.get("pixel_size", self._config["mosaic"]["pixel_size"])),
                "blur_radius": int(mosaic.get("blur_radius", self._config["mosaic"]["blur_radius"])),
            },
            "upscale": {
                "enabled": bool(upscale.get("enabled", self._config["upscale"].get("enabled", False))),
                "engine": engine,
                "model": model_name,
                "custom_model_path": custom_model,
                "scale": scale,
                "noise": noise if engine == "realcugan" else -1,
            },
        }

    def _normalize_batch_settings(self, batch: Dict[str, Any]) -> Dict[str, str]:
        batch = batch or {}
        return {
            "input_dir": str(batch.get("input_dir", self._config.get("last_input_dir", "")) or "").strip(),
            "output_dir": str(batch.get("output_dir", self._config.get("last_output_dir", "")) or "").strip(),
        }

    def _normalize_pixiv_settings(self, pixiv: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(PIXIV_DEFAULTS)
        merged.update(self._config.get("pixiv", {}))
        merged.update(self._session_pixiv_secrets)
        merged.update(pixiv or {})
        merged["upload_mode"] = str(merged.get("upload_mode") or "browser").strip().lower()
        if merged["upload_mode"] not in {item["value"] for item in PIXIV_UPLOAD_MODE_OPTIONS}:
            merged["upload_mode"] = "browser"
        merged["browser_channel"] = merged.get("browser_channel") or "msedge"
        merged["profile_dir"] = str(merged.get("profile_dir") or BASE_DIR / ".pixiv_profile")
        merged["cookie"] = str(merged.get("cookie") or "").strip()
        merged["csrf_token"] = str(merged.get("csrf_token") or "").strip()
        merged["llm_base_url"] = str(merged.get("llm_base_url") or "https://api.openai.com/v1").strip()
        merged["llm_api_key"] = str(merged.get("llm_api_key") or "").strip()
        merged["llm_model"] = str(merged.get("llm_model") or "").strip()
        merged["llm_metadata_prompt"] = str(merged.get("llm_metadata_prompt") or "").strip()
        merged["llm_image_prompt"] = str(merged.get("llm_image_prompt") or "").strip()
        try:
            merged["llm_temperature"] = float(merged.get("llm_temperature", 0.1))
        except (TypeError, ValueError):
            merged["llm_temperature"] = 0.1
        try:
            merged["llm_timeout"] = int(merged.get("llm_timeout", 60))
        except (TypeError, ValueError):
            merged["llm_timeout"] = 60
        merged["llm_temperature"] = max(0.0, min(merged["llm_temperature"], 2.0))
        merged["llm_timeout"] = max(5, min(merged["llm_timeout"], 300))
        merged["title_template"] = str(merged.get("title_template") or "{stem}")
        merged["caption"] = str(merged.get("caption") or "")
        merged["tags"] = str(merged.get("tags") or "")
        merged["tag_language"] = str(merged.get("tag_language") or "ja_priority")
        if merged["tag_language"] not in {item["value"] for item in PIXIV_TAG_LANGUAGE_OPTIONS}:
            merged["tag_language"] = "ja_priority"
        merged["safety_mode"] = str(merged.get("safety_mode") or "auto")
        if merged["safety_mode"] not in {item["value"] for item in PIXIV_SAFETY_MODE_OPTIONS}:
            merged["safety_mode"] = "auto"
        merged["visibility"] = merged.get("visibility") or "public"
        merged["age_restriction"] = merged.get("age_restriction") or "all"
        for key in (
            "enabled",
            "use_metadata_tags",
            "include_lora_tags",
            "add_original_tag",
            "ai_generated",
            "add_upscale_tag",
            "add_engine_tag",
            "add_model_tag",
            "add_scale_tag",
            "auto_submit",
            "lock_tags",
            "llm_enabled",
            "llm_image_enabled",
        ):
            merged[key] = bool(merged.get(key, PIXIV_DEFAULTS[key]))
        for field in PIXIV_SENSITIVE_FIELDS:
            self._session_pixiv_secrets[field] = str(merged.get(field) or "").strip()
        return merged

    def _canonicalize_tag(self, value: str) -> str:
        cleaned = str(value or "").strip().strip("#")
        cleaned = cleaned.replace("_", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _has_cjk(self, value: str) -> bool:
        return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]", value or ""))

    def _translate_pixiv_tag(self, value: str) -> Optional[str]:
        cleaned = self._canonicalize_tag(value)
        if not cleaned:
            return None
        if self._has_cjk(cleaned):
            return cleaned

        key = cleaned.lower()
        if key in PIXIV_TAG_MAP_JA:
            return PIXIV_TAG_MAP_JA[key]

        match = re.fullmatch(r"(black|white|red|blue|green|yellow|purple|pink|orange|silver|gray|grey|brown|blonde) hair", key)
        if match:
            return f"{PIXIV_COLOR_MAP_JA[match.group(1)]}髪"

        match = re.fullmatch(r"(black|white|red|blue|green|yellow|purple|pink|orange|silver|gray|grey|brown|blonde) eyes", key)
        if match:
            return f"{PIXIV_COLOR_MAP_JA[match.group(1)]}い目"

        match = re.fullmatch(r"(black|white|red|blue|green|yellow|purple|pink|orange|silver|gray|grey|brown|blonde) pupils", key)
        if match:
            return f"{PIXIV_COLOR_MAP_JA[match.group(1)]}の瞳"

        match = re.fullmatch(r"(black|white|red|blue|green|yellow|purple|pink|orange|silver|gray|grey|brown|blonde) background", key)
        if match:
            return f"{PIXIV_COLOR_MAP_JA[match.group(1)]}背景"

        return None

    def _localize_pixiv_tag(self, tag: str, strategy: str) -> List[str]:
        cleaned = self._canonicalize_tag(tag)
        if not cleaned:
            return []

        translated = self._translate_pixiv_tag(cleaned)
        if strategy == "raw":
            return [cleaned]
        if strategy == "dual_compact":
            if translated and translated != cleaned:
                return [translated, cleaned]
            return [translated or cleaned]
        return [translated or cleaned]

    def _append_unique_tags(self, target: List[str], seen: set, candidates: List[str]) -> None:
        for candidate in candidates:
            cleaned = self._canonicalize_tag(candidate)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            target.append(cleaned)
            if len(target) >= PIXIV_TAG_LIMIT:
                return

    def _resolve_active_order(self, settings: Dict[str, Any]) -> List[str]:
        active: List[str] = []
        for raw_step in str(settings.get("order", ORDER_OPTIONS[0])).split("->"):
            step = raw_step.strip()
            if step == "upscale" and settings["upscale"]["enabled"]:
                active.append(step)
            elif step == "mosaic" and settings["mosaic"]["enabled"] and settings["regions"]:
                active.append(step)
            elif step == "watermark" and settings["watermark"]["enabled"]:
                active.append(step)
        return active

    def _build_pixiv_title(self, image_path: Path, pixiv_settings: Dict[str, Any]) -> str:
        template = str(pixiv_settings.get("title_template") or "{stem}")
        try:
            return template.format(stem=image_path.stem, name=image_path.name)
        except Exception:
            return image_path.stem

    def _extract_metadata_tags(self, image_path: Path) -> Tuple[List[str], List[str]]:
        try:
            with Image.open(image_path) as image:
                parameters = image.info.get("parameters", "")
        except Exception:
            return [], []

        if not isinstance(parameters, str) or not parameters.strip():
            return [], []

        def split_prompt_chunks(text: str) -> List[str]:
            chunks: List[str] = []
            current: List[str] = []
            depth = 0
            for char in text:
                if char == "," and depth == 0:
                    chunk = "".join(current).strip()
                    if chunk:
                        chunks.append(chunk)
                    current = []
                    continue

                current.append(char)
                if char == "(":
                    depth += 1
                elif char == ")" and depth > 0:
                    depth -= 1

            tail = "".join(current).strip()
            if tail:
                chunks.append(tail)
            return chunks

        def expand_prompt_chunks(text: str) -> List[str]:
            expanded: List[str] = []
            for chunk in split_prompt_chunks(text):
                inner = chunk.strip()
                while inner.startswith("(") and inner.endswith(")") and len(inner) > 2:
                    inner = inner[1:-1].strip()
                if "," in inner:
                    expanded.extend(expand_prompt_chunks(inner))
                elif inner:
                    expanded.append(inner)
            return expanded

        positive_text = parameters.split("\nNegative prompt:", 1)[0]
        lora_tags = re.findall(r"<lora:([^:>]+)(?::[^>]+)?>", positive_text)
        positive_text = re.sub(r"<lora:[^>]+>", "", positive_text)
        prompt_chunks = expand_prompt_chunks(positive_text.replace("\n", ","))

        prompt_tags: List[str] = []
        for raw_tag in prompt_chunks:
            tag = raw_tag.strip()
            if not tag:
                continue
            tag = re.sub(r":-?\d+(?:\.\d+)?$", "", tag).strip()
            if not tag or tag.lower() in QUALITY_BLACKLIST:
                continue
            prompt_tags.append(tag)

        return prompt_tags, lora_tags

    def _pixiv_llm_cache_key(self, metadata_tags: List[str], pixiv_settings: Dict[str, Any], image_tags: Optional[List[str]] = None) -> str:
        return json.dumps(
            {
                "kind": "metadata",
                "metadata_tags": metadata_tags,
                "image_tags": image_tags or [],
                "base_url": pixiv_settings.get("llm_base_url", ""),
                "model": pixiv_settings.get("llm_model", ""),
                "temperature": pixiv_settings.get("llm_temperature", 0.1),
                "metadata_prompt": pixiv_settings.get("llm_metadata_prompt", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _pixiv_llm_image_cache_key(self, image_path: Path, pixiv_settings: Dict[str, Any]) -> str:
        try:
            resolved = Path(image_path).resolve()
        except Exception:
            resolved = Path(image_path)
        stat = resolved.stat()
        return json.dumps(
            {
                "kind": "image",
                "path": str(resolved),
                "size": stat.st_size,
                "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
                "base_url": pixiv_settings.get("llm_base_url", ""),
                "model": pixiv_settings.get("llm_model", ""),
                "temperature": pixiv_settings.get("llm_temperature", 0.1),
                "image_prompt": pixiv_settings.get("llm_image_prompt", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _generate_llm_pixiv_tags(
        self,
        metadata_tags: List[str],
        pixiv_settings: Dict[str, Any],
        image_tags: Optional[List[str]] = None,
        *,
        info_messages: Optional[List[str]] = None,
        warning_messages: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[str]:
        if not pixiv_settings.get("llm_enabled", False):
            return []
        if not metadata_tags and not image_tags:
            return []

        if not pixiv_settings.get("llm_base_url"):
            if warning_messages is not None:
                warning_messages.append("LLM 标签润色已启用，但 Base URL 为空，已回退到本地规则。")
            return []
        if not pixiv_settings.get("llm_model"):
            if warning_messages is not None:
                warning_messages.append("LLM 标签润色已启用，但 Model 为空，已回退到本地规则。")
            return []

        cache_key = self._pixiv_llm_cache_key(metadata_tags, pixiv_settings, image_tags=image_tags)
        if use_cache and cache_key in self._pixiv_llm_cache:
            cached = list(self._pixiv_llm_cache[cache_key])
            if info_messages is not None:
                info_messages.append("已复用缓存的 LLM Pixiv 标签结果。")
            return cached

        try:
            tagger = OpenAICompatiblePixivTagger(
                base_url=pixiv_settings.get("llm_base_url", ""),
                api_key=pixiv_settings.get("llm_api_key", ""),
                model=pixiv_settings.get("llm_model", ""),
                temperature=pixiv_settings.get("llm_temperature", 0.1),
                timeout=pixiv_settings.get("llm_timeout", 60),
                system_prompt=pixiv_settings.get("llm_metadata_prompt", "") or None,
                vision_system_prompt=pixiv_settings.get("llm_image_prompt", "") or None,
            )
            llm_tags = tagger.generate_tags(metadata_tags, image_tags=image_tags, limit=PIXIV_TAG_LIMIT)
            if use_cache:
                self._pixiv_llm_cache[cache_key] = list(llm_tags)
            if info_messages is not None:
                if image_tags:
                    info_messages.append(f"LLM 已综合 metadata 与看图标签整理出 {len(llm_tags)} 个 Pixiv 标签。")
                else:
                    info_messages.append(f"LLM 已将 metadata 提示词整理为 {len(llm_tags)} 个 Pixiv 标签。")
            return llm_tags
        except Exception as exc:
            if warning_messages is not None:
                warning_messages.append(f"LLM 标签润色失败，已回退到本地规则：{exc}")
            return []

    def _generate_llm_pixiv_image_tags(
        self,
        image_path: Path,
        pixiv_settings: Dict[str, Any],
        *,
        info_messages: Optional[List[str]] = None,
        warning_messages: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[str]:
        if not pixiv_settings.get("llm_enabled", False):
            return []
        if not pixiv_settings.get("llm_image_enabled", False):
            return []

        candidate = Path(image_path)
        if not candidate.exists():
            return []
        if not pixiv_settings.get("llm_base_url"):
            if warning_messages is not None:
                warning_messages.append("LLM 看图打标已启用，但 Base URL 为空，已跳过图像标签。")
            return []
        if not pixiv_settings.get("llm_model"):
            if warning_messages is not None:
                warning_messages.append("LLM 看图打标已启用，但 Model 为空，已跳过图像标签。")
            return []

        try:
            cache_key = self._pixiv_llm_image_cache_key(candidate, pixiv_settings)
        except Exception as exc:
            if warning_messages is not None:
                warning_messages.append(f"LLM 看图打标无法建立缓存键，已直接请求模型：{exc}")
            cache_key = ""

        if use_cache and cache_key and cache_key in self._pixiv_llm_cache:
            cached = list(self._pixiv_llm_cache[cache_key])
            if info_messages is not None:
                info_messages.append("已复用缓存的 LLM 看图标签结果。")
            return cached

        try:
            tagger = OpenAICompatiblePixivTagger(
                base_url=pixiv_settings.get("llm_base_url", ""),
                api_key=pixiv_settings.get("llm_api_key", ""),
                model=pixiv_settings.get("llm_model", ""),
                temperature=pixiv_settings.get("llm_temperature", 0.1),
                timeout=pixiv_settings.get("llm_timeout", 60),
                system_prompt=pixiv_settings.get("llm_metadata_prompt", "") or None,
                vision_system_prompt=pixiv_settings.get("llm_image_prompt", "") or None,
            )
            llm_tags = tagger.generate_tags_from_image(candidate, limit=PIXIV_TAG_LIMIT)
            if use_cache and cache_key:
                self._pixiv_llm_cache[cache_key] = list(llm_tags)
            if info_messages is not None:
                info_messages.append(f"LLM 已根据上传图内容补充 {len(llm_tags)} 个 Pixiv 标签。")
            return llm_tags
        except Exception as exc:
            if warning_messages is not None:
                warning_messages.append(f"LLM 看图打标失败，已忽略图像标签：{exc}")
            return []

    def _detect_keyword_hits(self, values: List[str], keywords: set[str]) -> List[str]:
        hits: List[str] = []
        seen = set()
        for value in values:
            lowered = self._canonicalize_tag(value).lower()
            if not lowered:
                continue
            for keyword in keywords:
                if keyword in lowered and keyword not in seen:
                    seen.add(keyword)
                    hits.append(keyword)
        return hits

    def _max_age_restriction(self, current: str, candidate: str) -> str:
        current_rank = PIXIV_AGE_RANK.get(current, 0)
        candidate_rank = PIXIV_AGE_RANK.get(candidate, 0)
        return candidate if candidate_rank > current_rank else current

    def _evaluate_pixiv_safety(
        self,
        *,
        final_tags: List[str],
        source_tags: List[str],
        pixiv_settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        mode = str(pixiv_settings.get("safety_mode") or "auto")
        effective_age = str(pixiv_settings.get("age_restriction") or "all")
        warnings: List[str] = []
        infos: List[str] = []
        errors: List[str] = []

        if mode == "off":
            return {
                "mode": mode,
                "effective_age": effective_age,
                "sexual_hits": [],
                "graphic_hits": [],
                "minor_hits": [],
                "warnings": warnings,
                "infos": infos,
                "errors": errors,
                "blocked": False,
            }

        combined = []
        combined.extend([str(item) for item in source_tags if str(item).strip()])
        combined.extend([str(item) for item in final_tags if str(item).strip()])

        sexual_hits = self._detect_keyword_hits(combined, PIXIV_SEXUAL_KEYWORDS)
        graphic_hits = self._detect_keyword_hits(combined, PIXIV_GRAPHIC_KEYWORDS)
        minor_hits = self._detect_keyword_hits(combined, PIXIV_MINOR_KEYWORDS)
        direct_r18_hits = self._detect_keyword_hits(combined, {"r-18", "r18", "成人向け"})
        direct_r18g_hits = self._detect_keyword_hits(combined, {"r-18g", "r18g"})

        if graphic_hits or direct_r18g_hits:
            upgraded = self._max_age_restriction(effective_age, "R-18G")
            if upgraded != effective_age:
                infos.append("检测到猎奇/重口味标签，已自动提升为 R-18G。")
            effective_age = upgraded
        elif sexual_hits or direct_r18_hits:
            upgraded = self._max_age_restriction(effective_age, "R-18")
            if upgraded != effective_age:
                infos.append("检测到成人标签，已自动提升为 R-18。")
            effective_age = upgraded

        blocked = False
        if minor_hits and (sexual_hits or graphic_hits or direct_r18_hits or direct_r18g_hits):
            blocked = True
            errors.append("检测到疑似未成年/幼态与成人或猎奇标签组合，已阻止自动投稿。")
        elif minor_hits:
            warnings.append("检测到幼态/未成年相关标签，请务必人工复核投稿分级和内容。")

        if mode == "strict" and (sexual_hits or graphic_hits or minor_hits):
            blocked = True
            errors.append("当前启用了严格拦截策略，命中风险标签后不会自动投稿。")

        return {
            "mode": mode,
            "effective_age": effective_age,
            "sexual_hits": sexual_hits,
            "graphic_hits": graphic_hits,
            "minor_hits": minor_hits,
            "warnings": warnings,
            "infos": infos,
            "errors": errors,
            "blocked": blocked,
        }

    def _build_pixiv_tags(
        self,
        image_path: Path,
        pixiv_settings: Dict[str, Any],
        pipeline_settings: Dict[str, Any],
        *,
        info_messages: Optional[List[str]] = None,
        warning_messages: Optional[List[str]] = None,
    ) -> List[str]:
        raw = str(pixiv_settings.get("tags") or "").replace("\n", ",")
        manual_tags: List[str] = []
        for item in raw.split(","):
            tag = self._canonicalize_tag(item)
            if tag:
                manual_tags.append(tag)

        strategy = str(pixiv_settings.get("tag_language") or "ja_priority")
        metadata_tags: List[str] = []
        lora_tags: List[str] = []

        if pixiv_settings.get("use_metadata_tags", True):
            prompt_tags, extracted_loras = self._extract_metadata_tags(Path(image_path))
            metadata_tags.extend(prompt_tags)
            if pixiv_settings.get("include_lora_tags", True):
                lora_tags.extend(extracted_loras)

        llm_image_tags = self._generate_llm_pixiv_image_tags(
            Path(image_path),
            pixiv_settings,
            info_messages=info_messages,
            warning_messages=warning_messages,
        )
        llm_metadata_tags = self._generate_llm_pixiv_tags(
            metadata_tags,
            pixiv_settings,
            image_tags=llm_image_tags,
            info_messages=info_messages,
            warning_messages=warning_messages,
        )

        fixed_tags: List[str] = []
        workflow_tags: List[str] = []

        if pixiv_settings.get("add_original_tag", True):
            fixed_tags.append("オリジナル")
        if pixiv_settings.get("ai_generated", False):
            fixed_tags.append("AIイラスト")

        if pipeline_settings["upscale"]["enabled"]:
            engine = normalize_upscale_engine(pipeline_settings["upscale"]["engine"])
            model_name = pipeline_settings["upscale"].get("model") or ""
            scale = int(pipeline_settings["upscale"]["scale"])

            if pixiv_settings.get("add_upscale_tag", True):
                workflow_tags.append("超解像")
            if pixiv_settings.get("add_engine_tag", True):
                engine_labels = {
                    "realesrgan": ["Real-ESRGAN"],
                    "realcugan": ["Real-CUGAN"],
                    "apisr": ["APISR"],
                }
                workflow_tags.extend(engine_labels.get(engine, [UPSCALE_ENGINES.get(engine, engine)]))
            if pixiv_settings.get("add_model_tag", False) and model_name:
                workflow_tags.append(Path(model_name).stem)
            if pixiv_settings.get("add_scale_tag", True):
                workflow_tags.append(f"{scale}x")

        unique_tags: List[str] = []
        seen = set()
        self._append_unique_tags(unique_tags, seen, manual_tags)
        if len(unique_tags) >= PIXIV_TAG_LIMIT:
            return unique_tags[:PIXIV_TAG_LIMIT]
        self._append_unique_tags(unique_tags, seen, fixed_tags)
        if len(unique_tags) >= PIXIV_TAG_LIMIT:
            return unique_tags[:PIXIV_TAG_LIMIT]
        self._append_unique_tags(unique_tags, seen, llm_image_tags)
        if len(unique_tags) >= PIXIV_TAG_LIMIT:
            return unique_tags[:PIXIV_TAG_LIMIT]

        if llm_metadata_tags:
            self._append_unique_tags(unique_tags, seen, llm_metadata_tags)
            if len(unique_tags) >= PIXIV_TAG_LIMIT:
                return unique_tags[:PIXIV_TAG_LIMIT]
        else:
            self._append_unique_tags(unique_tags, seen, llm_image_tags)
            if len(unique_tags) >= PIXIV_TAG_LIMIT:
                return unique_tags[:PIXIV_TAG_LIMIT]
            for tag in metadata_tags:
                self._append_unique_tags(unique_tags, seen, self._localize_pixiv_tag(tag, strategy))
                if len(unique_tags) >= PIXIV_TAG_LIMIT:
                    return unique_tags[:PIXIV_TAG_LIMIT]

        self._append_unique_tags(unique_tags, seen, lora_tags)
        if len(unique_tags) >= PIXIV_TAG_LIMIT:
            return unique_tags[:PIXIV_TAG_LIMIT]
        self._append_unique_tags(unique_tags, seen, workflow_tags)
        return unique_tags[:PIXIV_TAG_LIMIT]

    def _build_pixiv_tag_bundle(
        self,
        image_path: Path,
        pixiv_settings: Dict[str, Any],
        pipeline_settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        infos: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []

        metadata_tags: List[str] = []
        if pixiv_settings.get("use_metadata_tags", True):
            metadata_tags, _ = self._extract_metadata_tags(Path(image_path))

        tags = self._build_pixiv_tags(
            image_path,
            pixiv_settings,
            pipeline_settings,
            info_messages=infos,
            warning_messages=warnings,
        )
        safety = self._evaluate_pixiv_safety(
            final_tags=tags,
            source_tags=metadata_tags,
            pixiv_settings=pixiv_settings,
        )
        infos.extend(safety["infos"])
        warnings.extend(safety["warnings"])
        errors.extend(safety["errors"])
        return {
            "tags": tags,
            "infos": infos,
            "warnings": warnings,
            "errors": errors,
            "safety": safety,
        }

    def _resolve_pixiv_preview_source(self, batch_settings: Optional[Dict[str, Any]] = None) -> Path:
        if self._current_image_path and Path(self._current_image_path).exists():
            return Path(self._current_image_path)

        input_dir_raw = str((batch_settings or {}).get("input_dir", "") or "").strip()
        if input_dir_raw:
            input_dir = Path(input_dir_raw).expanduser()
            if input_dir.exists() and input_dir.is_dir():
                candidates = sorted(
                    [
                        path
                        for path in input_dir.iterdir()
                        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
                    ],
                    key=lambda item: item.name.lower(),
                )
                if candidates:
                    return candidates[0]

        raise RuntimeError("请先加载一张图片，或先填写批量输入目录后再预览 Pixiv 投稿")

    def _predict_pixiv_upload_name(self, result_path: Path) -> Tuple[str, str, bool]:
        suffix = result_path.suffix.lower()
        if suffix in PIXIV_UPLOAD_SUFFIXES:
            return result_path.name, suffix.lstrip(".").upper(), False
        return f"{result_path.stem}.png", "PNG", True

    def _prepare_pixiv_upload_image(self, result_path: Path, temp_dir: Path) -> Tuple[Path, Optional[str]]:
        upload_name, _, requires_conversion = self._predict_pixiv_upload_name(result_path)
        if not requires_conversion:
            return result_path, None

        temp_dir.mkdir(parents=True, exist_ok=True)
        converted_path = temp_dir / upload_name
        with Image.open(result_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.save(converted_path, format="PNG", optimize=True)
        return (
            converted_path,
            f"Pixiv 不支持 {result_path.suffix.lower()}，已临时转为 PNG 上传：{result_path.name} -> {converted_path.name}",
        )

    def _format_bytes(self, size: int) -> str:
        value = float(max(0, int(size or 0)))
        units = ["B", "KB", "MB", "GB"]
        index = 0
        while value >= 1024 and index < len(units) - 1:
            value /= 1024
            index += 1
        return f"{value:.1f} {units[index]}" if index else f"{int(value)} {units[index]}"

    def _build_pixiv_submission_preview(
        self,
        image_path: Path,
        pipeline_settings: Dict[str, Any],
        pixiv_settings: Dict[str, Any],
        batch_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_manual = str(pixiv_settings.get("tags") or "").replace("\n", ",")
        manual_count = len([self._canonicalize_tag(item) for item in raw_manual.split(",") if self._canonicalize_tag(item)])
        predicted_result = image_path.with_name(image_path.name)
        upload_file_name, upload_format, requires_conversion = self._predict_pixiv_upload_name(predicted_result)
        visibility_labels = {
            "public": "公开",
            "mypixiv": "My pixiv",
            "private": "非公开",
        }
        upload_mode_labels = {
            "browser": "浏览器自动填写",
            "direct": "Cookie + CSRF 直传",
        }
        age_labels = {
            "all": "全年龄",
            "R-18": "R-18",
            "R-18G": "R-18G",
        }

        errors: List[str] = []
        warnings: List[str] = []
        infos: List[str] = []
        title = self._build_pixiv_title(image_path, pixiv_settings)
        tag_bundle = self._build_pixiv_tag_bundle(image_path, pixiv_settings, pipeline_settings)
        tags = tag_bundle["tags"]
        infos.extend(tag_bundle["infos"])
        warnings.extend(tag_bundle["warnings"])
        errors.extend(tag_bundle["errors"])
        effective_age_restriction = tag_bundle["safety"]["effective_age"]

        if not pixiv_settings.get("enabled", False):
            infos.append("当前还没有启用 Pixiv 自动上传；这次只是生成投稿预览，不会实际投稿。")
        if not tags:
            errors.append("当前配置生成的标签为空，Pixiv 投稿至少需要 1 个标签。")
        if manual_count >= PIXIV_TAG_LIMIT:
            warnings.append("手动标签已经占满 10 个名额，自动标签将不会再追加。")
        if requires_conversion:
            warnings.append(
                f"当前处理结果若保留 {predicted_result.suffix.lower()}，上传前会自动转为 PNG：{predicted_result.name} -> {upload_file_name}"
            )

        source_size = image_path.stat().st_size
        if source_size > PIXIV_UPLOAD_MAX_BYTES:
            warnings.append(
                f"当前源图已有 {self._format_bytes(source_size)}，Pixiv 官方单张限制是 32 MB；处理结果若仍超限将无法投稿。"
            )

        if pixiv_settings.get("upload_mode") == "direct":
            if not pixiv_settings.get("cookie"):
                errors.append("直传模式缺少 Cookie。")
            if not pixiv_settings.get("csrf_token"):
                errors.append("直传模式缺少 CSRF Token。")
            if not pixiv_settings.get("auto_submit", True):
                warnings.append("直传模式没有停留在网页上手动确认的步骤，实际会直接提交。")
        elif not pixiv_settings.get("auto_submit", True):
            infos.append("当前是手动确认模式，浏览器会停在投稿页，等你检查完标题、标签和说明后再投稿。")

        input_dir_raw = str((batch_settings or {}).get("input_dir", "") or "").strip()
        if input_dir_raw:
            input_dir = Path(input_dir_raw).expanduser()
            if input_dir.exists() and input_dir.is_dir():
                image_count = len(
                    [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
                )
                if image_count > 1 and not pixiv_settings.get("auto_submit", True):
                    infos.append(f"批量目录里检测到 {image_count} 张图片，建议先用首张确认投稿内容。")

        return {
            "fileName": image_path.name,
            "sourcePath": str(image_path),
            "sourceSizeLabel": self._format_bytes(source_size),
            "title": title,
            "caption": str(pixiv_settings.get("caption") or ""),
            "tags": tags,
            "tagCount": len(tags),
            "maxTags": PIXIV_TAG_LIMIT,
            "uploadMode": pixiv_settings["upload_mode"],
            "uploadModeLabel": upload_mode_labels.get(pixiv_settings["upload_mode"], pixiv_settings["upload_mode"]),
            "visibility": pixiv_settings["visibility"],
            "visibilityLabel": visibility_labels.get(pixiv_settings["visibility"], pixiv_settings["visibility"]),
            "ageRestriction": effective_age_restriction,
            "ageRestrictionLabel": age_labels.get(
                effective_age_restriction, effective_age_restriction
            ),
            "configuredAgeRestriction": pixiv_settings["age_restriction"],
            "submitMode": "auto" if pixiv_settings.get("auto_submit", True) else "manual",
            "submitModeLabel": "自动投稿" if pixiv_settings.get("auto_submit", True) else "手动确认",
            "uploadFileName": upload_file_name,
            "uploadFormat": upload_format,
            "uploadLimitLabel": "32 MB",
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
        }

    def _run_pipeline(self, input_path: Path, output_path: Path, settings: Dict[str, Any]) -> Tuple[Path, List[str]]:
        if output_path.suffix.lower() not in IMAGE_SUFFIXES:
            output_path = output_path.with_suffix(".png")

        logs: List[str] = [f"开始处理：{input_path.name}"]
        order = [item.strip() for item in settings["order"].split("->")]
        current_path = input_path
        current_scale = 1

        with tempfile.TemporaryDirectory(prefix="pywebview_pipeline_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)

            for step in order:
                step_name = step.strip()

                if step_name == "upscale" and settings["upscale"]["enabled"]:
                    upscale = settings["upscale"]
                    model_name = upscale["custom_model_path"] or upscale["model"]
                    processor = UpscaleProcessor(
                        engine=upscale["engine"],
                        model_name=model_name,
                        realcugan_noise=upscale["noise"],
                    )
                    step_output = tmp_dir / f"step_upscale_{upscale['scale']}x.png"
                    result = processor.process(current_path, step_output, scale=upscale["scale"])
                    if not result:
                        raise RuntimeError("超分处理失败")
                    current_path = Path(result)
                    current_scale *= int(upscale["scale"])
                    logs.append(f"超分完成：{UPSCALE_ENGINES[upscale['engine']]} {upscale['scale']}x")

                elif step_name == "mosaic" and settings["mosaic"]["enabled"] and settings["regions"]:
                    mosaic = settings["mosaic"]
                    step_output = tmp_dir / "step_mosaic.png"
                    scaled_regions = self._scale_regions(settings["regions"], current_scale)
                    kwargs: Dict[str, Any] = {}
                    if mosaic["mode"] == "pixelate":
                        kwargs["pixel_size"] = mosaic["pixel_size"]
                    else:
                        kwargs["radius"] = mosaic["blur_radius"]
                    MosaicProcessor().process(
                        current_path,
                        step_output,
                        regions=scaled_regions,
                        mode=mosaic["mode"],
                        **kwargs,
                    )
                    current_path = step_output
                    logs.append(f"打码完成：{len(scaled_regions)} 个区域")

                elif step_name == "watermark" and settings["watermark"]["enabled"]:
                    wm = settings["watermark"]
                    step_output = tmp_dir / "step_watermark.jpg"
                    WatermarkProcessor(
                        {
                            "text": wm["text"],
                            "font_size": wm["font_size"],
                            "font_path": wm.get("font_path", ""),
                            "color": self._hex_to_rgb(wm["color"]),
                            "opacity": wm["opacity"],
                            "position": wm["position"],
                            "rotation_range": [wm["rotation_min"], wm["rotation_max"]],
                            "offset_range": [-15, 15] if wm["random_offset"] else [0, 0],
                        }
                    ).process(current_path, step_output)
                    current_path = step_output
                    logs.append("水印完成")

            self._write_final_output(current_path, output_path)
            logs.append("处理完成")
            return output_path, logs

    def _build_image_payload(self, path: Path, label: str) -> Dict[str, Any]:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            preview = image.copy()
            preview.thumbnail((1800, 1800), _resampling())
            data_url = self._image_to_data_url(preview)
        return {
            "label": label,
            "src": data_url,
            "width": width,
            "height": height,
            "fileName": path.name,
            "path": str(path),
        }

    def _image_to_data_url(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        fmt = "PNG" if image.mode in {"RGBA", "LA"} else "JPEG"
        if fmt == "PNG":
            image.save(buffer, format="PNG", optimize=True)
            mime = "image/png"
        else:
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(buffer, format="JPEG", quality=92, optimize=True)
            mime = "image/jpeg"
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def _hex_to_rgb(self, value: str) -> List[int]:
        cleaned = value.strip().lstrip("#")
        if len(cleaned) != 6:
            return [255, 255, 255]
        return [int(cleaned[i:i + 2], 16) for i in (0, 2, 4)]

    def _scale_regions(self, regions: List[Tuple[int, int, int, int]], factor: int) -> List[Tuple[int, int, int, int]]:
        if factor == 1:
            return list(regions)
        scaled: List[Tuple[int, int, int, int]] = []
        for x1, y1, x2, y2 in regions:
            scaled.append((int(x1 * factor), int(y1 * factor), int(x2 * factor), int(y2 * factor)))
        return scaled

    def _preferred_extension(self, settings: Dict[str, Any]) -> str:
        if settings["upscale"]["enabled"]:
            return ".png"
        return ".jpg" if settings["watermark"]["enabled"] else ".png"

    def _suggest_suffix(self, settings: Dict[str, Any]) -> str:
        return f"preview{self._preferred_extension(settings)}"

    def _write_final_output(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        suffix = destination.suffix.lower()

        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            with Image.open(source) as image:
                image = ImageOps.exif_transpose(image)
                if suffix in {".jpg", ".jpeg"}:
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(destination, format="JPEG", quality=95, optimize=True)
                elif suffix == ".png":
                    image.save(destination, format="PNG", optimize=True)
                elif suffix == ".webp":
                    image.save(destination, format="WEBP", quality=95, method=6)
                else:
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(destination, format="BMP")
        else:
            shutil.copy2(source, destination)

    def _first_path(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, (list, tuple)):
            return str(value[0]) if value else None
        return str(value)

    def _error_response(self, exc: Exception) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def main():
    entrypoint = WEBUI_DIR / "index.html"
    if not entrypoint.exists():
        raise FileNotFoundError(f"Missing web UI entrypoint: {entrypoint}")

    _write_boot_log("启动 webview_app")
    _write_boot_log(f"Python: {sys.executable} ({sys.version.split()[0]})")
    api = WebviewBridge()
    _write_boot_log("WebviewBridge 初始化完成")
    window = webview.create_window(
        title="Image Workbench",
        url=str(entrypoint.resolve()),
        js_api=api,
        width=1600,
        height=980,
        min_size=(1280, 780),
        background_color="#0f172a",
        text_select=False,
    )
    api._attach_window(window)
    _write_boot_log("窗口创建完成，准备进入 webview.start")
    webview.start(debug=False, http_server=True)
    _write_boot_log("webview.start 已退出")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _write_boot_log("启动异常:\n" + traceback.format_exc())
        raise












