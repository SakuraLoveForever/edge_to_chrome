@echo off
chcp 65001 >nul
echo ========================================
echo   浏览器标签页转移工具 - 构建 EXE
echo ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
pip install -r requirements.txt pyinstaller -q

echo [2/3] 清理旧构建...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [3/3] 构建 EXE...
pyinstaller --onefile --windowed --name "BrowserTabTransfer" ^
    --hidden-import requests ^
    --hidden-import lz4 ^
    --hidden-import lz4.block ^
    --hidden-import win32gui ^
    --hidden-import win32con ^
    --hidden-import win32api ^
    --hidden-import win32process ^
    --hidden-import win32clipboard ^
    browser_tab_transfer.py

echo.
echo ========================================
echo   构建完成！EXE 在 dist 目录下
echo ========================================
pause
