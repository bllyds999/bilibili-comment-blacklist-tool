#!/usr/bin/env python3
"""
哔哩哔哩评论区批量拉黑工具

DOM 结构（关键）：
  div#body              ← 每条评论的根容器（Light DOM）
  a#user-avatar[data-user-profile-id]  ← 用户 UID
  div#main
    div#header
    bili-comment-user-info    ← Shadow DOM → #user-name > a（用户名）
    div#content
    bili-rich-text        ← Shadow DOM → #contents（评论正文）
    div#footer
    bili-comment-action-buttons-renderer  ← Shadow DOM
      div#more
      button           ← 「更多」按钮
      bili-comment-menu    ← Shadow DOM → ul#options > li（菜单项）

嵌套 Shadow DOM 穿透策略：
  - 用 Playwright 的 >> 组合器找到 Shadow DOM 内的按钮
  - 用 JS evaluate + getRootNode().host 从按钮跨越 Shadow DOM 边界到 Light DOM
  - 用 JS evaluate + shadowRoot 穿透 bili-comment-menu 的 Shadow DOM 点击菜单项

使用方式：
  source venv/bin/activate
  python main.py
"""

import asyncio
import random
import re
import sys
import time
from typing import Optional

from playwright.async_api import async_playwright, Page

# ============================================================
# 固定配置 — Cookie 写在这里，不用每次粘贴
# ============================================================

# 在浏览器中打开 bilibili.com，DevTools → Application → Cookies，
# 全选复制所有 Cookie，粘贴到下面的三引号之间。
COOKIE_RAW = """

"""

# 要处理的视频 URL（可留空，每次运行时输入）
VIDEO_URL = ""


# ============================================================
# Cookie 解析
# ============================================================

def parse_cookie_string(raw: str) -> list[dict]:
  """
  解析用户粘贴的 Cookie 字符串，转为 Playwright 格式。

  支持格式：
    1. 浏览器 DevTools 复制： "name1=value1; name2=value2; ..."
    2. Netscape 导出格式（多行，含 \t 分隔符）
  """
  cookies = []
  domain = ".bilibili.com"

  if "\n" in raw.strip():
    for line in raw.strip().split("\n"):
      line = line.strip()
      if not line or line.startswith("#"):
        continue
      parts = line.split("\t")
      if len(parts) >= 7:
        name, value = parts[5], parts[6]
      elif "=" in line:
        name, value = line.split("=", 1)
      else:
        continue
      cookies.append({
        "name": name.strip(),
        "value": value.strip(),
        "domain": domain,
        "path": "/",
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
      })
  else:
    for pair in raw.split(";"):
      pair = pair.strip()
      if "=" not in pair:
        continue
      name, value = pair.split("=", 1)
      cookies.append({
        "name": name.strip(),
        "value": value.strip(),
        "domain": domain,
        "path": "/",
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
      })

  if not cookies:
    print("⚠️  未解析到任何 Cookie，请检查输入格式。")
    sys.exit(1)

  print(f"✅ 解析到 {len(cookies)} 个 Cookie")
  return cookies


# ============================================================
# 获取评论信息（UID + 用户名），跨越 Shadow DOM 边界
# ============================================================

async def get_comment_info(button) -> dict:
  """
  从「更多」按钮出发，跨越 Shadow DOM 边界到 Light DOM，
  提取评论的用户 UID 和用户名。

  返回: {"uid": str, "username": str}
  """
  info = await button.evaluate('''
    (btn) => {
      // Step 1: 从按钮所在的 Shadow DOM 跳到 Light DOM
      const actionButtons = btn.getRootNode().host;
      if (!actionButtons) return {uid: null, username: '未知'};

      const footer = actionButtons.parentElement;
      if (!footer) return {uid: null, username: '未知'};

      const main = footer.parentElement;
      if (!main) return {uid: null, username: '未知'};

      const body = main.parentElement;
      if (!body) return {uid: null, username: '未知'};

      // Step 2: 从 div#body 的子元素中获取用户信息
      const avatar = body.querySelector(':scope > a#user-avatar');
      const profileId = avatar ? avatar.getAttribute('data-user-profile-id') : null;

      // Step 3: 穿透 bili-comment-user-info 的 Shadow DOM 获取用户名
      const userInfo = body.querySelector('bili-comment-user-info');
      let username = '未知';
      if (userInfo && userInfo.shadowRoot) {
        const nameLink = userInfo.shadowRoot.querySelector('#user-name a');
        if (nameLink) {
          username = nameLink.textContent.trim();
        }
      }

      // Step 4: 回退 — 用 bili-rich-text 中的评论内容前20字做标识
      let snippet = '';
      const richText = body.querySelector('bili-rich-text');
      if (richText && richText.shadowRoot) {
        const contents = richText.shadowRoot.querySelector('#contents');
        if (contents) {
          snippet = contents.textContent.trim().substring(0, 30);
        }
      }

      return {
        uid: profileId || ('fallback-' + snippet),
        username: username,
        snippet: snippet,
      };
    }
  ''')
  return info


# ============================================================
# 确认弹窗处理
# ============================================================

async def handle_confirmation_dialog(page: Page, timeout: float = 3.0) -> bool:
  """
  等待并自动点击 B 站「确定拉黑」弹窗中的确认按钮。
  """
  confirm_selectors = [
    "text=确定",
    "text=确认",
    "button:has-text('确定')",
    "button:has-text('确认')",
    "[class*='primary']:has-text('确定')",
    "[class*='primary']:has-text('确认')",
    ".bili-modal button:has-text('确定')",
    "[class*='dialog'] button:has-text('确定')",
  ]

  for _ in range(int(timeout * 10)):
    for sel in confirm_selectors:
      try:
        btn = page.locator(sel).first
        if await btn.is_visible(timeout=100):
          await btn.click()
          await asyncio.sleep(0.5)
          return True
      except Exception:
        pass
    await asyncio.sleep(0.1)

  return False


# ============================================================
# 处理单条评论：点更多 → 点加入黑名单
# ============================================================

async def process_one_comment(page: Page, button) -> bool:
  """
  处理一条评论的拉黑操作（全程 JS evaluate，跳过 Playwright 可见性检查）：

    1. 强制设置 CSS 让被隐藏的「更多」按钮可见
    2. 点击「更多」按钮
    3. 穿透 bili-comment-menu 的 Shadow DOM → 点击「加入黑名单」
    4. 处理确认弹窗
  """
  try:
    clicked = await button.evaluate('''
      async (btn) => {
        // --- 1. 强制让「更多」按钮及其容器可见 ---
        // B 站用 CSS 变量 --bili-comment-hover-more-display 控制显隐，
        // 默认 display:none，只有鼠标悬停才出现。
        // 直接改 inline style 强制露出。
        const moreDiv = btn.closest('div#more');
        if (moreDiv) {
          moreDiv.style.setProperty('display', 'block', 'important');
          moreDiv.style.setProperty('visibility', 'visible', 'important');
          moreDiv.style.setProperty('opacity', '1', 'important');
        }
        btn.style.setProperty('display', 'inline-block', 'important');
        btn.style.setProperty('visibility', 'visible', 'important');
        btn.style.setProperty('opacity', '1', 'important');
        // 等一帧确保样式生效
        await new Promise(r => requestAnimationFrame(r));

        // --- 2. 点击「更多」按钮 ---
        btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
        await new Promise(r => setTimeout(r, 400));

        // --- 3. 在 bili-comment-menu 的 Shadow DOM 中点击「加入黑名单」---
        if (!moreDiv) return false;
        const menu = moreDiv.querySelector('bili-comment-menu');
        if (!menu || !menu.shadowRoot) return false;

        const items = menu.shadowRoot.querySelectorAll('li');
        for (const li of items) {
          if (li.textContent && li.textContent.includes('加入黑名单')) {
            li.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return true;
          }
        }
        return false;
      }
    ''')

    if not clicked:
      try:
        await page.get_by_text("加入黑名单", exact=True).first.click(timeout=2000)
        clicked = True
      except Exception:
        pass

    if not clicked:
      return False

    # 4. 等待并处理确认弹窗
    await asyncio.sleep(0.8)
    await handle_confirmation_dialog(page, timeout=2.0)

    return True

  except Exception as e:
    print(f"   ❌ 处理出错: {e}")
    return False


# ============================================================
# 主循环：处理一条 → 等待页面刷新 → 下一条
# ============================================================

async def run_blacklist_loop(page: Page):
  """
  主循环（适配 B 站拉黑后自动刷新评论的行为）：

    1. 找到一条未处理的评论 → 拉黑
    2. 等待页面自动刷新（该评论消失，新评论顶上）
    3. 继续找下一条
    4. 当前可见的都处理完了 → 缓慢滚动加载更多
    5. 到达底部且无新评论 → 结束
  """
  processed_uids: set[str] = set()
  total_blacklisted = 0
  no_new_streak = 0       # 连续"找不到未处理评论"的次数
  scroll_accumulator = 0    # 累计滚动距离，偶尔需要滚一下加载更多

  print("\n🚀 开始处理评论（拉黑一条 → 页面自动刷新 → 下一条）...\n")

  while True:
    # --- 尝试找一条未处理的评论 ---
    buttons = await page.locator(
      "bili-comment-action-buttons-renderer >> div#more > button"
    ).all()

    found_one = False
    for i, button in enumerate(buttons):
      try:
        info = await get_comment_info(button)
        uid = info.get("uid", f"unknown-{i}")
        username = info.get("username", "未知")

        if uid in processed_uids:
          continue  # 已拉黑过

        # 找到了！处理它
        found_one = True
        processed_uids.add(uid)

        print(f"🔨 [{total_blacklisted + 1}] 正在拉黑: {username} (UID: {uid}) ...")

        success = await process_one_comment(page, button)

        if success:
          total_blacklisted += 1
          print(f"   ✅ 已拉黑: {username}（累计 {total_blacklisted} 人）")
        else:
          print(f"   ⚠️  跳过: {username}（菜单点击失败）")

        # 拉黑后 B 站会刷新评论区，等待 DOM 稳定
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # 处理完一条就 break，重新扫描（因为页面已刷新，旧元素可能失效）
        break

      except Exception:
        # 页面刷新导致元素失效是正常的，跳过这条重新扫描
        continue

    # --- 根据结果决定下一步 ---
    if found_one:
      no_new_streak = 0
      continue  # 继续找下一条可见评论

    # --- 当前可见评论都已处理，需要滚动加载更多 ---
    no_new_streak += 1

    if no_new_streak >= 4:
      # 连续多次找不到新评论，可能到底了
      print("\n⏳ 连续多次未发现新评论，尝试最后滚动...")
      await page.evaluate("window.scrollBy(0, 1000)")
      await asyncio.sleep(5)

      # 最终扫描
      any_new = False
      final_buttons = await page.locator(
        "bili-comment-action-buttons-renderer >> div#more > button"
      ).all()
      for b in final_buttons:
        try:
          info = await get_comment_info(b)
          if info.get("uid") and info.get("uid") not in processed_uids:
            any_new = True
            break
        except Exception:
          # 元素可能已失效（页面变化），跳过
          continue

      if not any_new:
        print(f"\n🏁 已完成！共拉黑 {total_blacklisted} 人。")
        break
      else:
        no_new_streak = 0
        print("   发现新评论，继续处理...\n")
        continue

    # --- 缓慢滚动，加载更多评论 ---
    scroll_delta = random.randint(300, 500)
    current_scroll = await page.evaluate("window.scrollY")
    page_height = await page.evaluate("document.body.scrollHeight")

    await page.evaluate(f"window.scrollBy(0, {scroll_delta})")

    wait_time = random.uniform(2.0, 3.5)
    await asyncio.sleep(wait_time)

    print(f"   📜 滚动 {scroll_delta}px | 位置 {current_scroll}/{page_height} | 已拉黑 {total_blacklisted} 人")

    # 如果到底了
    if current_scroll + scroll_delta >= page_height - 100:
      await asyncio.sleep(3)  # 等待可能的懒加载
      new_height = await page.evaluate("document.body.scrollHeight")
      if new_height <= page_height:
        no_new_streak += 1

  return total_blacklisted


# ============================================================
# 程序入口
# ============================================================

async def main():
  print("=" * 60)
  print("  哔哩哔哩评论区 · 批量拉黑工具")
  print("=" * 60)
  print()

  # --- 获取 Cookie ---
  cookie_str = COOKIE_RAW.strip()
  if not cookie_str:
    print("❌ 请先在 main.py 顶部的 COOKIE_RAW 中粘贴你的 B 站 Cookie。")
    print("   浏览器 DevTools → Application → Cookies → 全选复制 → 粘贴到三引号之间。")
    sys.exit(1)

  # --- 获取视频 URL ---
  video_url = VIDEO_URL.strip()
  if not video_url:
    video_url = input("🔗 请输入视频页面 URL: ").strip()
  else:
    print(f"🔗 使用配置中的视频 URL: {video_url}")

  if not video_url:
    print("❌ 未输入视频 URL，程序退出。")
    sys.exit(1)

  # --- 解析 Cookie ---
  cookies = parse_cookie_string(cookie_str)

  # --- 启动无头浏览器 ---
  print("\n🌐 正在启动无头浏览器...")
  async with async_playwright() as p:
    browser = await p.chromium.launch(
      headless=True,
      args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
      ],
    )

    context = await browser.new_context(
      viewport={"width": 1920, "height": 1080},
      user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
      ),
      locale="zh-CN",
    )

    await context.add_cookies(cookies)

    page = await context.new_page()

    # 自动接受原生 alert/confirm 弹窗（备用）
    page.on("dialog", lambda dialog: asyncio.ensure_future(_accept_dialog(dialog)))

    # --- 打开视频页面 ---
    print(f"📄 正在加载: {video_url}")
    try:
      await page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
      print("⚠️  页面加载超时，尝试继续...")
      await page.wait_for_timeout(3000)

    try:
      await page.wait_for_load_state("load", timeout=15000)
    except Exception:
      pass
    print("✅ 页面加载完成")

    # 等待评论区渲染
    await asyncio.sleep(3)

    # 先滚一下，触发评论区懒加载
    await page.evaluate("window.scrollBy(0, 800)")
    await asyncio.sleep(3)

    # --- 主循环 ---
    try:
      total = await run_blacklist_loop(page)
      print(f"\n🎉 程序运行完毕，共拉黑 {total} 人。")
    except KeyboardInterrupt:
      print(f"\n⏹️  用户中断。")
    finally:
      await browser.close()
      print("👋 浏览器已关闭。")


async def _accept_dialog(dialog):
  """自动接受浏览器原生弹窗"""
  try:
    await dialog.accept()
  except Exception:
    pass


if __name__ == "__main__":
  asyncio.run(main())
