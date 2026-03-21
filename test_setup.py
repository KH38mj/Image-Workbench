#!/usr/bin/env python3
"""
Lightweight environment self-check for the image processor project.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _print_header(title: str) -> None:
    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)


def test_imports() -> bool:
    _print_header("Core Dependencies")

    required = [
        ("PIL (Pillow)", "PIL"),
        ("requests", "requests"),
        ("numpy", "numpy"),
        ("tkinter", "tkinter"),
    ]
    optional = [
        ("torch", "torch"),
        ("realesrgan", "realesrgan"),
        ("basicsr", "basicsr"),
        ("Final2x_core", "Final2x_core"),
        ("playwright", "playwright"),
        ("pywebview", "webview"),
    ]

    all_required_present = True
    for label, module_name in required:
        if _has_module(module_name):
            print(f"[OK]   {label:20} - installed")
        else:
            print(f"[FAIL] {label:20} - missing")
            all_required_present = False

    _print_header("Optional Dependencies")
    for label, module_name in optional:
        if _has_module(module_name):
            print(f"[OK]   {label:20} - installed")
        else:
            print(f"[WARN] {label:20} - missing (feature will install or stay unavailable)")

    return all_required_present


def test_directories() -> None:
    _print_header("Project Directories")

    for name in ("fonts", "assets", "models"):
        path = PROJECT_ROOT / name
        path.mkdir(exist_ok=True)
        print(f"[OK]   {name:20} - {path}")


def test_fonts() -> None:
    _print_header("Watermark Font")

    try:
        from main import get_font_path

        font_path = get_font_path()
        if font_path:
            print(f"[OK]   default font ready - {font_path}")
        else:
            print("[WARN] default font path is empty")
    except Exception as exc:
        print(f"[FAIL] watermark font check failed - {exc}")


if __name__ == "__main__":
    print("\nImage Processor - Environment Self Check")

    success = test_imports()
    test_directories()
    test_fonts()

    _print_header("Summary")
    if success:
        print("[OK]   core environment looks ready")
        print("[OK]   you can try running gui.py, webview_app.py, or main.py")
    else:
        print("[FAIL] core dependencies are missing")
        print("[INFO] install the missing packages from requirements.txt first")
        sys.exit(1)
