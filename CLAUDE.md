# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How to run

```bash
source venv/bin/activate
python main.py
```

Setup (once): `pip install -r requirements.txt && playwright install chromium`

## Architecture

Single-file Playwright automation script (`main.py`) that drives a headless Chromium to bulk-block Bilibili commenters.

**Core loop** (process one → wait for Bilibili to refresh → re-scan):

1. Find a visible, unprocessed "more" button via `bili-comment-action-buttons-renderer >> div#more > button` (Playwright `>>` pierces the outer Shadow DOM)
2. Extract UID + username by walking `getRootNode().host → parentElement` chain up to Light DOM, then read `bili-comment-user-info` Shadow DOM for the name
3. Force the CSS-hidden button to `display: block !important` (Bilibili hides it with `--bili-comment-hover-more-display`), dispatch click via JS
4. Pierce `bili-comment-menu` Shadow DOM via `.shadowRoot.querySelector('li')`, click "加入黑名单"
5. Auto-click the confirmation dialog
6. Wait for Bilibili's comment list to refresh, then re-scan

**Key design decisions:**

- **All DOM interaction uses JS `evaluate()`**, not Playwright's `click()`/`hover()`/`scroll_into_view_if_needed()`. Playwright's actionability checks time out on CSS-hidden elements (30s). `dispatchEvent(new MouseEvent('click', ...))` in JS bypasses all visibility checks.
- **Button is hidden by default**: Bilibili uses `--bili-comment-hover-more-display` CSS variable — the "more" button is `display: none` until mouse hover. The script force-overrides inline styles rather than relying on hover triggers.
- **One comment per iteration**: After each block, Bilibili removes the comment from the DOM and refreshes the list. The loop re-scans after every successful block to avoid stale element errors.
- **Dedup by UID**: `data-user-profile-id` from the user avatar link identifies unique commenters; `processed_uids` set prevents double-blocking.
- **Null-safe DOM traversal**: Every step of the `getRootNode().host → parentElement` chain has null guards — page refreshes can detach elements at any time.

## Configuration

Two constants at the top of `main.py`:

- `COOKIE_RAW` — paste the full Cookie string from browser DevTools (name1=value1; name2=value2; ...)
- `VIDEO_URL` — target video URL; leave empty to be prompted each run

**⚠️ Never commit the Cookie.** It contains the full login session.
