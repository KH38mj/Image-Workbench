# Image Workbench

[![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个偏本地工作流的 AI 图片后处理工具，支持水印、打码、超分、批处理，以及 Pixiv 投稿辅助。

当前项目以 Windows 桌面使用为主，推荐优先使用 `pywebview` 工作台。

## 适合谁

- 想把 AI 出图后的水印、打码、超分放进一套桌面流程里的人
- 想把单图处理、批处理、Pixiv 投稿辅助集中到同一个界面的人
- 想利用 metadata、LLM 和浏览器自动化来整理 Pixiv 标签的人

## 主要功能

### 图片处理

- 水印
  - 自定义文字
  - 自定义字体文件 `TTF / OTF / TTC`
  - 内置字体预设与字体预览
  - 在线读取和下载 Google Fonts
- 打码
  - 像素化
  - 高斯模糊
  - 多区域拖拽框选
- 超分
  - `Real-ESRGAN`
  - `Real-CUGAN`
  - `APISR`
  - 支持批处理工作流

### 桌面工作台

- `pywebview` 双栏工作台
- 单图预览与选区编辑
- 最近文件列表
- 批量处理与安全停止
- 内置日志面板
- 日志复制 / 导出 / 清空

### Pixiv 投稿辅助

- 浏览器自动投稿
- `Cookie + CSRF` 直传模式
- metadata 标签提取
- `原样 / 日文优先 / 双语精简` 标签语言策略
- OpenAI-compatible LLM 标签润色
- 标签上限控制与标签锁定
- NSFW / R-18 / R-18G 基础安全护栏
- Pixiv 投稿页调试快照导出

### 最近修复

- 修复 Pixiv 浏览器投稿页里 token/chip 型标签输入框的兼容问题
- 避免在追加下一个标签时误删前一个已经确认的标签
- 改进 Pixiv 标签容器定位与标签确认逻辑
- 新增 `抓取 Pixiv 调试快照` 调试入口，便于抓取投稿页 HTML / JSON / 截图

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `main.py` | CLI 主入口，包含水印、打码、超分、批处理 |
| `webview_app.py` | `pywebview` 桌面桥接后端 |
| `webui/` | `pywebview` 前端资源 |
| `pixiv_uploader.py` | Pixiv 上传与浏览器自动化逻辑 |
| `pixiv_llm.py` | OpenAI-compatible 标签整理器 |
| `tests/` | 自动化回归测试 |
| `start_webview.bat` | 可见终端启动器 |
| `open_webview.vbs` | 隐藏终端启动器 |
| `PROGRESS.md` | 开发过程记录 |

## 环境要求

- Windows
- 建议 Python `3.12`
- 建议使用独立虚拟环境
- 如需 GPU 超分，`torch` / CUDA 版本需要与显卡环境匹配

安装依赖：

```powershell
pip install -r requirements.txt
```

## 快速开始

### 0. clone 后最快跑起来

```powershell
git clone https://github.com/KH38mj/Image-Workbench.git
cd Image-Workbench
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
- 模型权重、Pixiv 凭证、本地字体不会随仓库一起下发
- 只测试基础功能时，不配置 Pixiv 和 GPU 超分也能运行

### 1. 启动桌面工作台

推荐先用可见终端启动，方便排查环境问题：

```powershell
start_webview.bat
```

环境稳定后，也可以直接双击：

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

## Pixiv 工作流说明

当前 Pixiv 面板支持：

- 浏览器自动投稿
- `Cookie + CSRF` 直传
- metadata 标签提取
- LLM 标签整理
- 自动限制到 Pixiv 当前 10 标签上限
- 手动确认投稿页后再提交

### 浏览器投稿模式

推荐在下面这些场景使用：

- 你想在投稿页手动检查标题、标签、说明
- 你需要保留浏览器登录态
- 你想观察 Pixiv 前端实际表现

### 调试 Pixiv 标签问题

如果浏览器投稿页的标签行为异常，可以这样抓现场：

1. 在工作台里点击 `处理当前图片并打开 Pixiv 草稿`，或首页的 `单图一键草稿`
2. 保持 Pixiv 投稿页打开
3. 点击 `抓取 Pixiv 调试快照`
4. 到 `tmp_pixiv_diag/` 查看输出的 `.json`、`.html`、`.png`

这套快照主要用于排查：

- 标签容器定位错误
- 推荐标签点击未确认
- token/chip 输入框误删已确认标签
- Pixiv 前端 DOM 结构变化

## 安全说明

以下字段不会再持久化写入 `webview_config.json`：

- Pixiv `cookie`
- Pixiv `csrf_token`
- LLM `api_key`

这些敏感字段只保留在当前运行会话内，重启工作台后需要重新填写。

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

- `pywebview` 前端仍在持续迭代，当前优先保证可用性
- 部分超分后端依赖较重，GPU 环境体积会比较大
- 如果启动时卡在“等待桌面桥接”，优先使用 `start_webview.bat` 查看日志
- Pixiv 浏览器投稿模式依赖页面结构，Pixiv 前端改版后可能需要重新适配
