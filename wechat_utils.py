import re
import time
import json
import datetime
import pyautogui
import win32gui
import win32con
import win32com.client
import pyperclip
import sqlite3
from pathlib import Path
from pywinauto import Desktop

# ── Global Configuration ───────────────────────────────────────────────────
BACKEND = 'uia'
desktop = Desktop(backend=BACKEND)
pyautogui.FAILSAFE = False

DEBUG_DIR = Path(__file__).parent / 'debug_screenshots'
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ── WeChat 4.0 UI Constants ────────────────────────────────────────────────
MAIN_WINDOW_CLASS   = 'mmui::MainWindow'
LOGIN_WINDOW_CLASS  = 'mmui::LoginWindow'
NAV_TOOLBAR_AUTO_ID = 'main_tabbar'
NAV_CHAT_TITLE      = '微信'
NAV_CONTACTS_TITLE  = '通讯录'
SEARCH_EDIT_CLASS   = 'mmui::XValidatorTextEdit'
SEARCH_LIST_AUTO_ID = 'search_list'
SEARCH_RESULT_CLASS = 'mmui::SearchContentCellView'
CHAT_INPUT_AUTO_ID  = 'chat_input_field'
MESSAGE_LIST_AUTO_ID = 'chat_message_list'
MESSAGE_ITEM_AUTO_ID = 'chat_message_list.qt_scrollarea_viewport.chat_bubble_item_view'

# ── Database Methods ────────────────────────────────────────────────────────

def init_db(db_path="wechat_chat.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_name TEXT,
            sender TEXT,
            content TEXT,
            side TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def log_message(conn, chat_name, sender, content, side):
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (chat_name, sender, content, side)
        VALUES (?, ?, ?, ?)
    ''', (chat_name, sender, content, side))
    conn.commit()

# ── Core Methods ─────────────────────────────────────────────────────────────

def get_latest_message(win):
    msgs = get_history_messages(win, count=1)
    return msgs[-1] if msgs else None

def get_last_messages(win, count=5):
    """Alias for backward compatibility."""
    return get_history_messages(win, count)

def get_history_messages(win, count=5):
    """
    Retrieves messages and attempts to identify sender and side.
    """
    try:
        msg_list = win.child_window(auto_id=MESSAGE_LIST_AUTO_ID, control_type='List')
        if not msg_list.exists(timeout=1):
            return []
        
        items = msg_list.children(control_type='ListItem')
        if not items:
            return []
        
        results = []
        for item in items[-count*2:]:
            try:
                title = item.window_text()
                # WeChat message items typically end with a space
                is_bubble = title.endswith(' ') and item.element_info.automation_id == MESSAGE_ITEM_AUTO_ID
                
                if not is_bubble:
                    if title.strip():
                        results.append({'text': title.strip(), 'type': 'system', 'sender': 'System'})
                    continue

                # Side Detection (Tier 4): Pixel Analysis
                rect = item.rectangle()
                img = pyautogui.screenshot(region=(rect.left, rect.top, rect.width(), rect.height()))
                w, h = img.size
                
                # Sample points for avatar/bubble detection
                # Left side (Other) vs Right side (Self)
                left_px = img.getpixel((w // 10, h // 2))
                right_px = img.getpixel((w * 9 // 10, h // 2))
                
                side = 'unknown'
                sender = 'Unknown'
                
                # Check for Self (Green bubble or avatar on right)
                if right_px[1] > right_px[0] + 10 and right_px[1] > right_px[2] + 10:
                    side = 'right'
                    sender = 'Self'
                # Check for Other (White/Light bubble on left)
                elif left_px[0] > 230 and left_px[1] > 230 and left_px[2] > 230:
                    side = 'left'
                    # In group chats, if we can't get the sender via UIA, we label it as 'Other'
                    # or try to guess from context. For now, let's use 'Other' if we can't find a colon.
                    if ':' in title:
                        parts = title.split(':', 1)
                        sender = parts[0].strip()
                        content = parts[1].strip()
                    else:
                        sender = 'Other'
                        content = title.strip()
                else:
                    content = title.strip()

                results.append({
                    'text': title.strip() if 'content' not in locals() else content,
                    'type': 'message',
                    'side': side,
                    'sender': sender
                })
            except:
                continue
        
        return results[-count:]
    except:
        return []

def find_wechat_hwnd() -> int:
    pattern = re.compile(r'Qt\d+QWindowIcon')
    candidates = []
    def _enum_cb(hwnd, _):
        try:
            cn = win32gui.GetClassName(hwnd)
            if pattern.match(cn):
                candidates.append(hwnd)
        except: pass
    win32gui.EnumDesktopWindows(0, _enum_cb, None)
    for hwnd in candidates:
        try:
            win = desktop.window(handle=hwnd)
            if MAIN_WINDOW_CLASS in win.class_name():
                return hwnd
        except: continue
    return 0

def screenshot_save(tag: str, region=None) -> str:
    ts = datetime.datetime.now().strftime('%H%M%S')
    path = str(DEBUG_DIR / f'{tag}_{ts}.png')
    img = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
    img.save(path)
    return path

def get_main_window():
    hwnd = find_wechat_hwnd()
    if not hwnd: return None
    win = desktop.window(handle=hwnd)
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        shell = win32com.client.Dispatch('WScript.Shell')
        shell.SendKeys('%')
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.4)
    except: pass
    return win

def get_nav_toolbar(win):
    try:
        toolbar = win.child_window(auto_id=NAV_TOOLBAR_AUTO_ID, control_type='ToolBar', found_index=0)
        if toolbar.exists(timeout=2): return toolbar
    except: pass
    return None

def click_nav_button(toolbar, title: str) -> bool:
    try:
        btn = toolbar.child_window(title=title, control_type='Button')
        if btn.exists(timeout=0.5):
            btn.click_input()
            time.sleep(0.4)
            return True
    except: pass
    return False

def open_chat(win, name: str) -> bool:
    toolbar = get_nav_toolbar(win)
    if not toolbar or not click_nav_button(toolbar, NAV_CHAT_TITLE):
        return False
    time.sleep(0.6)
    try:
        edit = win.child_window(class_name=SEARCH_EDIT_CLASS, control_type='Edit', found_index=0)
        edit.click_input()
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.hotkey('delete')
        pyperclip.copy(name)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.9)
        result_list = win.child_window(auto_id=SEARCH_LIST_AUTO_ID, control_type='List')
        items = result_list.children(control_type='ListItem')
        for item in items:
            if name in item.window_text() and item.class_name() == SEARCH_RESULT_CLASS:
                item.click_input()
                time.sleep(0.6)
                return True
    except: pass
    return False

def send_message(win, message: str) -> bool:
    try:
        chat_input = win.child_window(auto_id=CHAT_INPUT_AUTO_ID, control_type='Edit')
        if not chat_input.exists(timeout=1): return False
        chat_input.click_input()
        pyperclip.copy(message)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.2)
        pyautogui.hotkey('alt', 's')
        return True
    except: return False
