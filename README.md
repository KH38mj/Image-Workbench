# Image Workbench

[![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个偏本地工作流的 AI 图片后处理工具，主打把水印、打码、超分、批量处理，以及 Pixiv 投稿辅助整合到同一个 Windows 桌面工作台里。

当前推荐使用 `pywebview` 桌面版工作台。

## 适合谁

- 想把 AI 出图后的水印、打码、超分放进一套桌面流程里的人
- 想把单图处理、批量处理、自动投稿收拢到一个界面里的人
- 想结合 metadata、LLM、浏览器自动化来整理 Pixiv 标签和标题的人

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

### 桌面工作台

- `pywebview` 双栏工作区
- 单图预览与选区编辑
- 最近文件列表
- 批量处理进度、失败项重试与安全停止
- 日志复制、导出、清空
- 更稳的窗口布局与缩放适配

### Pixiv 投稿辅助

- 浏览器自动填写投稿页
- `Cookie + CSRF` 直传模式
- 从浏览器导入 Pixiv 登录态
- 自动检测直传鉴权并补齐 `CSRF Token`
- metadata 标签提取
- OpenAI-compatible LLM 标签整理
- 模板 + AI 混合标题生成
- 标题风格预设
  - 默认
  - 简洁
  - 梦幻
  - 日系轻小说
  - 角色中心
  - 自定义 Prompt
- Pixiv 预览生成
  - 标题
  - 标签
  - 说明
  - 性描写判定结果
  - 当前标题风格预设
- Pixiv 投稿页调试快照导出

## 最近更新

- 修复 Pixiv 投稿页标签输入在 token/chip 模式下的确认与误删问题
- 优化 Pixiv 标签确认逻辑与调试日志
- 增加 Pixiv 调试快照导出，方便抓 HTML / JSON / 截图
- 打通 Pixiv 浏览器登录态导入与直传鉴权探测
- 支持 AI 标题润色与标题风格预设
- Pixiv 预览里会显示当前标题风格与 AI 标题润色情况
- 首页与工作区体验做过一轮可用性优化

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `main.py` | CLI 入口，包含水印、打码、超分、批处理 |
| `webview_app.py` | `pywebview` 桌面桥接后端 |
| `webui/` | `pywebview` 前端资源 |
| `pixiv_uploader.py` | Pixiv 上传与浏览器自动化逻辑 |
| `pixiv_llm.py` | OpenAI-compatible Pixiv 标签与标题整理 |
| `tests/` | 回归测试 |
| `start_webview.bat` | 可见终端启动器 |
| `open_webview.vbs` | 隐藏终端启动器 |
| `PROGRESS.md` | 开发过程记录 |

## 环境要求

- Windows
- 建议 Python `3.12`
- 建议使用独立虚拟环境
- 如需 GPU 超分，`torch / CUDA` 版本需要与显卡环境匹配

安装依赖：

```powershell
pip install -r requirements.txt
```

## 快速开始

### 1. 克隆项目

```powershell
git clone https://github.com/KH38mj/Image-Workbench.git
cd Image-Workbench
py -3.12 -m venv .venv312
.venv312\Scripts\python.exe -m pip install -U pip
.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 启动桌面工作台

优先用可见终端启动，方便排查环境问题：

```powershell
start_webview.bat
```

环境稳定后，也可以直接双击：

- `open_webview.vbs`

旧版 Tk GUI 仍保留：

```powershell
start.bat
```

## CLI 示例

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

## Pixiv 工作流

当前 Pixiv 面板支持：

- 浏览器自动填写
- `Cookie + CSRF` 直传
- metadata 标签提取
- LLM 标签整理
- 模板 + AI 标题润色
- 自动限制到 Pixiv 当前 10 标签上限
- 性描写字段自动判定
- 投稿前预览

### 浏览器自动填写模式

适合这些场景：

- 你想在投稿页手动检查标题、标签、说明
- 你需要保留浏览器登录态
- 你想观察 Pixiv 前端真实表现

### 直传模式

适合这些场景：

- 想减少浏览器自动化的不稳定因素
- 想把登录态导入后直接做接口级上传
- 想在批量流程里少依赖前端页面交互

推荐流程：

1. 在 Pixiv 面板里先点“从浏览器导入登录态”
2. 如果只拿到 Cookie，点“检测直传”自动补齐 `CSRF Token`
3. 日志出现“Pixiv 直传鉴权可用”后，再正式使用直传模式

### 标题生成

标题现在支持两段式：

1. 先按标题模板生成基础标题
2. 再交给 LLM 做一次标题润色

你可以为标题润色选择风格预设，也可以切成自定义 Prompt。

Pixiv 预览日志里会显示：

- 当前生成的标题
- 当前标题风格预设
- 是否启用了 AI 标题润色

### 调试 Pixiv 标签问题

如果浏览器投稿页的标签行为异常，可以这样抓现场：

1. 在工作台里打开 Pixiv 草稿页
2. 保持 Pixiv 投稿页不要关
3. 点击“抓取 Pixiv 调试快照”
4. 到 `tmp_pixiv_diag/` 查看输出的 `.json`、`.html`、`.png`

这套快照主要用于排查：

- 标签容器定位错误
- 推荐标签点击后未确认
- token/chip 输入框误删已确认标签
- Pixiv 前端 DOM 结构变化

## 安全说明

以下字段不会再持久化写入 `webview_config.json`：

- Pixiv `cookie`
- Pixiv `csrf_token`
- LLM `api_key`

这些敏感字段只保留在当前运行会话里，重启工作台后需要重新填写或重新导入。

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
- Pixiv 浏览器自动填写模式依赖页面结构，Pixiv 改版后可能需要重新适配
