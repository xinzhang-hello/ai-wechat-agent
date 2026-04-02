# WECHAT-EXPLORER — 微信 Windows UI 探索式开发完全指南

> 本文档教你（或 AI Agent）如何在不依赖现有库封装的情况下，从零探索 Windows 微信桌面版的 UI 结构，
> 基于探索结果编写可靠的自动化适配器，并应对不同版本之间的 UI 变更。
>
> 类比 CLI-EXPLORER.md（Web 站点 API 探索），本指南将浏览器换成 pywinauto + win32gui，
> 将网络抓包换成 UIA 树快照，将 DOM 交互换成控件的 `click_input()` 和键盘事件。

**配套脚本：** `explore_wechat.py`（零依赖 pyweixin 库，仅用 pywinauto + win32gui + pyautogui）

---

## AI Agent 开发者必读：主动探索优先

> **警告**：不要直接猜控件名称或 auto_id！WeChat 4.0 有 GPU 渲染层，部分控件对 UIA 不可见，
> 必须先跑 `explore_wechat.py --snapshot` 实际观察树结构，再写代码。

### 为什么？

微信桌面版基于 Qt（`mmui::` 命名空间），UI 结构在不同版本中频繁变动：
- 按钮的 `title` 在中/英文版 WeChat 中不同
- GPU 渲染（硬件加速）导致大量控件（右键菜单、部分列表项）UIA **不可见** —— 必须用截图分析
- `auto_id` 在 4.0 系列中逐渐规范化，但部分旧控件仍只能靠 `class_name` 或坐标定位

### AI Agent 探索工作流（必须遵循）

| 步骤 | 命令/方法 | 目的 |
|------|-----------|------|
| 0. 连接微信 | `find_wechat_hwnd()` | 获取主窗口句柄，建立 pywinauto 连接 |
| 1. 全局快照 | `snapshot_tree(win)` | 打印 UIA 树，找到各控件的 class/auto_id/title |
| 2. 导航探索 | `explore_nav_sections(win)` | 依次点击侧边栏各按钮，对每个视图快照 |
| 3. 交互测试 | `search_and_open(win, name)` | 搜索好友 → 打开聊天 → 确认 input 控件可达 |
| 4. GPU 回退检测 | `screenshot_analysis(region)` | 当 UIA 返回空或 ElementNotFoundError 时拍截图 |
| 5. 写适配器 | — | 基于 Step 1-3 确认的控件路径写代码 |

### 常犯错误

| ❌ 错误做法 | ✅ 正确做法 |
|------------|-----------|
| 直接假设 `title='搜索'` 可用 | 先 `snapshot_tree` 确认当前状态有搜索 Edit |
| 只用 `child_window(title=...)` 一步定位 | 先确认父容器存在，再找子控件 |
| 遇到 `ElementNotFoundError` 就放弃 | 检查是否 GPU 渲染 → 截图分析 → 键盘导航回退 |
| 以为搜索结果是 `mmui::SearchContentCellView` | 先 `search_result_list.print_control_identifiers()` 确认实际类名 |
| 切换页签后立即操作 | 等待 0.3-0.8s 或 `wait('exists', timeout=N)` 后再操作 |

---

## 核心流程

```
┌────────────────┐    ┌─────────────────┐    ┌──────────────────┐    ┌────────┐
│ 0. 连接主窗口  │ ──▶ │ 1. UIA树快照     │ ──▶ │ 2. 导航/交互探索  │ ──▶ │ 3. 写  │
│  (win32gui)    │    │ (pywinauto tree) │    │ (click+snapshot)  │    │  代码  │
└────────────────┘    └─────────────────┘    └──────────────────┘    └────────┘
          ↓ GPU渲染无法访问？
   ┌──────────────────────┐
   │ 截图分析 / 键盘导航  │
   └──────────────────────┘
```

---

## Step 0: 连接微信主窗口

微信 4.0 基于 Qt，窗口类名为 `Qt51514QWindowIcon`（数字随版本变化）模式匹配。
pywinauto 访问到的真实类名是 `mmui::MainWindow`。

```python
import re, win32gui
from pywinauto import Desktop

desktop = Desktop(backend='uia')

def find_wechat_hwnd():
    """枚举所有 Qt 窗口，找到 mmui::MainWindow。"""
    pattern = re.compile(r'Qt\d+QWindowIcon')
    candidates = []
    def _cb(hwnd, _):
        if pattern.match(win32gui.GetClassName(hwnd)):
            candidates.append(hwnd)
    win32gui.EnumDesktopWindows(0, _cb, None)

    for hwnd in candidates:
        try:
            cn = desktop.window(handle=hwnd).class_name()
            if 'mmui::MainWindow' in cn:
                return hwnd
        except Exception:
            pass
    return 0

hwnd = find_wechat_hwnd()
main_window = desktop.window(handle=hwnd)
```

**已知窗口类名（WeChat 4.0）：**

| 类名 | 描述 |
|------|------|
| `mmui::MainWindow` | 主界面（聊天、朋友圈等） |
| `mmui::LoginWindow` | 登录界面（扫码/账号密码） |
| `mmui::IndependentWindow` / `mmui::ChatWindow` | 独立弹出聊天窗口 |
| `mmui::SNSWindow` | 朋友圈独立窗口 |
| `mmui::PreviewWindow` | 图片/视频预览窗口 |
| `mmui::ProfileUniquePop` | 好友个人资料弹窗 |
| `mmui::SearchWindow` | 搜一搜独立窗口 |

---

## Step 1: UI 树快照

类比浏览器 DevTools 的 Elements 面板。

```python
def snapshot_tree(ctrl, depth=0, max_depth=6, output=None):
    """递归打印 UIA 树：类名、控件类型、title、auto_id、矩形区域"""
    if output is None:
        output = []
    if depth > max_depth:
        return output
    try:
        info = {
            'depth': depth,
            'class_name': ctrl.class_name(),
            'control_type': ctrl.element_info.control_type,
            'title': ctrl.window_text()[:60],
            'auto_id': ctrl.element_info.automation_id,
            'rect': str(ctrl.rectangle()),
        }
        indent = '  ' * depth
        output.append(
            f"{indent}[{info['control_type']}] class={info['class_name']!r} "
            f"title={info['title']!r} auto_id={info['auto_id']!r} rect={info['rect']}"
        )
    except Exception as e:
        output.append(f"{'  '*depth}[ERROR] {e}")
        return output
    try:
        for child in ctrl.children():
            snapshot_tree(child, depth+1, max_depth, output)
    except Exception:
        pass
    return output
```

**快照策略：**
- 先用 `max_depth=3` 获取顶层骨架
- 对感兴趣的子树用 `max_depth=6` 深度挖掘
- 对 GPU 渲染区域（快照为空）改用截图

---

## Step 2: 主界面结构（WeChat 4.0 已探索）

```
mmui::MainWindow  (根窗口)
├── [ToolBar]  auto_id='main_tabbar'  title='导航'   ← 左侧导航栏
│   ├── [Button]  title='微信'        ← 聊天会话列表
│   ├── [Button]  title='通讯录'      ← 联系人列表
│   ├── [Button]  title='收藏'        ← 收藏夹
│   ├── [Button]  title='朋友圈'      ← (WeChat 4.0: 坐标点击，GPU渲染)
│   ├── [Button]  title='视频号'
│   ├── [Button]  title='搜一搜'
│   ├── [Button]  title='更多'        ← 底部更多菜单
│   └── [Button]  title='设置'
│
├── [List]  title='会话'  framework_id='Qt'  ← 会话列表 (聊天视图)
│   └── [ListItem]  class='mmui::ChatSessionCell'  ← 每条会话
│
├── [Edit] class='mmui::XValidatorTextEdit' title='搜索'  ← 搜索栏 (通讯录视图)
│
├── [List]  auto_id='search_list'  title=''  ← 搜索结果列表
│   ├── [ListItem]  title='联系人'            ← 分组标题（不可点击）
│   ├── [ListItem]  class='mmui::SearchContentCellView'  title='<friend>'  ← 可点击
│   └── ...
│
└── [Edit]  auto_id='chat_input_field'  ← 聊天输入框 (聊天视图)
```

### 导航栏各按钮的功能说明

| 按钮 title | auto_id | 功能 | 打开后的主要控件变化 |
|-----------|---------|------|---------------------|
| `微信` | (在 main_tabbar 内, found_index=0) | 显示最近会话列表 | `List title='会话'` 出现 |
| `通讯录` | — | 显示联系人列表 + 搜索栏 | `Edit class='mmui::XValidatorTextEdit'` 出现 |
| `收藏` | — | 显示收藏内容列表 | — |
| `朋友圈` | — | **GPU渲染** → 截图分析或坐标点击 | 打开 `mmui::SNSWindow` 独立窗口 |
| `视频号` | — | 打开视频号界面 | — |
| `搜一搜` | — | 打开搜一搜界面 | — |
| `更多` | — | 底部弹出菜单 | GPU渲染菜单 → 键盘导航 |
| `设置` | — | 打开设置面板 | — |

---

## Step 3: 接入策略分级（类比 CLI-EXPLORER 认证 Tier）

```
控件是否在 UIA 树中可见？
  → ✅ Tier 1: 直接 child_window(auto_id=...) 或 child_window(title=...)
  → ❌ UIA 可见但控件属性不稳定？
       → ✅ Tier 2: child_window(class_name=..., control_type=..., found_index=N)
       → ❌ 控件完全 GPU 渲染 (ElementNotFoundError)?
              → ✅ Tier 3: 键盘导航 (Tab / 方向键 / Enter)
              → ❌ 键盘也无效？
                     → ✅ Tier 4: 截图分析 + 坐标点击 (pyautogui)
                     → ❌ Tier 5: Win32 API 直接发消息 (SendMessage / PostMessage)
```

| Tier | 策略 | 速度 | 适用场景 | 示例 |
|------|------|------|---------|------|
| 1 | auto_id / title | 最快 | 搜索栏、输入框 | `child_window(auto_id='chat_input_field')` |
| 2 | class_name + found_index | 快 | 导航按钮、会话列表项 | `child_window(class_name='mmui::XTabBarItem', found_index=0)` |
| 3 | 键盘导航 | 中 | GPU渲染上下文菜单 | `key_press('Down', 3); key_press('Enter')` |
| 4 | 截图+坐标 | 慢 | 完全不透明的GPU层 | `pyautogui.click(x, y)` + `screenshot()` 验证 |
| 5 | Win32 API | 最慢 | 极端情况 | `win32gui.SendMessage(hwnd, WM_CHAR, ...)` |

---

## Step 4: 搜索好友并发送消息（探索发现的完整路径）

通过 `explore_wechat.py --snapshot` 探索后确认的控件路径：

```
操作流程:
  1. 切换到"微信"（聊天）视图  →  main_tabbar 内 title='微信' Button
     ⚠️  必须在聊天视图！通讯录视图的搜索栏是 GPU 渲染，UIA 不可见。
  2. 点击搜索栏          →  class='mmui::XValidatorTextEdit', found_index=0
  3. 输入好友名称         →  set_text(name) / clipboard paste
  4. 等待搜索结果         →  0.9s sleep（结果是懒加载）
  5. 点击结果项           →  auto_id='search_list' → mmui::SearchContentCellView
                              备注可包含 emoji，用 'name in item_text' 子串匹配
  6. 等待聊天界面加载     →  0.6s sleep
  7. 点击输入框           →  auto_id='chat_input_field'
  8. 写入消息             →  clipboard paste（避免中文输入法问题）
  9. 发送                 →  Alt+S
```

**注意事项：**
- Step 2 搜索栏 **仅在通讯录视图可访问**（聊天视图的搜索栏被 GPU 渲染或隐藏）
- Step 8 必须用剪贴板粘贴而非 `type_keys`，因为中文字符无法通过 `type_keys` 直接输入
- Step 9 发送快捷键为 `Alt+S`（WeChat 4.0 默认，非 `Enter`）

---

## Step 5: GPU 渲染特殊处理

WeChat 4.0 在以下场景存在 GPU 渲染层，UIA 无法直接访问：

| 场景 | 症状 | 解决方案 |
|------|------|---------|
| GPU渲染重复UIA副本 | `child_window(auto_id='main_tabbar')` 抛出"27个元素匹配"错误 | 必须加 `found_index=0` |
| 右键上下文菜单 | `ElementNotFoundError: MenuItem not found` | Tier 3: 键盘 `Down×N` + `Enter` |
| 朋友圈导航按钮 | 坐标点击或 UIA Button 可能都失效 | Tier 4: 截图确认位置后坐标点击 |
| 图片预览窗口内控件 | 窗口可见但子控件无法枚举 | `SetForegroundWindow` + `HWND_TOPMOST` 后截图 |
| 部分列表项渲染 | `window_text()` 返回空字符串 | 截图 + OCR 或坐标推算 |

### GPU 渲染检测模式

```python
import pyautogui, time

def try_uia_or_screenshot(ctrl_spec, fallback_region, tag):
    """
    先尝试 UIA 访问；若控件不存在或 window_text() 为空，
    则截图存档供肉眼 / 视觉模型分析。
    """
    try:
        if ctrl_spec.exists(timeout=0.5):
            text = ctrl_spec.window_text()
            if text:
                return ('uia', text)
    except Exception:
        pass
    # GPU渲染回退：截图
    time.sleep(0.2)
    screenshot = pyautogui.screenshot(region=fallback_region)
    path = f'debug_screenshots/{tag}_{int(time.time())}.png'
    screenshot.save(path)
    return ('screenshot', path)
```

---

## 已知 WeChat 4.0 UI 常量速查表

```python
# ── 窗口类名 ──────────────────────────────────────────
MAIN_WINDOW_CLASS    = 'mmui::MainWindow'
LOGIN_WINDOW_CLASS   = 'mmui::LoginWindow'
SNS_WINDOW_CLASS     = 'mmui::SNSWindow'          # 朋友圈
PREVIEW_WINDOW_CLASS = 'mmui::PreviewWindow'       # 图片预览
PROFILE_POPUP_CLASS  = 'mmui::ProfileUniquePop'    # 好友资料弹窗

# ── 导航栏 ────────────────────────────────────────────
NAV_TOOLBAR_AUTO_ID  = 'main_tabbar'               # 左侧 ToolBar
NAV_CHAT_TITLE       = '微信'                       # 聊天入口
NAV_CONTACTS_TITLE   = '通讯录'                     # 通讯录入口

# ── 搜索相关（⚠️ 仅在 微信/聊天 视图中有效，通讯录视图 UIA 返回 0 个 Edit）────
# GPU渲染致重复副本：child_window 必须加 found_index=0，否则抛"27个元素匹配"异常
SEARCH_EDIT_CLASS    = 'mmui::XValidatorTextEdit'  # 聊天视图搜索栏，无 auto_id
SEARCH_LIST_AUTO_ID  = 'search_list'               # 搜索结果列表
SEARCH_RESULT_CLASS  = 'mmui::SearchContentCellView'  # 可点击的结果项（含emoji备注如'糖葫芦🍡'）

# ── 聊天区 ─────────────────────────────────────────────
CHAT_INPUT_AUTO_ID   = 'chat_input_field'          # 消息输入框
SESSION_LIST_TITLE   = '会话'                       # 最近会话列表
SESSION_ITEM_CLASS   = 'mmui::ChatSessionCell'     # 会话列表项
```

---

## 实战成功案例：5 分钟实现「给好友发消息」

以下是用上述工作流实际完成发送消息的完整记录：

```
1. find_wechat_hwnd()
   → hwnd=XXXXXX, class=mmui::MainWindow  ✓

2. snapshot_tree(main_window, max_depth=2)
   → [ToolBar] auto_id='main_tabbar' title='导航'  ← 找到导航栏
   → [List] title='会话'                            ← 当前在聊天视图

3. 切换到通讯录 (title='通讯录' Button)
   → [Edit] class='mmui::XValidatorTextEdit' title='搜索'  ← 找到搜索栏

4. 输入 '糖葫芦' → 等待 0.8s
   → [List] auto_id='search_list'
     → [ListItem] title='联系人' (分组标题)
     → [ListItem] class='mmui::SearchContentCellView' title='糖葫芦'  ← 目标！

5. 点击结果项 → 等待 0.5s
   → [Edit] auto_id='chat_input_field'  ← 聊天输入框出现 ✓

6. 剪贴板粘贴消息 → Alt+S 发送
   → 消息发出 ✓
```

---

## 版本差异处理策略

当脚本在新版本 WeChat 上出错时，按以下顺序检查：

1. **运行 `explore_wechat.py --snapshot`**：对当前 UI 状态拍全树快照
2. **对比已知常量**：看哪些 `class_name` / `auto_id` 发生了变化
3. **使用 Tier 降级**：Tier 1 不工作 → 尝试 Tier 2 → ... → Tier 4
4. **更新常量表**：确认新路径后更新 `WECHAT-EXPLORER.md` 的速查表
5. **写测试**：确保发送一条测试消息成功后再提交修复

---

## 进一步探索（参考 CLI-EXPLORER 进阶章节）

- **联系人列表懒加载**：通讯录列表需要滚动才会加载更多条目（类比 Web 的分页 API）
- **消息历史分页**：聊天记录向上滚动触发加载（类比 API 的 `pn` 参数）
- **群聊 @成员**：`type_keys('@')` 后出现成员列表（GPU 渲染，需截图分析或键盘导航）
- **文件发送**：Ctrl+V 粘贴文件路径，或用 `type_keys('{ENTER}')` 打开文件选择器


## 开发过程
探索阶段的文件都放到debug目录下

## 其他文档、历史经验
参考 ref/*.md文档