# Image Workbench

一个偏本地工作流的 AI 图片后处理工具，支持水印、打码、超分、批处理，以及 Pixiv 投稿辅助。

当前项目以 Windows 桌面使用为主，推荐优先使用 `pywebview` 新前端。

## 主要功能

- 水印
  - 自定义文字
  - 自定义字体文件 `TTF / OTF / TTC`
  - 内置常用字体选项
  - 自动清理图片中的 metadata
- 打码
  - 像素化
  - 高斯模糊
  - 多区域框选
- 超分
  - `Real-ESRGAN`
  - `Real-CUGAN`
  - `APISR`
  - 支持批处理工作流
- 桌面前端
  - `pywebview` 工作台
  - 单图预览与选区编辑
  - 批量处理
  - 一键停止当前批处理任务
- Pixiv 投稿辅助
  - 浏览器自动投稿
  - `Cookie + CSRF` 直传模式
  - 从 metadata 提取标签
  - 可选 OpenAI-compatible LLM 标签润色
  - NSFW / R-18 / R-18G 基础安全护栏
- 测试与回归
  - 已补关键回归测试
  - 覆盖批处理输出格式和敏感配置持久化问题

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `main.py` | CLI 主入口，包含水印、打码、超分、批处理 |
| `webview_app.py` | `pywebview` 桌面前端后端桥接 |
| `webui/` | `pywebview` 前端页面资源 |
| `pixiv_uploader.py` | Pixiv 上传逻辑 |
| `pixiv_llm.py` | OpenAI-compatible 标签整理器 |
| `tests/` | 自动化回归测试 |
| `start_webview.bat` | 可见终端启动器 |
| `open_webview.vbs` | 隐藏终端启动器 |
| `PROGRESS.md` | 开发过程记录 |

## 环境要求

- Windows
- 建议 Python `3.12`
- 推荐使用独立虚拟环境
- 如果要启用 GPU 超分，`torch` / CUDA 版本需要与显卡匹配

安装依赖：

```powershell
pip install -r requirements.txt
```

## 快速开始

### 0. clone 后最快跑起来

如果你是第一次把仓库拉到本地，推荐直接走这套：

```powershell
git clone https://github.com/KH38mj/picture.git
cd picture
py -3.12 -m venv .venv312
.venv312\Scripts\python.exe -m pip install -U pip
.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

装好以后，优先这样启动：

```powershell
start_webview.bat
```

说明：

- `requirements.txt` 已经包含 `pywebview`
- 上面的仓库地址和目录名目前仍然是 `picture`，因为 GitHub 仓库还没实际改名
- 模型权重、Pixiv 凭证、本地字体等不会跟仓库一起下，需要你自己按需准备
- 如果只想先试基础功能，先不配 Pixiv 和 GPU 超分也能跑

### 1. 启动桌面工作台

推荐先用可见终端启动，方便排查环境问题：

```powershell
start_webview.bat
```

如果环境已经稳定，也可以双击：

- `open_webview.vbs`

旧版 Tk GUI 仍然保留：

```powershell
start.bat
```

### 2. CLI 示例

水印：

```powershell
python main.py watermark -i input.jpg -o output.jpg -t "YourName"
```

打码：

```powershell
python main.py mosaic -i input.jpg -o output.jpg -r "100,100,200,200" -m pixelate
```

Real-ESRGAN 超分：

```powershell
python main.py upscale -i input.jpg -o output.png -e realesrgan -s 4 -m RealESRGAN_x4plus_anime_6B.pth
```

Real-CUGAN 超分：

```powershell
python main.py upscale -i input.jpg -o output.png -e realcugan -s 4 -m RealCUGAN-se --noise -1
```

APISR 超分：

```powershell
python main.py upscale -i input.jpg -o output.png -e apisr -s 4 -m APISR-RRDB
```

批处理流水线：

```powershell
python main.py pipeline `
  -i .\input `
  -o .\output `
  --watermark `
  --mosaic `
  --upscale `
  --upscale-engine realcugan `
  --upscale-model RealCUGAN-se `
  --upscale-scale 4 `
  --upscale-noise -1
```

## 超分说明

### Real-ESRGAN

- 更偏通用
- 支持传入本地 `.pth` 权重路径
- 也会自动搜索常见模型目录

如果自动下载失败，可以直接指定本地权重：

```powershell
python main.py upscale -i input.jpg -o output.png -e realesrgan -m D:\models\RealESRGAN_x4plus_anime_6B.pth
```

### Real-CUGAN

- 更适合二次元图
- 支持 `2x / 3x / 4x`
- 可选降噪等级

### APISR

- 细节会更锐一点
- 适合拿来对比 `Real-CUGAN`

## Pixiv 功能

当前 Pixiv 面板支持：

- 浏览器自动投稿
- `Cookie + CSRF` 直传
- metadata 标签提取
- `原样 / 日文优先 / 双语精简` 标签语言策略
- OpenAI-compatible LLM 标签润色
- 标签上限控制
- 标签锁定
- 基础 NSFW 安全策略

### 安全说明

- Pixiv `cookie`
- Pixiv `csrf_token`
- LLM `api_key`

这些敏感字段现在不会再持久化写入 `webview_config.json`，只保留在当前运行会话里。

## 字体功能

水印支持：

- 预设字体
- 自定义字体文件
- 字体小样预览
- 在线读取和下载开源字体列表

## 测试

运行回归测试：

```powershell
python -m unittest discover -s tests -v
```

运行环境自检：

```powershell
python test_setup.py
```

## 已知说明

- `pywebview` 前端仍在持续迭代，优先保证可用性
- 部分超分后端依赖较重，GPU 环境体积会比较大
- 如果启动时卡在“等待桌面桥接”，优先使用 `start_webview.bat` 查看可见日志
