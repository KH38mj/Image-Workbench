# 图片处理工具

AI 生成图片后处理工具，支持水印添加（去 Metadata）、敏感部位打码、支持 Real-ESRGAN / Real-CUGAN / APISR 的本地图片超分。

## 功能

### 1. 水印功能
- 自动下载 Dancing Script 手写风格字体
- 龙图标（🐉）自动获取
- 随机位置偏移（防批量去除）
- 随机角度旋转
- 透明度、颜色可调
- **自动清除所有 Metadata**（包括 AI 工作流信息）

### 2. 打码功能
- 像素马赛克
- 高斯模糊
- 可视化区域选择
- 支持多个区域

### 3. 超分功能
- 支持三种后端：Real-ESRGAN、Real-CUGAN、APISR
- Real-ESRGAN：支持通用/二次元模型，自动下载模型
- Real-CUGAN：支持 2x/3x/4x，可选降噪等级（-1/0/1/2/3）
- APISR：支持 APISR-RRDB 2x/4x 放大

## 安装使用

### 方式一：图形界面（推荐）

双击运行：
```
start.bat
```

或在命令行中：
```bash
pip install -r requirements.txt
python gui.py
```

### 方式二：命令行

```bash
# 安装依赖
pip install -r requirements.txt

# 水印
python main.py watermark -i input.jpg -o output.jpg -t "YourName"

# 打码
python main.py mosaic -i input.jpg -o output.jpg -r "100,100,200,200" -m pixelate

# 超分（Real-ESRGAN）
python main.py upscale -i input.jpg -o output.png -e realesrgan -s 4 -m RealESRGAN_x4plus_anime_6B.pth

# 超分（Real-CUGAN）
python main.py upscale -i input.jpg -o output.png -e realcugan -s 4 -m RealCUGAN-se --noise -1

# 超分（APISR）
python main.py upscale -i input.jpg -o output.png -e apisr -s 4 -m APISR-RRDB

# 批量流水线（可选引擎/模型）
python main.py pipeline -i ./input -o ./output --watermark --mosaic --upscale --upscale-engine realcugan --upscale-model RealCUGAN-se --upscale-scale 4 --upscale-noise -1
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 命令行主程序 |
| `gui.py` | 图形界面程序 |
| `start.bat` | Windows 一键启动 |
| `requirements.txt` | 依赖列表 |
| `fonts/` | 自动下载的字体 |
| `assets/` | 龙图标 |
| `gui_config.json` | 界面配置保存 |

## 注意事项

1. **超分配置**：在超分设置标签页中选择引擎（Real-ESRGAN/Real-CUGAN/APISR）、模型和倍率
2. **字体下载**：首次使用水印时会自动从 Google Fonts 下载 Dancing Script
3. **龙图标**：自动从 Twemoji 下载，如果失败会使用 emoji 后备
4. **处理顺序建议**：超分 → 打码 → 水印（默认）


## Real-ESRGAN Local Weights

If automatic download fails, you can now provide a local `.pth` file in either of these ways:

```bash
python main.py upscale -i input.jpg -o output.png -e realesrgan -m D:\\models\\RealESRGAN_x4plus_anime_6B.pth
```

Or place the file in one of the auto-detected folders:
- `./models`
- `ComfyUI/models/upscale_models`
- `ComfyUI/models/ESRGAN`

The loader now prefers an existing local file before trying to download from GitHub.

## PyWebView Frontend Preview

The project now includes a new `pywebview`-based frontend prototype:

- Entry point: `webview_app.py`
- Assets: `webui/`
- Visible launcher: `start_webview.bat`
- Hidden-console launcher: `open_webview.vbs`

Install the extra dependency first if needed:

```bash
pip install pywebview
```

Then launch with:

```bash
python webview_app.py
```

Or double-click `open_webview.vbs` on Windows.
