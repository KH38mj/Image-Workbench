#!/usr/bin/env python3
"""
鍥剧墖澶勭悊宸ュ叿 - 鍥惧舰鐣岄潰鐗?"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter import font as tkfont
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
import threading
import json
import os
import random
import re

from main import (
    WatermarkProcessor, MosaicProcessor, UpscaleProcessor,
    UPSCALE_ENGINES, UPSCALE_MODELS, UPSCALE_SCALE_OPTIONS,
    normalize_upscale_engine
)
from pixiv_uploader import (
    PixivUploader,
    PIXIV_AGE_OPTIONS,
    PIXIV_BROWSER_CHANNELS,
    PIXIV_VISIBILITY_OPTIONS,
)


class ImageProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("图片处理工具")
        self.root.geometry("1120x820")
        self.root.minsize(1040, 760)

        # 閰嶇疆
        self.config_file = Path(__file__).parent / "gui_config.json"
        self.load_config()

        # 褰撳墠鍥剧墖
        self.current_image = None
        self.preview_image = None
        self.preview_photo = None

        # 鎵撶爜鍖哄煙
        self.mosaic_regions = []
        self.temp_rects = []

        self.setup_ui()
        self.apply_theme()

    def load_config(self):
        """鍔犺浇閰嶇疆"""
        default_config = {
            "watermark": {
                "text": "YourName",
                "font_size": 48,
                "color": [255, 255, 255],
                "opacity": 0.6,
                "position": "bottom-right",
                "rotation_min": -10,
                "rotation_max": 10,
                "random_offset": True,
            },
            "mosaic": {
                "mode": "pixelate",
                "pixel_size": 10,
                "blur_radius": 15,
            },
            "upscale": {
                "engine": "realesrgan",
                "model": "RealESRGAN_x4plus_anime_6B.pth",
                "custom_model_path": "",
                "scale": 4,
                "noise": -1,
            },
            "pixiv": {
                "enabled": False,
                "browser_channel": "msedge",
                "profile_dir": str(Path(__file__).parent / ".pixiv_profile"),
                "title_template": "{stem}",
                "caption": "",
                "tags": "",
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
            },
            "last_input_dir": "",
            "last_output_dir": "",
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for key, value in loaded.items():
                        if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                            default_config[key].update(value)
                        else:
                            default_config[key] = value
            except Exception:
                pass

        self.config = default_config

    def save_config(self):
        """淇濆瓨閰嶇疆"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"淇濆瓨閰嶇疆澶辫触: {e}")

    def setup_ui(self):
        """璁剧疆鐣岄潰"""
        # 涓诲灞傚鍣?
        self.app_shell = ttk.Frame(self.root, style="App.TFrame", padding=16)
        self.app_shell.pack(fill=tk.BOTH, expand=True)

        # 涓诲竷灞€
        self.main_paned = ttk.PanedWindow(self.app_shell, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # left control card
        self.left_card = ttk.Frame(self.main_paned, style="Card.TFrame", padding=(18, 16, 18, 18))
        self.main_paned.add(self.left_card, weight=5)
        self.left_frame = ttk.Frame(self.left_card, style="Card.TFrame")
        self.left_frame.pack(fill=tk.BOTH, expand=True)

        # right preview card
        self.right_card = ttk.Frame(self.main_paned, style="PreviewCard.TFrame", padding=(18, 16, 18, 18))
        self.main_paned.add(self.right_card, weight=6)
        self.right_frame = ttk.Frame(self.right_card, style="PreviewCard.TFrame")
        self.right_frame.pack(fill=tk.BOTH, expand=True)

        self.setup_control_panel()
        self.setup_preview_panel()

    def setup_control_panel(self):
        """璁剧疆鎺у埗闈㈡澘"""
        header = ttk.Frame(self.left_frame, style="Card.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(header, text="处理面板", style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="把水印、打码、超分和批量上传整理到同一块工作区里。",
            style="CardSubtle.TLabel",
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # notebook tabs
        self.notebook = ttk.Notebook(self.left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # === 姘村嵃鏍囩椤?===
        self.watermark_frame = ttk.Frame(self.notebook, style="Page.TFrame")
        self.notebook.add(self.watermark_frame, text="水印设置")
        self.setup_watermark_tab()

        # === 鎵撶爜鏍囩椤?===
        self.mosaic_frame = ttk.Frame(self.notebook, style="Page.TFrame")
        self.notebook.add(self.mosaic_frame, text="打码设置")
        self.setup_mosaic_tab()

        # === 瓒呭垎鏍囩椤?===
        self.upscale_frame = ttk.Frame(self.notebook, style="Page.TFrame")
        self.notebook.add(self.upscale_frame, text="超分设置")
        self.setup_upscale_tab()

        # === 鎵归噺澶勭悊鏍囩椤?===
        self.batch_frame = ttk.Frame(self.notebook, style="Page.TFrame")
        self.notebook.add(self.batch_frame, text="批量处理")
        self.setup_batch_tab()

    def setup_watermark_tab(self):
        """璁剧疆姘村嵃鏍囩椤?"""
        frame = ttk.Frame(self.watermark_frame, padding=14, style="Page.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        # 鏂囧瓧
        row = 0
        ttk.Label(frame, text="水印文字:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.wm_text = ttk.Entry(frame)
        self.wm_text.insert(0, self.config["watermark"]["text"])
        self.wm_text.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)

        # 瀛椾綋澶у皬
        row += 1
        ttk.Label(frame, text="字体大小:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.wm_font_size = ttk.Spinbox(frame, from_=12, to=200, width=10)
        self.wm_font_size.set(self.config["watermark"]["font_size"])
        self.wm_font_size.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        # 棰滆壊閫夋嫨
        row += 1
        ttk.Label(frame, text="文字颜色:").grid(row=row, column=0, sticky=tk.W, pady=5)
        color_frame = ttk.Frame(frame)
        color_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        self.wm_color_preview = tk.Canvas(color_frame, width=30, height=20, bg=self._rgb_to_hex(self.config["watermark"]["color"]))
        self.wm_color_preview.pack(side=tk.LEFT)
        self.wm_color_btn = ttk.Button(color_frame, text="选择颜色", command=self.choose_color)
        self.wm_color_btn.pack(side=tk.LEFT, padx=5)
        self.wm_color = self.config["watermark"]["color"].copy()

        # opacity
        row += 1
        ttk.Label(frame, text="透明度:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.wm_opacity = ttk.Scale(frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL)
        self.wm_opacity.set(self.config["watermark"]["opacity"])
        self.wm_opacity.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)

        # 浣嶇疆
        row += 1
        ttk.Label(frame, text="位置:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.wm_position = ttk.Combobox(frame, values=[
            "center", "top-left", "top-right", "bottom-left", "bottom-right"
        ], state="readonly")
        self.wm_position.set(self.config["watermark"]["position"])
        self.wm_position.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        # 鏃嬭浆鑼冨洿
        row += 1
        ttk.Label(frame, text="旋转角度范围:").grid(row=row, column=0, sticky=tk.W, pady=5)
        rotation_frame = ttk.Frame(frame)
        rotation_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        self.wm_rot_min = ttk.Spinbox(rotation_frame, from_=-45, to=45, width=6)
        self.wm_rot_min.set(self.config["watermark"]["rotation_min"])
        self.wm_rot_min.pack(side=tk.LEFT)
        ttk.Label(rotation_frame, text="~").pack(side=tk.LEFT, padx=2)
        self.wm_rot_max = ttk.Spinbox(rotation_frame, from_=-45, to=45, width=6)
        self.wm_rot_max.set(self.config["watermark"]["rotation_max"])
        self.wm_rot_max.pack(side=tk.LEFT)

        # 闅忔満鍋忕Щ
        row += 1
        self.wm_random_offset = tk.BooleanVar(value=self.config["watermark"]["random_offset"])
        ttk.Checkbutton(frame, text="启用随机偏移", variable=self.wm_random_offset).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=5)

        # 棰勮鎸夐挳
        row += 1
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="加载图片预览", command=self.load_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame,
            text="应用水印预览",
            command=self.preview_watermark,
            style="Accent.TButton",
        ).pack(side=tk.LEFT, padx=5)

        frame.columnconfigure(1, weight=1)

    def setup_mosaic_tab(self):
        """璁剧疆鎵撶爜鏍囩椤?"""
        frame = ttk.Frame(self.mosaic_frame, padding=14, style="Page.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        # 妯″紡閫夋嫨
        row = 0
        ttk.Label(frame, text="打码模式:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.mosaic_mode = ttk.Combobox(frame, values=["pixelate", "blur"], state="readonly")
        self.mosaic_mode.set(self.config["mosaic"]["mode"])
        self.mosaic_mode.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.mosaic_mode.bind("<<ComboboxSelected>>", self.on_mosaic_mode_change)

        # 鍍忕礌澶у皬
        row += 1
        self.pixel_size_label = ttk.Label(frame, text="马赛克像素大小:")
        self.pixel_size_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.mosaic_pixel_size = ttk.Spinbox(frame, from_=2, to=50, width=10)
        self.mosaic_pixel_size.set(self.config["mosaic"]["pixel_size"])
        self.mosaic_pixel_size.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        # 妯＄硦鍗婂緞
        row += 1
        self.blur_radius_label = ttk.Label(frame, text="模糊半径:")
        self.blur_radius_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.mosaic_blur_radius = ttk.Spinbox(frame, from_=1, to=50, width=10)
        self.mosaic_blur_radius.set(self.config["mosaic"]["blur_radius"])
        self.mosaic_blur_radius.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        # 鍖哄煙閫夋嫨璇存槑
        row += 1
        ttk.Label(frame, text="区域选择:", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 5))

        row += 1
        ttk.Label(frame, text="在右侧预览图中拖拽选择区域").grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=5)

        # 鍖哄煙鍒楄〃
        row += 1
        self.region_listbox = tk.Listbox(frame, height=6)
        self.region_listbox.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=5)

        # 鍖哄煙鎸夐挳
        row += 1
        region_btn_frame = ttk.Frame(frame)
        region_btn_frame.grid(row=row, column=0, columnspan=2, pady=5)

        ttk.Button(region_btn_frame, text="删除选中区域", command=self.delete_region).pack(side=tk.LEFT, padx=5)
        ttk.Button(region_btn_frame, text="清空所有区域", command=self.clear_regions).pack(side=tk.LEFT, padx=5)

        # 棰勮鎸夐挳
        row += 1
        ttk.Button(frame, text="应用打码预览", command=self.preview_mosaic, style="Accent.TButton").grid(
            row=row, column=0, columnspan=2, pady=20)

        # initialize mosaic controls
        self.on_mosaic_mode_change()

        frame.columnconfigure(1, weight=1)

    def setup_upscale_tab(self):
        """璁剧疆瓒呭垎鏍囩椤?- 澶氬紩鎿庢敮鎸?"""
        frame = ttk.Frame(self.upscale_frame, padding=14, style="Page.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        # 寮曟搸閫夋嫨
        ttk.Label(frame, text="超分引擎:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.upscale_engine = ttk.Combobox(frame, values=list(UPSCALE_ENGINES.keys()), state="readonly")
        try:
            default_engine = normalize_upscale_engine(self.config["upscale"].get("engine", "realesrgan"))
        except Exception:
            default_engine = "realesrgan"
        self.upscale_engine.set(default_engine)
        self.upscale_engine.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.upscale_engine.bind("<<ComboboxSelected>>", self.on_upscale_engine_change)

        # 妯″瀷閫夋嫨
        row += 1
        ttk.Label(frame, text="超分模型:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.upscale_model = ttk.Combobox(frame, state="readonly")
        self.upscale_model.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)
        self.upscale_model.bind("<<ComboboxSelected>>", self.on_upscale_model_change)

        row += 1
        ttk.Label(frame, text="自定义权重:").grid(row=row, column=0, sticky=tk.W, pady=5)
        custom_model_frame = ttk.Frame(frame)
        custom_model_frame.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)
        self.upscale_custom_model = ttk.Entry(custom_model_frame)
        self.upscale_custom_model.insert(0, self.config["upscale"].get("custom_model_path", ""))
        self.upscale_custom_model.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.upscale_custom_model_btn = ttk.Button(
            custom_model_frame,
            text="浏览",
            command=self.browse_upscale_model,
        )
        self.upscale_custom_model_btn.pack(side=tk.LEFT, padx=5)

        # Real-CUGAN 闄嶅櫔
        row += 1
        self.upscale_noise_label = ttk.Label(frame, text="降噪等级:")
        self.upscale_noise_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.upscale_noise = ttk.Combobox(frame, values=[-1, 0, 1, 2, 3], state="readonly", width=10)
        self.upscale_noise.set(str(self.config["upscale"].get("noise", -1)))
        self.upscale_noise.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        # 鏀惧ぇ鍊嶆暟
        row += 1
        ttk.Label(frame, text="放大倍数:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.upscale_scale = ttk.Combobox(frame, state="readonly", width=10)
        self.upscale_scale.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        # 鎻愮ず淇℃伅
        row += 1
        self.upscale_info_label = ttk.Label(frame, text="", wraplength=350, foreground="gray", justify=tk.LEFT)
        self.upscale_info_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=20)

        # 娴嬭瘯鎸夐挳
        row += 1
        ttk.Button(frame, text="测试超分功能", command=self.test_upscale, style="Accent.TButton").grid(
            row=row, column=0, columnspan=2, pady=10)

        frame.columnconfigure(1, weight=1)

        # initialize upscale controls
        self.update_upscale_options(reset_model=True, reset_scale=True)

    def on_upscale_engine_change(self, event=None):
        """瓒呭垎寮曟搸鍒囨崲銆?"""
        self.update_upscale_options(reset_model=True, reset_scale=True)

    def on_upscale_model_change(self, event=None):
        """瓒呭垎妯″瀷鍒囨崲銆?"""
        self.update_upscale_options(reset_model=False, reset_scale=False)

    def update_upscale_options(self, reset_model=False, reset_scale=False):
        """鏍规嵁寮曟搸鍒锋柊妯″瀷銆佸€嶇巼銆佹彁绀轰俊鎭€?"""
        try:
            engine = normalize_upscale_engine(self.upscale_engine.get())
        except Exception:
            engine = "realesrgan"
            self.upscale_engine.set(engine)

        models = UPSCALE_MODELS.get(engine, [])
        self.upscale_model.configure(values=models)

        current_model = self.upscale_model.get()
        saved_model = self.config.get("upscale", {}).get("model")
        if reset_model or current_model not in models:
            if saved_model in models:
                self.upscale_model.set(saved_model)
            elif models:
                self.upscale_model.set(models[0])
            else:
                self.upscale_model.set("")

        scales = [str(v) for v in UPSCALE_SCALE_OPTIONS.get(engine, [4])]
        self.upscale_scale.configure(values=scales)

        current_scale = str(self.upscale_scale.get()) if self.upscale_scale.get() != "" else ""
        saved_scale = str(self.config.get("upscale", {}).get("scale", "4"))
        if reset_scale or current_scale not in scales:
            if saved_scale in scales:
                self.upscale_scale.set(saved_scale)
            elif scales:
                self.upscale_scale.set(scales[0])
            else:
                self.upscale_scale.set("4")

        if engine == "realcugan":
            self.upscale_noise_label.configure(state=tk.NORMAL)
            self.upscale_noise.configure(state="readonly")
        else:
            self.upscale_noise_label.configure(state=tk.DISABLED)
            self.upscale_noise.configure(state=tk.DISABLED)

        custom_model_state = "normal" if engine == "realesrgan" else "disabled"
        self.upscale_custom_model.configure(state=custom_model_state)
        self.upscale_custom_model_btn.configure(state=custom_model_state)

        info_map = {
            "realesrgan": "说明：\n• 首次使用会自动下载 Real-ESRGAN 模型\n• 也支持本地 .pth 权重路径\n• 可放在项目 models 或 ComfyUI/models/upscale_models",
            "realcugan": "说明：\n• Real-CUGAN 适合动漫风格图片\n• 可设置降噪等级（-1 保守）\n• 通过 Final2x-core 后端执行",
            "apisr": "说明：\n• APISR-RRDB 适合高质量细节重建\n• 当前提供 2x/4x 选项\n• 通过 Final2x-core 后端执行",
        }
        self.upscale_info_label.configure(text=info_map.get(engine, ""))

    def setup_batch_tab(self):
        """璁剧疆鎵归噺澶勭悊鏍囩椤?"""
        frame = ttk.Frame(self.batch_frame, padding=14, style="Page.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        # 杈撳叆鐩綍
        row = 0
        ttk.Label(frame, text="输入目录:").grid(row=row, column=0, sticky=tk.W, pady=5)
        input_frame = ttk.Frame(frame)
        input_frame.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)

        self.batch_input = ttk.Entry(input_frame)
        self.batch_input.insert(0, self.config["last_input_dir"])
        self.batch_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(input_frame, text="浏览", command=lambda: self.browse_dir(self.batch_input)).pack(side=tk.LEFT, padx=5)

        # 杈撳嚭鐩綍
        row += 1
        ttk.Label(frame, text="输出目录:").grid(row=row, column=0, sticky=tk.W, pady=5)
        output_frame = ttk.Frame(frame)
        output_frame.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)

        self.batch_output = ttk.Entry(output_frame)
        self.batch_output.insert(0, self.config["last_output_dir"])
        self.batch_output.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(output_frame, text="浏览", command=lambda: self.browse_dir(self.batch_output)).pack(side=tk.LEFT, padx=5)

        # 澶勭悊姝ラ
        row += 1
        ttk.Label(frame, text="处理步骤:", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))

        self.do_watermark = tk.BooleanVar(value=True)
        self.do_mosaic = tk.BooleanVar(value=False)
        self.do_upscale = tk.BooleanVar(value=False)

        ttk.Checkbutton(frame, text="添加水印", variable=self.do_watermark).grid(
            row=row+1, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(frame, text="打码处理", variable=self.do_mosaic).grid(
            row=row+2, column=0, sticky=tk.W, pady=2)
        ttk.Checkbutton(frame, text="超分处理", variable=self.do_upscale).grid(
            row=row+3, column=0, sticky=tk.W, pady=2)

        # 澶勭悊椤哄簭
        row += 4
        ttk.Label(frame, text="处理顺序:").grid(row=row, column=0, sticky=tk.W, pady=10)
        self.process_order = ttk.Combobox(frame, values=[
            "upscale -> mosaic -> watermark",
            "mosaic -> upscale -> watermark",
            "watermark -> mosaic",
        ], state="readonly")
        self.process_order.set("upscale -> mosaic -> watermark")
        self.process_order.grid(row=row, column=1, sticky=tk.W, pady=10, padx=5)

        # Pixiv upload
        row += 1
        pixiv_frame = ttk.LabelFrame(frame, text="Pixiv 上传", padding=10)
        pixiv_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(5, 15))

        p_row = 0
        self.do_pixiv_upload = tk.BooleanVar(value=self.config["pixiv"]["enabled"])
        ttk.Checkbutton(
            pixiv_frame,
            text="处理完成后自动上传到 Pixiv",
            variable=self.do_pixiv_upload,
        ).grid(row=p_row, column=0, columnspan=3, sticky=tk.W, pady=2)

        p_row += 1
        ttk.Label(pixiv_frame, text="浏览器:").grid(row=p_row, column=0, sticky=tk.W, pady=5)
        self.pixiv_browser = ttk.Combobox(pixiv_frame, values=PIXIV_BROWSER_CHANNELS, state="readonly", width=12)
        self.pixiv_browser.set(self.config["pixiv"]["browser_channel"])
        self.pixiv_browser.grid(row=p_row, column=1, sticky=tk.W, pady=5, padx=5)

        p_row += 1
        ttk.Label(pixiv_frame, text="配置目录:").grid(row=p_row, column=0, sticky=tk.W, pady=5)
        profile_frame = ttk.Frame(pixiv_frame)
        profile_frame.grid(row=p_row, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)
        self.pixiv_profile_dir = ttk.Entry(profile_frame)
        self.pixiv_profile_dir.insert(0, self.config["pixiv"]["profile_dir"])
        self.pixiv_profile_dir.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(profile_frame, text="浏览", command=lambda: self.browse_dir(self.pixiv_profile_dir)).pack(side=tk.LEFT, padx=5)

        p_row += 1
        ttk.Label(pixiv_frame, text="标题模板:").grid(row=p_row, column=0, sticky=tk.W, pady=5)
        self.pixiv_title_template = ttk.Entry(pixiv_frame)
        self.pixiv_title_template.insert(0, self.config["pixiv"]["title_template"])
        self.pixiv_title_template.grid(row=p_row, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)

        p_row += 1
        ttk.Label(pixiv_frame, text="标签:").grid(row=p_row, column=0, sticky=tk.W, pady=5)
        self.pixiv_tags = ttk.Entry(pixiv_frame)
        self.pixiv_tags.insert(0, self.config["pixiv"]["tags"])
        self.pixiv_tags.grid(row=p_row, column=1, columnspan=2, sticky=tk.EW, pady=5, padx=5)

        p_row += 1
        self.pixiv_use_metadata_tags = tk.BooleanVar(value=self.config["pixiv"].get("use_metadata_tags", True))
        ttk.Checkbutton(
            pixiv_frame,
            text="从原图 metadata 提取 prompt 标签",
            variable=self.pixiv_use_metadata_tags,
        ).grid(row=p_row, column=0, sticky=tk.W, pady=2)
        self.pixiv_include_lora_tags = tk.BooleanVar(value=self.config["pixiv"].get("include_lora_tags", True))
        ttk.Checkbutton(
            pixiv_frame,
            text="自动追加 LoRA 标签",
            variable=self.pixiv_include_lora_tags,
        ).grid(row=p_row, column=1, sticky=tk.W, pady=2)

        p_row += 1
        self.pixiv_add_original_tag = tk.BooleanVar(value=self.config["pixiv"]["add_original_tag"])
        ttk.Checkbutton(
            pixiv_frame,
            text="自动添加 原创 / オリジナル",
            variable=self.pixiv_add_original_tag,
        ).grid(row=p_row, column=0, sticky=tk.W, pady=2)
        self.pixiv_ai_generated = tk.BooleanVar(value=self.config["pixiv"]["ai_generated"])
        ttk.Checkbutton(
            pixiv_frame,
            text="自动添加 AI生成 / AIイラスト",
            variable=self.pixiv_ai_generated,
        ).grid(row=p_row, column=1, sticky=tk.W, pady=2)
        self.pixiv_auto_submit = tk.BooleanVar(value=self.config["pixiv"]["auto_submit"])
        ttk.Checkbutton(
            pixiv_frame,
            text="填表后自动投稿",
            variable=self.pixiv_auto_submit,
        ).grid(row=p_row, column=2, sticky=tk.W, pady=2)

        p_row += 1
        self.pixiv_add_upscale_tag = tk.BooleanVar(value=self.config["pixiv"].get("add_upscale_tag", True))
        ttk.Checkbutton(
            pixiv_frame,
            text="自动添加 超分 / 超解像",
            variable=self.pixiv_add_upscale_tag,
        ).grid(row=p_row, column=0, sticky=tk.W, pady=2)
        self.pixiv_add_engine_tag = tk.BooleanVar(value=self.config["pixiv"].get("add_engine_tag", True))
        ttk.Checkbutton(
            pixiv_frame,
            text="自动添加 引擎名",
            variable=self.pixiv_add_engine_tag,
        ).grid(row=p_row, column=1, sticky=tk.W, pady=2)
        self.pixiv_add_model_tag = tk.BooleanVar(value=self.config["pixiv"].get("add_model_tag", False))
        ttk.Checkbutton(
            pixiv_frame,
            text="自动添加 模型名",
            variable=self.pixiv_add_model_tag,
        ).grid(row=p_row, column=2, sticky=tk.W, pady=2)

        p_row += 1
        self.pixiv_add_scale_tag = tk.BooleanVar(value=self.config["pixiv"].get("add_scale_tag", True))
        ttk.Checkbutton(
            pixiv_frame,
            text="自动添加 倍率标签",
            variable=self.pixiv_add_scale_tag,
        ).grid(row=p_row, column=0, sticky=tk.W, pady=2)

        p_row += 1
        ttk.Label(pixiv_frame, text="可见范围:").grid(row=p_row, column=0, sticky=tk.W, pady=5)
        self.pixiv_visibility = ttk.Combobox(pixiv_frame, values=PIXIV_VISIBILITY_OPTIONS, state="readonly", width=12)
        self.pixiv_visibility.set(self.config["pixiv"]["visibility"])
        self.pixiv_visibility.grid(row=p_row, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Label(pixiv_frame, text="年龄限制:").grid(row=p_row, column=2, sticky=tk.W, pady=5)
        self.pixiv_age = ttk.Combobox(pixiv_frame, values=PIXIV_AGE_OPTIONS, state="readonly", width=12)
        self.pixiv_age.set(self.config["pixiv"]["age_restriction"])
        self.pixiv_age.grid(row=p_row, column=3, sticky=tk.W, pady=5, padx=5)

        p_row += 1
        ttk.Label(pixiv_frame, text="说明:").grid(row=p_row, column=0, sticky=tk.NW, pady=5)
        self.pixiv_caption = tk.Text(pixiv_frame, height=4, wrap=tk.WORD)
        self.pixiv_caption.grid(row=p_row, column=1, columnspan=3, sticky=tk.EW, pady=5, padx=5)
        self.pixiv_caption.insert("1.0", self.config["pixiv"]["caption"])

        p_row += 1
        ttk.Label(
            pixiv_frame,
            text="标题模板支持 {stem} / {name}。建议先在已登录状态下测试一次自动投稿。",
            foreground="gray",
            wraplength=420,
            justify=tk.LEFT,
        ).grid(row=p_row, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))

        pixiv_frame.columnconfigure(1, weight=1)
        pixiv_frame.columnconfigure(3, weight=1)

        # progress bar
        row += 1
        self.progress = ttk.Progressbar(frame, mode='determinate')
        self.progress.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=20)

        # 鏃ュ織杈撳嚭
        row += 1
        ttk.Label(frame, text="处理日志:").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)

        row += 1
        self.log_text = tk.Text(frame, height=8, wrap=tk.WORD)
        self.log_text.grid(row=row, column=0, columnspan=2, sticky=tk.EW)

        scrollbar = ttk.Scrollbar(frame, command=self.log_text.yview)
        scrollbar.grid(row=row, column=2, sticky=tk.NS)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # start button
        row += 1
        self.start_btn = ttk.Button(frame, text="开始批量处理", command=self.start_batch)
        self.start_btn.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=20)

        frame.columnconfigure(1, weight=1)

    def setup_preview_panel(self):
        """璁剧疆棰勮闈㈡澘"""
        # 鏍囬
        header = ttk.Frame(self.right_frame, style="PreviewCard.TFrame")
        header.pack(fill=tk.X, pady=(0, 10))

        top_row = ttk.Frame(header, style="PreviewCard.TFrame")
        top_row.pack(fill=tk.X)

        title_block = ttk.Frame(top_row, style="PreviewCard.TFrame")
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            title_block,
            text="图片预览工作台",
            style="PreviewTitle.TLabel",
        ).pack(anchor=tk.W)
        self.preview_file_var = tk.StringVar(value="未选择图片")
        ttk.Label(
            title_block,
            textvariable=self.preview_file_var,
            style="PreviewSubtle.TLabel",
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        action_bar = ttk.Frame(top_row, style="PreviewCard.TFrame")
        action_bar.pack(side=tk.RIGHT, anchor=tk.NE)
        ttk.Button(
            action_bar,
            text="加载图片",
            command=self.load_preview,
            style="ToolbarAccent.TButton",
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            action_bar,
            text="还原预览",
            command=self.reset_preview,
            style="Toolbar.TButton",
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            action_bar,
            text="清空选区",
            command=self.clear_regions,
            style="Toolbar.TButton",
        ).pack(side=tk.LEFT)

        ttk.Label(
            header,
            text="拖拽右侧画布来框选打码区域，左侧面板负责配置处理步骤。",
            style="PreviewSubtle.TLabel",
            wraplength=520,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        info_row = ttk.Frame(header, style="PreviewCard.TFrame")
        info_row.pack(fill=tk.X, pady=(12, 0))
        self.preview_size_var = tk.StringVar(value="尺寸: -")
        self.preview_zoom_var = tk.StringVar(value="缩放: -")
        self.preview_region_var = tk.StringVar(value="选区: 0")
        self.preview_status_var = tk.StringVar(value="状态: 等待载入")

        ttk.Label(info_row, textvariable=self.preview_size_var, style="Chip.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(info_row, textvariable=self.preview_zoom_var, style="Chip.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(info_row, textvariable=self.preview_region_var, style="Chip.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(info_row, textvariable=self.preview_status_var, style="AccentChip.TLabel").pack(side=tk.LEFT)

        canvas_wrap = ttk.Frame(self.right_frame, style="CanvasWrap.TFrame", padding=10)
        canvas_wrap.pack(fill=tk.BOTH, expand=True)

        # Canvas 鐢ㄤ簬鏄剧ず鍥剧墖鍜岄€夋嫨鍖哄煙
        self.preview_canvas = tk.Canvas(canvas_wrap, bg="#1f252c", highlightthickness=1)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        # 缁戝畾榧犳爣浜嬩欢鐢ㄤ簬閫夋嫨鍖哄煙
        self.preview_canvas.bind("<Button-1>", self.on_canvas_click)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # 鎻愮ず鏂囧瓧
        self.canvas_text = self.preview_canvas.create_text(
            400, 300, text="点击\"加载图片\"开始",
            fill="white", font=("", 12), tags="hint"
        )

        footer = ttk.Frame(self.right_frame, style="PreviewCard.TFrame")
        footer.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(
            footer,
            text="提示：先点击“加载图片预览”，再进行框选；完成后可直接在左侧测试预览。",
            style="PreviewSubtle.TLabel",
            wraplength=520,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        self.selection_start = None
        self.selection_rect = None
        self.update_preview_workspace()

    def apply_theme(self):
        """搴旂敤涓婚鏍峰紡"""
        palette = {
            "bg": "#eff4fb",
            "panel": "#e7effb",
            "card": "#ffffff",
            "card_soft": "#f7faff",
            "border": "#d8e3f2",
            "text": "#162033",
            "muted": "#607086",
            "accent": "#2563eb",
            "accent_hover": "#3b82f6",
            "accent_pressed": "#1d4ed8",
            "preview": "#0f172a",
            "preview_text": "#dbeafe",
        }
        self.theme = palette

        self.root.configure(bg=palette["bg"])
        self.root.option_add("*TCombobox*Listbox.background", palette["card"])
        self.root.option_add("*TCombobox*Listbox.foreground", palette["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", palette["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_font.configure(family="Microsoft YaHei UI", size=10)
            text_font = tkfont.nametofont("TkTextFont")
            text_font.configure(family="Microsoft YaHei UI", size=10)
            heading_font = tkfont.nametofont("TkHeadingFont")
            heading_font.configure(family="Microsoft YaHei UI", size=10, weight="bold")
        except tk.TclError:
            pass

        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=palette["bg"], foreground=palette["text"])
        style.configure("App.TFrame", background=palette["bg"])
        style.configure("TFrame", background=palette["card"])
        style.configure("Card.TFrame", background=palette["card"])
        style.configure("PreviewCard.TFrame", background=palette["card"])
        style.configure("Page.TFrame", background=palette["card"])
        style.configure("CanvasWrap.TFrame", background=palette["panel"])
        style.configure("TLabel", background=palette["card"], foreground=palette["text"])
        style.configure("Header.TLabel", background=palette["card"], foreground=palette["text"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("CardTitle.TLabel", background=palette["card"], foreground=palette["text"], font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("CardSubtle.TLabel", background=palette["card"], foreground=palette["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("PreviewTitle.TLabel", background=palette["card"], foreground=palette["text"], font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("PreviewSubtle.TLabel", background=palette["card"], foreground=palette["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Chip.TLabel", background=palette["card_soft"], foreground=palette["muted"], font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.configure("AccentChip.TLabel", background=palette["panel"], foreground=palette["accent"], font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 6))
        style.configure(
            "TButton",
            padding=(16, 10),
            background=palette["card_soft"],
            foreground=palette["text"],
            borderwidth=0,
            focusthickness=0,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.map(
            "TButton",
            background=[("pressed", "#e4eefc"), ("active", "#edf4ff")],
            foreground=[("disabled", palette["muted"])],
        )
        style.configure(
            "Accent.TButton",
            padding=(18, 10),
            background=palette["accent"],
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", palette["accent_pressed"]), ("active", palette["accent_hover"])],
            foreground=[("disabled", "#dce9ff")],
        )
        style.configure("Toolbar.TButton", padding=(14, 8), background=palette["card_soft"], foreground=palette["text"], borderwidth=0, focusthickness=0, font=("Microsoft YaHei UI", 9, "bold"))
        style.map(
            "Toolbar.TButton",
            background=[("pressed", "#e4eefc"), ("active", "#edf4ff")],
            foreground=[("disabled", palette["muted"])],
        )
        style.configure("ToolbarAccent.TButton", padding=(14, 8), background=palette["accent"], foreground="#ffffff", borderwidth=0, focusthickness=0, font=("Microsoft YaHei UI", 9, "bold"))
        style.map(
            "ToolbarAccent.TButton",
            background=[("pressed", palette["accent_pressed"]), ("active", palette["accent_hover"])],
            foreground=[("disabled", "#dce9ff")],
        )
        style.configure(
            "TEntry",
            fieldbackground=palette["card_soft"],
            foreground=palette["text"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            padding=8,
            borderwidth=0,
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
            lightcolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
            darkcolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=palette["card_soft"],
            background=palette["card_soft"],
            foreground=palette["text"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            arrowcolor=palette["accent"],
            padding=7,
            borderwidth=0,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette["card_soft"])],
            selectbackground=[("readonly", palette["accent"])],
            selectforeground=[("readonly", "#ffffff")],
            bordercolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
            lightcolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
            darkcolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=palette["card_soft"],
            foreground=palette["text"],
            arrowsize=14,
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            padding=6,
            borderwidth=0,
        )
        style.map(
            "TSpinbox",
            bordercolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
            lightcolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
            darkcolor=[("focus", palette["accent"]), ("!focus", palette["border"])],
        )
        style.configure("TCheckbutton", background=palette["card"], foreground=palette["text"])
        style.map("TCheckbutton", foreground=[("disabled", palette["muted"])])
        style.configure("Horizontal.TScale", background=palette["card"], troughcolor=palette["panel"])
        style.configure(
            "Horizontal.TProgressbar",
            background=palette["accent"],
            troughcolor=palette["panel"],
            bordercolor=palette["panel"],
            lightcolor=palette["accent"],
            darkcolor=palette["accent"],
            thickness=10,
        )
        style.configure("TLabelframe", background=palette["card"], bordercolor=palette["border"], relief="solid", borderwidth=0)
        style.configure("TLabelframe.Label", background=palette["card"], foreground=palette["text"], font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TNotebook", background=palette["card"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background=palette["panel"],
            foreground=palette["muted"],
            padding=(20, 11),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", palette["card_soft"]), ("active", "#eef4ff")],
            foreground=[("selected", palette["accent"]), ("active", palette["text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=palette["panel"],
            troughcolor=palette["card_soft"],
            bordercolor=palette["card_soft"],
            arrowcolor=palette["muted"],
            darkcolor=palette["panel"],
            lightcolor=palette["panel"],
        )
        style.configure("TPanedwindow", background=palette["bg"], sashwidth=8)

        self.main_paned.configure(style="TPanedwindow")

        self.preview_canvas.configure(
            bg=palette["preview"],
            highlightbackground=palette["panel"],
            highlightcolor=palette["accent"],
            highlightthickness=0,
        )
        self.preview_canvas.itemconfig(self.canvas_text, fill=palette["preview_text"])
        self.wm_color_preview.configure(highlightthickness=1, highlightbackground=palette["border"], bd=0)
        self.region_listbox.configure(
            bg=palette["card_soft"],
            fg=palette["text"],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground=palette["border"],
            selectbackground=palette["accent"],
            selectforeground="#ffffff",
            selectborderwidth=0,
        )
        self.log_text.configure(
            bg=palette["card_soft"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground=palette["border"],
            selectbackground=palette["accent"],
            selectforeground="#ffffff",
        )
        self.pixiv_caption.configure(
            bg=palette["card_soft"],
            fg=palette["text"],
            insertbackground=palette["text"],
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=palette["border"],
            selectbackground=palette["accent"],
            selectforeground="#ffffff",
        )
        self.start_btn.configure(style="Accent.TButton")

    # ===== 浜嬩欢澶勭悊 =====

    def update_preview_workspace(self, status=None):
        """鏇存柊鍙充晶棰勮宸ヤ綔鍙伴《閮ㄧ姸鎬併€?"""
        if self.current_image:
            width, height = self.current_image.size
            self.preview_size_var.set(f"尺寸: {width} x {height}")
        else:
            self.preview_size_var.set("尺寸: -")

        if getattr(self, "preview_image", None) is not None and getattr(self, "preview_scale", None):
            self.preview_zoom_var.set(f"缩放: {int(self.preview_scale * 100)}%")
        else:
            self.preview_zoom_var.set("缩放: -")

        self.preview_region_var.set(f"选区: {len(self.mosaic_regions)}")

        if status is not None:
            self.preview_status_var.set(f"状态: {status}")
        elif self.current_image:
            self.preview_status_var.set("状态: 可编辑")
        else:
            self.preview_status_var.set("状态: 等待载入")

    def redraw_preview_regions(self):
        """鍦ㄩ瑙堝伐浣滃彴涓噸缁樺凡閫夌殑鍖哄煙銆?"""
        self.preview_canvas.delete("saved-selection")
        if not getattr(self, "preview_image", None):
            return

        scale = getattr(self, "preview_scale", None)
        offset = getattr(self, "preview_offset", None)
        if not scale or offset is None:
            return

        offset_x, offset_y = offset
        for index, region in enumerate(self.mosaic_regions, start=1):
            x1, y1, x2, y2 = region
            px1 = offset_x + int(x1 * scale)
            py1 = offset_y + int(y1 * scale)
            px2 = offset_x + int(x2 * scale)
            py2 = offset_y + int(y2 * scale)
            self.preview_canvas.create_rectangle(
                px1,
                py1,
                px2,
                py2,
                outline="#60a5fa",
                width=2,
                dash=(6, 4),
                tags="saved-selection",
            )
            self.preview_canvas.create_text(
                px1 + 10,
                py1 + 10,
                text=str(index),
                anchor=tk.NW,
                fill="#dbeafe",
                font=("Microsoft YaHei UI", 9, "bold"),
                tags="saved-selection",
            )

    def reset_preview(self):
        """鎭㈠鍒板師濮嬮瑙堛€?"""
        if not self.current_image:
            messagebox.showwarning("提示", "请先加载图片")
            return
        self.show_preview(self.current_image.copy(), status="已重置")

    def choose_color(self):
        """閫夋嫨棰滆壊"""
        color = colorchooser.askcolor(color=self._rgb_to_hex(self.wm_color))[0]
        if color:
            self.wm_color = [int(c) for c in color]
            self.wm_color_preview.config(bg=self._rgb_to_hex(self.wm_color))

    def _rgb_to_hex(self, rgb):
        """RGB 杞?HEX"""
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def on_mosaic_mode_change(self, event=None):
        """鎵撶爜妯″紡鍒囨崲"""
        mode = self.mosaic_mode.get()
        if mode == "pixelate":
            self.pixel_size_label.config(state=tk.NORMAL)
            self.mosaic_pixel_size.config(state=tk.NORMAL)
            self.blur_radius_label.config(state=tk.DISABLED)
            self.mosaic_blur_radius.config(state=tk.DISABLED)
        else:
            self.pixel_size_label.config(state=tk.DISABLED)
            self.mosaic_pixel_size.config(state=tk.DISABLED)
            self.blur_radius_label.config(state=tk.NORMAL)
            self.mosaic_blur_radius.config(state=tk.NORMAL)

    def browse_dir(self, entry):
        """娴忚鐩綍"""
        path = filedialog.askdirectory()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def browse_upscale_model(self):
        """选择 Real-ESRGAN 本地权重文件。"""
        path = filedialog.askopenfilename(
            filetypes=[("PyTorch weights", "*.pth"), ("All files", "*.*")]
        )
        if path:
            self.upscale_custom_model.delete(0, tk.END)
            self.upscale_custom_model.insert(0, path)

    def get_selected_upscale_model(self):
        """优先返回自定义权重路径，否则返回当前下拉模型。"""
        try:
            engine = normalize_upscale_engine(self.upscale_engine.get())
        except Exception:
            engine = "realesrgan"

        if engine == "realesrgan":
            custom_path = self.upscale_custom_model.get().strip()
            if custom_path:
                return custom_path

        return (self.upscale_model.get() or "").strip() or None

    def test_upscale(self):
        """娴嬭瘯瓒呭垎鍔熻兘"""
        try:
            engine = normalize_upscale_engine(self.upscale_engine.get())
            model_name = self.get_selected_upscale_model()
            scale = int(self.upscale_scale.get())
            noise = int(self.upscale_noise.get()) if self.upscale_engine.get() == "realcugan" else -1

            processor = UpscaleProcessor(
                engine=engine,
                model_name=model_name,
                realcugan_noise=noise,
            )

            # Real-ESRGAN prepares/downloads weights directly; other engines only verify runtime dependencies.
            ready = processor.prepare()
            if ready:
                messagebox.showinfo(
                    "成功",
                    f"{UPSCALE_ENGINES[engine]} 已就绪\n模型: {processor.model_name}\n倍率: {scale}x",
                )
            else:
                messagebox.showwarning("提示", "超分后端初始化未完成，请查看日志")
        except Exception as e:
            messagebox.showerror("错误", f"初始化失败: {e}")

    # ===== 鍥剧墖棰勮 =====

    def load_preview(self):
        """鍔犺浇棰勮鍥剧墖"""
        path = filedialog.askopenfilename(
            filetypes=[("鍥剧墖", "*.jpg *.jpeg *.png *.webp *.bmp")]
        )
        if not path:
            return

        self.current_image = Image.open(path)
        self.preview_file_var.set(Path(path).name)
        self.show_preview(self.current_image.copy(), status="已载入")
        self.log(f"已加载图片: {path} ({self.current_image.size[0]}x{self.current_image.size[1]})")

    def show_preview(self, img, status=None):
        """鏄剧ず棰勮"""
        self.preview_image = img

        # 閫傚簲 Canvas 澶у皬
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()

        if canvas_w < 100:
            canvas_w = 600
        if canvas_h < 100:
            canvas_h = 500

        img_w, img_h = img.size
        scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)

        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        resized = img.resize((new_w, new_h), Image.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(resized)

        # clear and redraw preview canvas
        self.preview_canvas.delete("all")
        offset_x = (canvas_w - new_w) // 2
        offset_y = (canvas_h - new_h) // 2

        self.preview_canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self.preview_photo, tags="image")
        self.preview_canvas.config(scrollregion=(0, 0, canvas_w, canvas_h))

        # 淇濆瓨缂╂斁姣斾緥鐢ㄤ簬鍧愭爣杞崲
        self.preview_scale = scale
        self.preview_offset = (offset_x, offset_y)
        self.original_size = (img_w, img_h)
        self.redraw_preview_regions()
        self.update_preview_workspace(status=status)

    def preview_watermark(self):
        """棰勮姘村嵃鏁堟灉"""
        if not self.current_image:
            messagebox.showwarning("提示", "请先加载图片")
            return

        # build temporary preview config
        config = {
            "text": self.wm_text.get() or "Preview",
            "font_size": int(self.wm_font_size.get()),
            "color": self.wm_color,
            "opacity": self.wm_opacity.get(),
            "position": self.wm_position.get(),
            "rotation_range": [int(self.wm_rot_min.get()), int(self.wm_rot_max.get())],
            "offset_range": [-15, 15] if self.wm_random_offset.get() else [0, 0],
        }

        processor = WatermarkProcessor(config)

        # 鍒涘缓涓存椂鏂囦欢
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            temp_path = f.name

        try:
            processor.process(Path(temp_path.replace('.jpg', '_dummy')), Path(temp_path), **config)
            # Preview directly in memory instead of writing an intermediate file.

            img = self.current_image.copy()
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 杩欓噷鐩存帴缁樺埗棰勮
            preview = self._apply_watermark_preview(img, config)
            self.show_preview(preview, status="水印预览")

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _apply_watermark_preview(self, img, config):
        """鐩存帴搴旂敤姘村嵃鍒板浘鐗囷紙鐢ㄤ簬棰勮锛?"""
        # Draw the watermark directly onto the preview image.
        from main import get_font_path, create_dragon_icon

        font_path = get_font_path()
        draw = ImageDraw.Draw(img)

        img_w, img_h = img.size
        font_size = int(config.get("font_size", 48))

        try:
            font = ImageFont.truetype(str(font_path), font_size) if font_path else ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        text = config["text"]
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # 璁＄畻浣嶇疆
        margin = 30
        pos = config.get("position", "bottom-right")

        if pos == "center":
            x, y = (img_w - text_w) // 2, (img_h - text_h) // 2
        elif pos == "top-left":
            x, y = margin, margin
        elif pos == "top-right":
            x, y = img_w - text_w - margin, margin
        elif pos == "bottom-left":
            x, y = margin, img_h - text_h - margin
        else:
            x, y = img_w - text_w - margin, img_h - text_h - margin

        # 搴旂敤鍋忕Щ
        offset = config.get("offset_range", [0, 0])
        if offset != [0, 0]:
            x += random.randint(offset[0], offset[1])
            y += random.randint(offset[0], offset[1])

        # 缁樺埗鏂囧瓧
        color = tuple(config["color"]) + (int(255 * config["opacity"]),)

        # 浣跨敤绠€鍗曟柟寮忕粯鍒讹紙棰勮鐢級
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.text((x, y), text, font=font, fill=color)

        # 鏃嬭浆
        rotation = config.get("rotation_range", [0, 0])
        if rotation != [0, 0]:
            angle = random.uniform(rotation[0], rotation[1])
            overlay = overlay.rotate(angle, expand=False, resample=Image.BICUBIC)

        result = Image.alpha_composite(img, overlay)
        if result.mode == 'RGBA':
            bg = Image.new('RGB', result.size, (255, 255, 255))
            bg.paste(result, mask=result.split()[3])
            result = bg

        return result

    def preview_mosaic(self):
        """棰勮鎵撶爜鏁堟灉"""
        if not self.current_image:
            messagebox.showwarning("提示", "请先加载图片")
            return

        if not self.mosaic_regions:
            messagebox.showwarning("提示", "请先选择打码区域")
            return

        img = self.current_image.copy()
        if img.mode != 'RGB':
            img = img.convert('RGB')

        processor = MosaicProcessor()
        mode = self.mosaic_mode.get()

        kwargs = {}
        if mode == "pixelate":
            kwargs['pixel_size'] = int(self.mosaic_pixel_size.get())
        else:
            kwargs['radius'] = int(self.mosaic_blur_radius.get())

        for region in self.mosaic_regions:
            if mode == "pixelate":
                img = processor.pixelate(img, region, kwargs.get('pixel_size', 10))
            else:
                img = processor.gaussian_blur(img, region, kwargs.get('radius', 15))

        self.show_preview(img, status="打码预览")

    # ===== 鍖哄煙閫夋嫨 =====

    def on_canvas_click(self, event):
        """榧犳爣鐐瑰嚮"""
        if not self.preview_image:
            return
        self.selection_start = (event.x, event.y)

    def on_canvas_drag(self, event):
        """榧犳爣鎷栨嫿"""
        if not self.selection_start:
            return

        if self.selection_rect:
            self.preview_canvas.delete(self.selection_rect)

        self.selection_rect = self.preview_canvas.create_rectangle(
            self.selection_start[0], self.selection_start[1],
            event.x, event.y,
            outline="red", width=2, tags="selection"
        )

    def on_canvas_release(self, event):
        """榧犳爣閲婃斁"""
        if not self.selection_start:
            return

        x1, y1 = self.selection_start
        x2, y2 = event.x, event.y

        # convert back to original image coordinates
        scale = getattr(self, 'preview_scale', 1.0)
        offset_x, offset_y = getattr(self, 'preview_offset', (0, 0))

        # 鐩稿浜庡浘鐗囩殑浣嶇疆
        img_x1 = int((min(x1, x2) - offset_x) / scale)
        img_y1 = int((min(y1, y2) - offset_y) / scale)
        img_x2 = int((max(x1, x2) - offset_x) / scale)
        img_y2 = int((max(y1, y2) - offset_y) / scale)

        # clamp to image bounds
        orig_w, orig_h = getattr(self, 'original_size', (0, 0))
        img_x1 = max(0, min(img_x1, orig_w))
        img_y1 = max(0, min(img_y1, orig_h))
        img_x2 = max(0, min(img_x2, orig_w))
        img_y2 = max(0, min(img_y2, orig_h))

        if img_x2 > img_x1 and img_y2 > img_y1:
            region = (img_x1, img_y1, img_x2, img_y2)
            self.mosaic_regions.append(region)
            self.region_listbox.insert(tk.END, f"{region}")
            self.log(f"添加打码区域: {region}")
            self.redraw_preview_regions()
            self.update_preview_workspace(status="选区已更新")

        self.selection_start = None
        if self.selection_rect:
            self.preview_canvas.delete(self.selection_rect)
            self.selection_rect = None

    def delete_region(self):
        """鍒犻櫎閫変腑鍖哄煙"""
        selection = self.region_listbox.curselection()
        if selection:
            idx = selection[0]
            self.region_listbox.delete(idx)
            if idx < len(self.mosaic_regions):
                del self.mosaic_regions[idx]
            self.redraw_preview_regions()
            self.update_preview_workspace(status="选区已更新")

    def clear_regions(self):
        """娓呯┖鎵€鏈夊尯鍩?"""
        self.region_listbox.delete(0, tk.END)
        self.mosaic_regions.clear()
        self.redraw_preview_regions()
        self.update_preview_workspace(status="选区已清空")

    # ===== 鎵归噺澶勭悊 =====

    def log(self, message):
        """娣诲姞鏃ュ織"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def get_pixiv_settings(self):
        """鏋勫缓 Pixiv 涓婁紶閰嶇疆銆?"""
        return {
            "enabled": self.do_pixiv_upload.get(),
            "browser_channel": self.pixiv_browser.get() or "msedge",
            "profile_dir": self.pixiv_profile_dir.get().strip(),
            "title_template": self.pixiv_title_template.get().strip() or "{stem}",
            "caption": self.pixiv_caption.get("1.0", tk.END).strip(),
            "tags": self.pixiv_tags.get().strip(),
            "use_metadata_tags": self.pixiv_use_metadata_tags.get(),
            "include_lora_tags": self.pixiv_include_lora_tags.get(),
            "add_original_tag": self.pixiv_add_original_tag.get(),
            "ai_generated": self.pixiv_ai_generated.get(),
            "add_upscale_tag": self.pixiv_add_upscale_tag.get(),
            "add_engine_tag": self.pixiv_add_engine_tag.get(),
            "add_model_tag": self.pixiv_add_model_tag.get(),
            "add_scale_tag": self.pixiv_add_scale_tag.get(),
            "visibility": self.pixiv_visibility.get() or "public",
            "age_restriction": self.pixiv_age.get() or "all",
            "auto_submit": self.pixiv_auto_submit.get(),
        }

    def build_pixiv_title(self, image_path: Path) -> str:
        """鏍规嵁妯℃澘鐢熸垚 Pixiv 鏍囬銆?"""
        template = self.pixiv_title_template.get().strip() or "{stem}"
        try:
            return template.format(stem=image_path.stem, name=image_path.name)
        except Exception:
            return image_path.stem

    def extract_metadata_tags(self, image_path: Path):
        """浠庢簮鍥?metadata 涓彁鍙?prompt 鏍囩銆?"""
        quality_blacklist = {
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

        try:
            with Image.open(image_path) as img:
                parameters = img.info.get("parameters", "")
        except Exception:
            return [], []

        if not isinstance(parameters, str) or not parameters.strip():
            return [], []

        def split_prompt_chunks(text):
            chunks = []
            current = []
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

        def expand_prompt_chunks(text):
            expanded = []
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

        prompt_tags = []
        for raw_tag in prompt_chunks:
            tag = raw_tag.strip()
            if not tag:
                continue

            tag = re.sub(r":-?\d+(?:\.\d+)?$", "", tag).strip()
            if not tag:
                continue

            normalized = tag.lower()
            if normalized in quality_blacklist:
                continue
            prompt_tags.append(tag)

        return prompt_tags, lora_tags

    def build_pixiv_tags(self, image_path: Path = None):
        """鐢熸垚 Pixiv 鏍囩鍒楄〃銆?"""
        raw = self.pixiv_tags.get().replace("\n", ",")
        tags = []
        for item in raw.split(","):
            tag = item.strip()
            if tag:
                tags.append(tag)

        if image_path is not None and self.pixiv_use_metadata_tags.get():
            prompt_tags, lora_tags = self.extract_metadata_tags(Path(image_path))
            tags.extend(prompt_tags)
            if self.pixiv_include_lora_tags.get():
                tags.extend(lora_tags)

        if self.pixiv_add_original_tag.get():
            tags.extend(["原创", "オリジナル"])
        if self.pixiv_ai_generated.get():
            tags.extend(["AI鐢熸垚", "AI銈ゃ儵銈广儓"])

        if self.do_upscale.get():
            engine = normalize_upscale_engine(self.upscale_engine.get())
            model_name = self.get_selected_upscale_model() or ""
            scale = int(self.upscale_scale.get())

            if self.pixiv_add_upscale_tag.get():
                tags.extend(["超分", "超解像", "高解像度化"])

            if self.pixiv_add_engine_tag.get():
                engine_labels = {
                    "realesrgan": ["Real-ESRGAN"],
                    "realcugan": ["Real-CUGAN"],
                    "apisr": ["APISR"],
                }
                tags.extend(engine_labels.get(engine, [UPSCALE_ENGINES.get(engine, engine)]))

            if self.pixiv_add_model_tag.get() and model_name:
                tags.append(Path(model_name).stem)

            if self.pixiv_add_scale_tag.get():
                tags.extend([f"{scale}x", f"{scale}x鏀惧ぇ"])

        unique_tags = []
        seen = set()
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        return unique_tags

    def start_batch(self):
        """寮€濮嬫壒閲忓鐞?"""
        input_dir = self.batch_input.get()
        output_dir = self.batch_output.get()

        if not input_dir or not output_dir:
            messagebox.showerror("错误", "请指定输入和输出目录")
            return

        if not os.path.exists(input_dir):
            messagebox.showerror("错误", "输入目录不存在")
            return

        # 淇濆瓨閰嶇疆
        self.config["last_input_dir"] = input_dir
        self.config["last_output_dir"] = output_dir
        self.config["watermark"]["text"] = self.wm_text.get()
        self.config["watermark"]["font_size"] = int(self.wm_font_size.get())
        self.config["watermark"]["color"] = self.wm_color
        self.config["watermark"]["opacity"] = self.wm_opacity.get()
        self.config["watermark"]["position"] = self.wm_position.get()
        self.config["watermark"]["rotation_min"] = int(self.wm_rot_min.get())
        self.config["watermark"]["rotation_max"] = int(self.wm_rot_max.get())
        self.config["watermark"]["random_offset"] = self.wm_random_offset.get()
        self.config["mosaic"]["mode"] = self.mosaic_mode.get()
        self.config["mosaic"]["pixel_size"] = int(self.mosaic_pixel_size.get())
        self.config["mosaic"]["blur_radius"] = int(self.mosaic_blur_radius.get())
        self.config["upscale"]["engine"] = normalize_upscale_engine(self.upscale_engine.get())
        self.config["upscale"]["model"] = self.upscale_model.get()
        self.config["upscale"]["custom_model_path"] = self.upscale_custom_model.get().strip()
        self.config["upscale"]["scale"] = int(self.upscale_scale.get())
        self.config["upscale"]["noise"] = int(self.upscale_noise.get()) if self.upscale_engine.get() == "realcugan" else -1
        self.config["pixiv"] = self.get_pixiv_settings()
        self.save_config()

        # run processing in a worker thread
        self.start_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0

        thread = threading.Thread(target=self._process_batch)
        thread.daemon = True
        thread.start()

    def _process_batch(self):
        """鎵归噺澶勭悊绾跨▼"""
        try:
            input_dir = Path(self.batch_input.get())
            output_dir = Path(self.batch_output.get())

            # 鏋勫缓閰嶇疆
            watermark_config = None
            if self.do_watermark.get():
                watermark_config = {
                    "text": self.wm_text.get() or "YourName",
                    "font_size": int(self.wm_font_size.get()),
                    "color": self.wm_color,
                    "opacity": self.wm_opacity.get(),
                    "position": self.wm_position.get(),
                    "rotation_range": [int(self.wm_rot_min.get()), int(self.wm_rot_max.get())],
                    "offset_range": [-15, 15] if self.wm_random_offset.get() else [0, 0],
                }

            mosaic_regions = None
            if self.do_mosaic.get() and self.mosaic_regions:
                mosaic_regions = self.mosaic_regions.copy()

            upscale_processor = None
            if self.do_upscale.get():
                engine = normalize_upscale_engine(self.upscale_engine.get())
                model_name = self.get_selected_upscale_model()
                noise = int(self.upscale_noise.get()) if engine == "realcugan" else -1
                upscale_processor = UpscaleProcessor(
                    engine=engine,
                    model_name=model_name,
                    realcugan_noise=noise,
                )
                self.root.after(
                    0,
                    lambda e=engine, m=upscale_processor.model_name: self.log(
                        f"瓒呭垎鍚庣: {UPSCALE_ENGINES.get(e, e)} / 妯″瀷: {m}"
                    ),
                )

            pixiv_settings = self.get_pixiv_settings()
            pixiv_uploader = None
            if pixiv_settings["enabled"]:
                pixiv_uploader = PixivUploader(
                    pixiv_settings,
                    log_fn=lambda message: self.root.after(0, lambda m=message: self.log(m)),
                )
                self.root.after(0, lambda: self.log("[Pixiv] 自动上传已启用"))

            # 瑙ｆ瀽澶勭悊椤哄簭
            order_str = self.process_order.get()
            order_map = {
                "upscale -> mosaic -> watermark": ["upscale", "mosaic", "watermark"],
                "mosaic -> upscale -> watermark": ["mosaic", "upscale", "watermark"],
                "watermark -> mosaic": ["watermark", "mosaic"],
            }
            order = order_map.get(order_str, ["upscale", "mosaic", "watermark"])

            # 杩囨护鏈惎鐢ㄧ殑姝ラ
            if not self.do_upscale.get():
                order = [s for s in order if s != "upscale"]
            if not self.do_mosaic.get():
                order = [s for s in order if s != "mosaic"]
            if not self.do_watermark.get():
                order = [s for s in order if s != "watermark"]

            if not order:
                self.root.after(0, lambda: messagebox.showwarning("提示", "请至少选择一个处理步骤"))
                return

            self.root.after(0, lambda: self.log(f"开始处理，顺序: {' -> '.join(order)}"))

            # 鑾峰彇鍥剧墖鍒楄〃
            image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
            images = [f for f in input_dir.iterdir()
                     if f.is_file() and f.suffix.lower() in image_extensions]

            total = len(images)
            self.root.after(0, lambda: self.progress.config(maximum=total))

            if pixiv_uploader is not None and not pixiv_settings["auto_submit"] and total > 1:
                self.root.after(
                    0,
                    lambda: self.log("[Pixiv] 当前为手动投稿模式，建议先确认首张流程是否符合预期。"),
                )

            for i, img_path in enumerate(images, 1):
                self.root.after(0, lambda p=img_path, idx=i: self.log(f"[{idx}/{total}] 处理: {p.name}"))

                try:
                    final_path = self._process_single_image(
                        img_path,
                        output_dir,
                        watermark_config,
                        mosaic_regions,
                        self.mosaic_mode.get(),
                        order,
                        upscale_processor,
                    )

                    if pixiv_uploader is not None and final_path is not None:
                        pixiv_uploader.upload_image(
                            final_path,
                            title=self.build_pixiv_title(final_path),
                            caption=pixiv_settings["caption"],
                            tags=self.build_pixiv_tags(img_path),
                            visibility=pixiv_settings["visibility"],
                            age_restriction=pixiv_settings["age_restriction"],
                            ai_generated=pixiv_settings["ai_generated"],
                            auto_submit=pixiv_settings["auto_submit"],
                        )
                except Exception as e:
                    self.root.after(0, lambda e=e: self.log(f"错误: {e}"))

                self.root.after(0, lambda v=i: self.progress.config(value=v))

            self.root.after(0, lambda: self.log("处理完成"))
            self.root.after(0, lambda: messagebox.showinfo("完成", "批量处理已完成！"))

        finally:
            try:
                if 'pixiv_uploader' in locals() and pixiv_uploader is not None and pixiv_settings.get("auto_submit", True):
                    pixiv_uploader.close()
            except Exception:
                pass
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

    def _process_single_image(self, input_path, output_dir, watermark_config,
                              mosaic_regions, mosaic_mode, order, upscale_processor=None):
        """澶勭悊鍗曞紶鍥剧墖"""
        current_path = input_path
        temp_files = []

        try:
            for step in order:
                if step == "upscale":
                    if upscale_processor is None:
                        continue

                    output_path = output_dir / f"{input_path.stem}_upscaled.png"
                    result = upscale_processor.process(
                        current_path,
                        output_path,
                        scale=int(self.upscale_scale.get()),
                    )
                    if not result:
                        raise RuntimeError("瓒呭垎澶勭悊澶辫触")

                    if current_path != input_path:
                        temp_files.append(current_path)
                    current_path = Path(result)

                elif step == "mosaic":
                    output_path = output_dir / f"{input_path.stem}_mosaic.jpg"
                    processor = MosaicProcessor()

                    kwargs = {}
                    if mosaic_mode == "pixelate":
                        kwargs['pixel_size'] = int(self.mosaic_pixel_size.get())
                    else:
                        kwargs['radius'] = int(self.mosaic_blur_radius.get())

                    processor.process(current_path, output_path,
                                    regions=mosaic_regions or [],
                                    mode=mosaic_mode, **kwargs)

                    if current_path != input_path:
                        temp_files.append(current_path)
                    current_path = output_path

                elif step == "watermark":
                    output_path = output_dir / f"{input_path.stem}_watermarked.jpg"
                    processor = WatermarkProcessor(watermark_config)
                    processor.process(current_path, output_path)

                    if current_path != input_path:
                        temp_files.append(current_path)
                    current_path = output_path

            # 閲嶅懡鍚嶄负鏈€缁堟枃浠跺悕
            final_path = output_dir / input_path.name
            if current_path != final_path:
                if final_path.exists():
                    final_path.unlink()
                os.replace(current_path, final_path)

            return final_path

        finally:
            # 娓呯悊涓存椂鏂囦欢
            for temp in temp_files:
                try:
                    if temp.exists() and temp != input_path:
                        temp.unlink()
                except Exception:
                    pass


def main():
    root = tk.Tk()
    app = ImageProcessorGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()




