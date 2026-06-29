# 🚫 Bilibili Comment Blacklist Tool / 哔哩哔哩评论区批量拉黑工具

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Playwright](https://img.shields.io/badge/Playwright-1.40%2B-green)](https://playwright.dev)

> ⚠️ **免责声明 / Disclaimer**
>
> 使用 B 站 Cookie 运行本脚本有**封号风险**，请酌情考虑。本工具仅供学习研究使用，作者不对因使用本工具导致的任何后果负责。
>
> Running this script with your Bilibili Cookie carries a **risk of account suspension/ban**. Use at your own discretion. This tool is for educational purposes only. The author is not responsible for any consequences arising from its use.

Automatically block commenters on Bilibili videos. Runs a headless browser, scrolls through the comment section, finds every comment's "more" menu, clicks "Block user" through nested Shadow DOMs, and confirms the dialog.

自动遍历 B 站视频评论区，找到每条评论的「更多」按钮，穿透嵌套 Shadow DOM 点击「加入黑名单」，并自动确认弹窗。全无头浏览器运行。

---

## Features / 功能

- **No manual Cookie input each time** — paste once, reuse forever / Cookie 一次配置，永久生效
- **Headless Chromium** — runs in background, no visible browser / 全后台运行，无浏览器窗口
- **Nested Shadow DOM piercing** — handles `bili-comment-action-buttons-renderer` + `bili-comment-menu` double Shadow DOM / 正确处理双层嵌套 Shadow DOM
- **Slow scroll + lazy load detection** — scrolls 300–500px at a time, waits for comments to load / 缓慢滚动加载评论区
- **Post-blacklist refresh handling** — Bilibili refreshes after each block; the tool re-scans immediately / 拉黑后评论区自动刷新，程序实时重新扫描
- **Dedup by UID** — never blocks the same user twice / 按 UID 去重，不会重复拉黑
- **Per-user logging** — prints the username and UID being blocked / 实时输出被拉黑的用户名和 UID
- **Confirmation dialog auto-dismiss** — automatically clicks "Confirm" on the modal / 自动点击确认弹窗

---

## How It Works / 工作原理

1. **Open page** — Open the Bilibili video page with Cookie injected / 注入 Cookie，打开 B 站视频页面
2. **Scroll** — Scroll down 300–500px at a time, wait 2–3.5s for comments to lazy-load / 缓慢滚动 300–500px，每次等待 2–3.5s 让评论区懒加载
3. **Find comment** — Locate unprocessed comments by UID (dedup) / 按 UID 找到未处理的评论（自动去重）
4. **Show button** — Force CSS `display:block` on the hidden "more" button / 强制 CSS 露出被隐藏的「更多」按钮
5. **Click "more"** — Dispatch a click event to open the menu / 模拟点击展开菜单
6. **Block user** — Pierce `bili-comment-menu` Shadow DOM, click "加入黑名单" / 穿透 Shadow DOM 点击"加入黑名单"
7. **Confirm** — Auto-click the confirmation dialog / 自动点击确认弹窗
8. **Refresh** — Bilibili refreshes the comment list; go back to step 3 / B 站刷新评论区，回到步骤 3 继续
9. **Scroll more** — When no unprocessed comments are visible, scroll again; exit when reaching bottom / 当前可见评论全部处理完后，继续滚动加载更多；到达底部后自动退出

## Prerequisites / 前置要求

- **macOS** (tested on macOS Sequoia) / 已在 macOS Sequoia 上测试
- **Python 3.10+** (Python 3.14.6 used in development) / 开发使用 Python 3.14.6

---

## Setup / 安装部署

### 1. Clone / 克隆项目

```bash
git clone <your-repo-url> demo6
cd demo6
```

### 2. Create virtual env / 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate      # macOS / Linux
# or on Windows: venv\Scripts\activate
```

### 3. Install dependencies / 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

This installs Playwright in the local `venv/` and downloads a Chromium browser (~170 MB). Everything stays in the project — no system pollution.

(安装到本地 `venv/`，Chromium 浏览器也下载到用户缓存中，不污染系统环境)。

### 4. Configure / 配置

Edit `main.py` and fill in two items:

编辑 `main.py`，填入以下两项：

#### a) Cookie

Open Chrome DevTools (`F12` or `Cmd+Option+I`) on `bilibili.com`:

1. Go to **Application** → **Storage** → **Cookies** → `https://www.bilibili.com`
2. Click any row, press `Cmd+A` to select all, `Cmd+C` to copy
3. Paste between the triple quotes of `COOKIE_RAW` in `main.py`:

在 bilibili.com 打开浏览器 DevTools → Application → Cookies → 全选复制，粘贴到 `main.py` 的 `COOKIE_RAW` 中：

```python
COOKIE_RAW = """
buvid3=...; SESSDATA=...; bili_jct=...; ...
"""
```

> ⚠️ The Cookie contains your login session. **Never commit or share it.** Treat it like a password.
> Cookie 包含你的登录态，**切勿提交到 Git 或分享给他人**，请像密码一样保管。

#### b) Video URL / 视频链接

```python
VIDEO_URL = "https://www.bilibili.com/video/BV1iKfYBeE6Q/"
```

Leave empty (`""`) if you want to type the URL each time you run.

留空则每次运行时手动输入。

---

## Usage / 使用方式

```bash
source venv/bin/activate
python main.py
```

The headless browser will:

1. Open the video page
2. Scroll down to trigger comment section loading
3. Process each comment one by one (block → wait for refresh → next)
4. Scroll further when all visible comments are done
5. Exit when reaching the bottom with no new comments

无头浏览器将自动打开视频页面，缓慢滚动加载评论区，逐条拉黑，到达底部后自动退出。

### Output example / 输出示例

```
🚀 开始处理评论（拉黑一条 → 页面自动刷新 → 下一条）...

🔨 [1] 正在拉黑: 我的屁屁凑凑的 (UID: 1145141919810) ...
   ✅ 已拉黑: 我的屁屁凑凑的（累计 1 人）
🔨 [2] 正在拉黑: 另一位用户 (UID: 1234567890) ...
   ✅ 已拉黑: 另一位用户（累计 2 人）
   📜 滚动 423px | 位置 2400/8560 | 已拉黑 2 人
🔨 [3] 正在拉黑: 第三位用户 (UID: 5678901234) ...
   ✅ 已拉黑: 第三位用户（累计 3 人）

🏁 已完成！共拉黑 3 人。
```

---

## Technical Details / 技术细节

### Shadow DOM Structure / DOM 结构

```
bili-comment-action-buttons-renderer  ← Shadow Root (open)
  ├── div#more
  │   ├── button                      ← "more" / 「更多」
  │   └── bili-comment-menu           ← Shadow Root (open)
  │       └── ul#options
  │           ├── li: 复制评论链接
  │           ├── li: 加入黑名单       ← target
  │           └── li: 举报
  └── ...

bili-comment-user-info                ← Shadow Root (open)
  └── #user-name > a                  ← username / 用户名
```

### CSS Visibility Issue / CSS 显隐问题

Bilibili uses `--bili-comment-hover-more-display` CSS variable — the "more" button has `display: none` by default and only appears on mouse hover. Playwright's visibility checks fail on hidden elements, causing 30-second timeouts.

B 站用 CSS 变量控制「更多」按钮显隐，默认 `display: none`，只有鼠标悬停才出现。Playwright 的可见性检查会卡住。

**Solution / 解决方案**: All interactions are done via `element.evaluate()` in JavaScript,:
- Forcibly set `display: block !important; visibility: visible !important; opacity: 1 !important` on the target element
- Use `dispatchEvent(new MouseEvent('click', ...))` to fire clicks (works even on elements with `display: none`)
- Pierce Shadow DOMs via `.shadowRoot.querySelector()`

全部用 JS `evaluate()` 操作：
- 强制覆盖 CSS 让按钮可见
- 用 `dispatchEvent` 触发点击（即使 `display:none` 也能工作）
- 通过 `.shadowRoot` 穿透 Shadow DOM

---

## Project Structure / 项目结构

```
demo6/
├── main.py              # Main script / 主程序
├── requirements.txt     # Python dependencies / Python 依赖
├── venv/                # Virtual environment (created by setup) / 虚拟环境
└── README.md            # This file / 本文件
```

---

## Safety Notes / 安全须知

1. **Cookie security**: Your Cookie grants full access to your Bilibili account. Never commit it to Git. The current `main.py` in this repo has a **real but expired** Cookie — replace it with your own.
   Cookie 包含你的完整登录权限，切勿提交到 Git。当前代码中的 Cookie 已过期，请替换为你自己的。

2. **Rate limiting**: The tool adds random delays (0.5–1.5s between operations, 300–500px scrolls with 2–3.5s pauses). This mimics human behavior and reduces the risk of triggering captchas.
   程序加入了随机延迟模拟人类行为，降低触发验证码的风险。

3. **Use responsibly**: Bulk blocking users may not align with Bilibili's terms of service. Use at your own risk.
   批量拉黑行为可能不符合 B 站服务条款，请自行承担风险。

---

## License / 许可

MIT
