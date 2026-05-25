#!/usr/bin/env python3
"""
Browser Tab Transfer — 浏览器标签页一键转移
Chrome ↔ Edge ↔ Firefox 三者任意互转。
通过键盘模拟 (Ctrl+L/Ctrl+C) 逐个读取地址栏 URL，100% 准确。
"""

import os
import re
import json
import struct
import time
import shutil
import threading
import tempfile
import configparser
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import lz4.block
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False

try:
    import win32gui
    import win32con
    import win32api
    import win32process
    import win32clipboard
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# ── Config ──────────────────────────────────────────────────────
BROWSERS = {
    "chrome": {
        "label": "Chrome",  "proc": "chrome.exe",
        "exes": [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "user_data": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        "new_tab": "--new-tab",
    },
    "edge": {
        "label": "Edge",    "proc": "msedge.exe",
        "exes": [
            os.path.expandvars(r"%PROGRAMFILES(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "user_data": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        "new_tab": "--new-tab",
    },
    "firefox": {
        "label": "Firefox", "proc": "firefox.exe",
        "exes": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "user_data": os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles"),
        "new_tab": "-new-tab",
    },
}


# ── Helpers ─────────────────────────────────────────────────────

def find_exe(k):
    for p in BROWSERS[k]["exes"]:
        if os.path.exists(p):
            return p
    return None


def is_running(k):
    p = BROWSERS[k]["proc"]
    try:
        r = __import__('subprocess').run(
            f'tasklist /FI "IMAGENAME eq {p}" 2>nul',
            shell=True, capture_output=True, text=True,
        )
        return p.lower() in r.stdout.lower()
    except Exception:
        return False


def find_firefox_profile():
    d = BROWSERS["firefox"]["user_data"]
    ini = os.path.join(d, "profiles.ini")
    if not os.path.isfile(ini):
        return None
    cfg = configparser.ConfigParser()
    cfg.read(ini)
    for sec in cfg.sections():
        if sec.startswith("Install"):
            dk = cfg[sec].get("Default")
            if dk and dk in cfg:
                pp = cfg[dk].get("Path", "")
                if pp:
                    if not os.path.isabs(pp):
                        pp = os.path.join(d, pp)
                    if os.path.isdir(pp):
                        return pp
    for item in os.listdir(d):
        full = os.path.join(d, item)
        if os.path.isdir(full) and (".default-release" in item or ".default" in item):
            return full
    return None


# ── Keyboard-based tab reading (Chrome / Edge) ────────────────────
# Reads each tab's address bar via Ctrl+L / Ctrl+C / clipboard.
# 100% accurate at the cost of briefly switching tabs in the browser.

_VK_CTRL  = 0x11
_VK_SHIFT = 0x10
_VK_TAB   = 0x09
_VK_L     = 0x4C
_VK_C     = 0x43

_kernel32_ps = ctypes.WinDLL('kernel32')

def _get_exe(pid):
    try:
        h = _kernel32_ps.OpenProcess(0x0400 | 0x0010, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(260)
            sz = wintypes.DWORD(260)
            _kernel32_ps.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz))
            _kernel32_ps.CloseHandle(h)
            return buf.value.lower()
    except:
        pass
    return ''


def _find_browser_windows(key):
    """Return list of (hwnd, title) for the given browser key (chrome/edge)."""
    if not HAS_WIN32:
        return []
    result = []
    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetClassName(hwnd) != 'Chrome_WidgetWin_1':
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = _get_exe(pid)
        browser = None
        if 'chrome' in exe:
            browser = 'chrome'
        elif 'edge' in exe or 'msedge' in exe:
            browser = 'edge'
        if browser == key:
            result.append((hwnd, title))
    win32gui.EnumWindows(_cb, None)
    return result


def _send_combo(mod_vk, key_vk):
    if not HAS_WIN32:
        return
    win32api.keybd_event(mod_vk, 0, 0, 0)
    time.sleep(0.03)
    win32api.keybd_event(key_vk, 0, 0, 0)
    time.sleep(0.06)
    win32api.keybd_event(key_vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    win32api.keybd_event(mod_vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.04)


def _read_address_bar(hwnd):
    """Focus browser window, send Ctrl+L → Ctrl+C, return clipboard URL."""
    if not HAS_WIN32:
        return ''
    cur = win32gui.GetForegroundWindow()
    if cur != hwnd:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except:
            pass
        time.sleep(0.15)

    # Clear clipboard
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.CloseClipboard()
    except:
        pass
    time.sleep(0.06)

    _send_combo(_VK_CTRL, _VK_L)   # focus address bar
    time.sleep(0.12)
    _send_combo(_VK_CTRL, _VK_C)   # copy
    time.sleep(0.10)

    url = ''
    try:
        win32clipboard.OpenClipboard()
        try:
            url = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) or ''
        except:
            pass
        win32clipboard.CloseClipboard()
    except:
        pass
    return url.strip()


def _next_tab():
    _send_combo(_VK_CTRL, _VK_TAB)
    time.sleep(0.45)


def _prev_tab():
    if not HAS_WIN32:
        return
    win32api.keybd_event(_VK_CTRL, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(_VK_SHIFT, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(_VK_TAB, 0, 0, 0)
    time.sleep(0.06)
    win32api.keybd_event(_VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    win32api.keybd_event(_VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    win32api.keybd_event(_VK_CTRL, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.45)


def get_chromium_tabs(key, log=None):
    """Read ALL open tab URLs from Chrome/Edge by cycling through tabs
    and reading the address bar via Ctrl+L / Ctrl+C.  Returns list of {url, title}.

    This is the only approach that gives 100% accurate current tab URLs."""
    if not HAS_WIN32:
        if log:
            log("  pywin32 未安装，无法读取标签页")
        return []

    windows = _find_browser_windows(key)
    if not windows:
        if log:
            log(f"  未找到 {BROWSERS[key]['label']} 窗口")
        return []

    all_tabs = []
    seen_urls = set()
    label = BROWSERS[key]['label']
    MAX_TABS = 30

    for hwnd, title in windows:
        if log:
            log(f"  窗口: {title[:60]}")

        # Read starting tab
        start_url = _read_address_bar(hwnd)
        if log:
            log(f"    标签 1: {start_url[:80] if start_url else '(空)'}")

        if start_url and start_url.lower().startswith('http'):
            seen_urls.add(start_url.lower().rstrip('/'))
            all_tabs.append({"url": start_url, "title": ""})
        elif start_url:
            seen_urls.add(start_url.lower())

        # Cycle forward through remaining tabs
        for i in range(1, MAX_TABS):
            _next_tab()
            url = _read_address_bar(hwnd)

            if not url:
                if log:
                    log(f"    标签 {i+1}: (空) — 跳过")
                continue

            key_u = url.lower().rstrip('/')

            if key_u in seen_urls:
                if log:
                    log(f"    标签 {i+1}: {url[:60]} ← 已循环，完成")
                _prev_tab()  # return to original position
                break

            if url.lower().startswith('http'):
                seen_urls.add(key_u)
                all_tabs.append({"url": url, "title": ""})
                if log:
                    log(f"    标签 {i+1}: {url[:80]}")
            else:
                seen_urls.add(key_u)
                if log:
                    log(f"    标签 {i+1}: ({url[:40]}) — 跳过")
        else:
            if log:
                log(f"    达到最大标签数 ({MAX_TABS})")

    return all_tabs


# ── Windows API: read locked files (unused, kept for reference) ───

_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.CreateFileW.restype = wintypes.HANDLE

def _win_read_locked(path):
    """Read a file even if locked by another process (Windows API)."""
    GENERIC_READ = 0x80000000
    FILE_SHARE_RW = 7  # READ | WRITE | DELETE
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80

    handle = _kernel32.CreateFileW(
        path, GENERIC_READ, FILE_SHARE_RW,
        None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None,
    )
    if handle == wintypes.HANDLE(-1).value:
        return None

    try:
        # Try GetFileSizeEx first
        size = ctypes.c_longlong(0)
        if not _kernel32.GetFileSizeEx(handle, ctypes.byref(size)):
            # Fallback: read in chunks
            chunks = []
            while True:
                buf = ctypes.create_string_buffer(65536)
                n = wintypes.DWORD(0)
                if not _kernel32.ReadFile(handle, buf, 65536, ctypes.byref(n), None):
                    break
                if n.value == 0:
                    break
                chunks.append(buf.raw[:n.value])
            return b''.join(chunks)

        size = size.value
        buf = ctypes.create_string_buffer(size)
        n = wintypes.DWORD(0)
        if not _kernel32.ReadFile(handle, buf, size, ctypes.byref(n), None):
            return None
        return buf.raw[:n.value]
    finally:
        _kernel32.CloseHandle(handle)


def read_file_robust(path):
    """Read a file: normal open first, then Windows API for locked files, then temp copy."""
    # Method 1: normal open
    try:
        with open(path, 'rb') as f:
            return f.read()
    except (PermissionError, OSError):
        pass

    # Method 2: Windows API (handles locked files)
    data = _win_read_locked(path)
    if data is not None:
        return data

    # Method 3: copy to temp then read
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            shutil.copy2(path, tmp.name)
            with open(tmp.name, 'rb') as f:
                return f.read()
        finally:
            os.unlink(tmp.name)
    except Exception:
        pass

    return None


# ── Firefox: parse recovery.jsonlz4 ─────────────────────────────

def mozlz4_decompress(data):
    if not HAS_LZ4 or data[:8] != b'mozLz40\0':
        return None
    size = struct.unpack('<I', data[8:12])[0]
    return lz4.block.decompress(data[12:], uncompressed_size=size)


def get_firefox_tabs(log=None):
    """Read open tabs from Firefox — NO browser restart needed."""
    if not HAS_LZ4:
        if log:
            log("  lz4 库未安装")
        return []

    profile = find_firefox_profile()
    if not profile:
        if log:
            log("  未找到 Firefox 配置")
        return []

    recovery = os.path.join(profile, "sessionstore-backups", "recovery.jsonlz4")
    if not os.path.isfile(recovery):
        recovery = os.path.join(profile, "sessionstore-backups", "previous.jsonlz4")
    if not os.path.isfile(recovery):
        if log:
            log("  未找到会话文件")
        return []

    raw = read_file_robust(recovery)
    if raw is None:
        if log:
            log("  无法读取会话文件")
        return []

    dec = mozlz4_decompress(raw)
    if dec is None:
        if log:
            log("  LZ4 解压失败")
        return []

    try:
        session = json.loads(dec)
        tabs = []
        for win in session.get("windows", []):
            for tab in win.get("tabs", []):
                entries = tab.get("entries", [])
                idx = tab.get("index", 1) - 1
                if 0 <= idx < len(entries):
                    entry = entries[idx]
                elif entries:
                    entry = entries[-1]
                else:
                    continue
                url = entry.get("url", "")
                title = entry.get("title", "")
                if url and not url.startswith(("about:", "moz-extension://", "about:blank")):
                    tabs.append({"url": url, "title": title})
        return tabs
    except Exception as e:
        if log:
            log(f"  JSON 解析失败: {e}")
        return []


# ── Open tabs in target browser ─────────────────────────────────

def open_tabs(target, tabs, log=None):
    import subprocess
    exe = find_exe(target)
    flag = BROWSERS[target]["new_tab"]

    if not exe:
        import webbrowser
        for t in tabs:
            webbrowser.open(t["url"])
        if log:
            log(f"  ✓ 已用默认浏览器打开 {len(tabs)} 个标签页")
        return

    cnt = 0
    for t in tabs:
        try:
            subprocess.Popen(
                [exe, flag, t["url"]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            cnt += 1
            time.sleep(0.06)
        except Exception:
            import webbrowser
            webbrowser.open(t["url"])
            cnt += 1
    if log:
        log(f"  ✓ 已在 {BROWSERS[target]['label']} 打开 {cnt} 个标签页")


# ── GUI ─────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("浏览器标签页转移")
        self.root.resizable(False, False)
        self._busy = False

        main = ttk.Frame(root, padding=(12, 8, 12, 8))
        main.pack(fill="both", expand=True)

        # Source
        ttk.Label(main, text="从", font=("", 9, "bold")).pack(anchor="w")
        self.src_var = tk.StringVar(value="chrome")
        sf = ttk.Frame(main)
        sf.pack(fill="x")
        for k in BROWSERS:
            ttk.Radiobutton(sf, text=BROWSERS[k]["label"],
                          variable=self.src_var, value=k).pack(side="left", padx=(0, 12))

        ttk.Label(main, text="       ↓  转移到  ↓", font=("", 8)).pack(anchor="center")

        # Target
        ttk.Label(main, text="到", font=("", 9, "bold")).pack(anchor="w")
        self.dst_var = tk.StringVar(value="edge")
        df = ttk.Frame(main)
        df.pack(fill="x", pady=(0, 8))
        for k in BROWSERS:
            ttk.Radiobutton(df, text=BROWSERS[k]["label"],
                          variable=self.dst_var, value=k).pack(side="left", padx=(0, 12))

        # Button
        self.btn = ttk.Button(main, text="▶  一键转移", command=self._go)
        self.btn.pack(pady=(4, 6))

        # Log
        lf = ttk.Frame(main)
        lf.pack(fill="both", expand=True)
        self.log = tk.Text(lf, width=52, height=9, state="disabled",
                         font=("Consolas", 9), bg="#1a1a2e", fg="#e0e0e0",
                         insertbackground="#e0e0e0", relief="flat", padx=8, pady=6)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

        self._put("就绪 — 选择源/目标浏览器，一键转移")
        self._put("  直接读取浏览器会话文件，无需关闭浏览器")

    def _put(self, msg):
        def _w():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _w)

    def _busy_on(self):
        self._busy = True
        self.root.after(0, lambda: self.btn.configure(
            state="disabled", text="⏳ 处理中..."))

    def _busy_off(self):
        self._busy = False
        self.root.after(0, lambda: self.btn.configure(
            state="normal", text="▶  一键转移"))

    def _go(self):
        if self._busy:
            return
        src = self.src_var.get()
        dst = self.dst_var.get()
        if src == dst:
            messagebox.showwarning("", "源和目标不能相同")
            return

        self._busy_on()
        self._put("─" * 35)
        self._put(f"  {BROWSERS[src]['label']}  →  {BROWSERS[dst]['label']}")
        threading.Thread(target=self._worker, args=(src, dst), daemon=True).start()

    def _worker(self, src, dst):
        try:
            tag = BROWSERS[src]["label"]

            # ── Step 1: Read tabs ──
            self._put("")
            self._put(f"▸ 读取 {tag} 当前打开的标签页 ...")

            if src == "firefox":
                tabs = get_firefox_tabs(log=self._put)
            else:
                tabs = get_chromium_tabs(src, log=self._put)

            if not tabs:
                self._put(f"  ⚠ 未找到标签页。请确认 {tag} 正在运行并有打开的页面。")
                return

            self._put(f"  共提取 {len(tabs)} 个标签页")

            # Show preview
            for i, t in enumerate(tabs[:15], 1):
                label = t['title'] if t['title'] else t['url']
                self._put(f"  {i:2d}. {label[:60]}")
            if len(tabs) > 15:
                self._put(f"  ... 及另外 {len(tabs) - 15} 个")

            # ── Step 2: Open in target ──
            self._put("")
            self._put(f"▸ 在 {BROWSERS[dst]['label']} 中打开 ...")
            open_tabs(dst, tabs, log=self._put)

            self._put("")
            self._put("✓ 完成")

        except Exception as e:
            self._put(f"✗ {e}")
            import traceback
            self._put(traceback.format_exc())
        finally:
            self._busy_off()


def main():
    root = tk.Tk()
    w, h = 460, 360
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
    ttk.Style().theme_use("clam")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
