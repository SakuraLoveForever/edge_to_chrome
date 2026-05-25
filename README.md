# Browser Tab Transfer — 浏览器标签页一键转移

Chrome ↔ Edge ↔ Firefox 任意互转。选中源浏览器和目标浏览器，一键将所有打开的标签页转移到目标浏览器中打开。

## 工作方式

- **Chrome / Edge**：通过键盘模拟 (`Ctrl+L` → `Ctrl+C` → 读剪贴板 → `Ctrl+Tab`) 逐个读取地址栏 URL，100% 准确。
- **Firefox**：直接读取并解压 `sessionstore-backups\recovery.jsonlz4` 会话文件，无需切换标签页。

## 运行环境

- Windows 10 / 11
- 源浏览器必须正在运行且有打开的标签页
- 目标浏览器无需提前打开（会自动启动）

## 使用

```bash
pip install -r requirements.txt
python browser_tab_transfer.py
```

或者下载 `dist/BrowserTabTransfer.exe` 直接运行。

1. 选择 **源浏览器**（从哪个浏览器读取标签页）
2. 选择 **目标浏览器**（在哪个浏览器中打开）
3. 点击 **一键转移**

> **注意**：读取 Chrome/Edge 标签页时会短暂切换标签页，这是正常现象。完成后会自动回到原始标签页。

## 构建 EXE

```bash
build.bat
```

或手动：

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name "BrowserTabTransfer" ^
    --hidden-import requests ^
    --hidden-import lz4 --hidden-import lz4.block ^
    --hidden-import win32gui --hidden-import win32con ^
    --hidden-import win32api --hidden-import win32process ^
    --hidden-import win32clipboard ^
    browser_tab_transfer.py
```

## 依赖

| 包 | 用途 |
|---|---|
| `pywin32` | Chrome/Edge 标签页读取（键盘模拟 + 剪贴板） |
| `lz4` | Firefox 会话文件解压 |
| `requests` | 保留 |
