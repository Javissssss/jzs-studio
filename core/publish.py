# -*- coding: utf-8 -*-
"""Publish helpers - DRAFT ONLY, never clicks publish (red line).

v1 approach = assisted publishing (reliable):
  WeChat: render final HTML in agent-browser -> select-all -> copy rich text to
          clipboard -> open mp editor (jzs profile) -> user pastes & saves draft.
  XHS:    gather card PNGs + copy text -> open creator platform (jzs-xhs profile)
          -> user uploads images, pastes text, saves draft.

agent-browser is launched --headed so the user can take over at any time.
"""

import os
import shutil
import subprocess
import sys

from . import config

WECHAT_DRAFT_URL = "https://mp.weixin.qq.com"
XHS_PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
XHS_DRAFT_URL = "https://creator.xiaohongshu.com/new/note-manager"

PROFILE_WECHAT = os.path.join(
    os.path.expanduser("~"), ".agent-browser", "profiles", "jzs"
)
PROFILE_XHS = os.path.join(
    os.path.expanduser("~"), ".agent-browser", "profiles", "jzs-xhs"
)


def _agent_browser_cmd():
    """Locate agent-browser executable."""
    exe = shutil.which("agent-browser")
    if exe:
        return exe
    # Windows npm global
    npm_dir = os.path.join(os.environ.get("APPDATA", ""), "npm")
    for name in ("agent-browser.cmd", "agent-browser.ps1", "agent-browser"):
        cand = os.path.join(npm_dir, name)
        if os.path.exists(cand):
            return cand
    return "agent-browser"


def _run_ab(args, timeout=60):
    ab = _agent_browser_cmd()
    cmd = [ab] + args
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            shell=(os.name == "nt" and ab.endswith((".cmd", ".ps1"))),
        )
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


def open_in_default_browser(path):
    """Open a local file in the OS default browser."""
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa
            return True
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return True
        else:
            subprocess.Popen(["xdg-open", path])
            return True
    except Exception:
        return False


def copy_html_to_clipboard(html_path):
    """Copy rendered HTML as RICH TEXT to system clipboard via agent-browser.
    Falls back to plain-text clipboard if agent-browser unavailable."""
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    ok, log = _run_ab(["open", url], timeout=45)
    if ok:
        _run_ab(["press", "Control+a"], timeout=15)
        ok2, log2 = _run_ab(["press", "Control+c"], timeout=15)
        if ok2:
            return True, "富文本已复制到剪贴板（agent-browser）"
    # fallback: plain text via OS clipboard
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        if os.name == "nt":
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            p.communicate(content.encode("utf-16le"))
            return (
                True,
                "HTML源码已复制到剪贴板（纯文本降级，建议在浏览器里打开终版HTML手动Ctrl+A/C）",
            )
    except Exception as e:
        return False, f"复制失败：{e}"
    return False, "agent-browser 不可用，请手动打开终版HTML复制"


def open_platform(platform, profile=None):
    """Open WeChat/XHS platform headed in agent-browser (login reused via profile)."""
    if platform == "wechat":
        url, prof = WECHAT_DRAFT_URL, profile or PROFILE_WECHAT
    elif platform == "xhs":
        url, prof = XHS_PUBLISH_URL, profile or PROFILE_XHS
    else:
        return False, "unknown platform"
    ok, log = _run_ab(["--profile", prof, "--headed", "open", url], timeout=60)
    return ok, log


def copy_text_to_clipboard(text):
    """Copy plain text to system clipboard."""
    try:
        if os.name == "nt":
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-16le"))
            return True
        elif sys.platform == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
        else:
            p = subprocess.Popen(
                ["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE
            )
            p.communicate(text.encode("utf-8"))
            return True
    except Exception:
        return False


def wechat_kit(pid, state):
    """Build the WeChat publish kit: paths + urls + steps."""
    out_dir = os.path.join(config.project_dir(pid), "output")
    html_file = state.get("render", {}).get("html_path") or ""
    imgs = []
    if os.path.isdir(out_dir):
        for f in sorted(os.listdir(out_dir)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                imgs.append(os.path.join(out_dir, f))
    return {
        "html_path": html_file,
        "images": imgs,
        "draft_url": WECHAT_DRAFT_URL,
        "steps": [
            "1. 点「复制富文本」把终版HTML渲染内容复制到剪贴板",
            "2. 点「打开公众号后台」（首次需扫码登录 jzs profile）",
            "3. 草稿箱 → 新的创作 → 写新图文",
            "4. 正文区点击一下 → Ctrl+V 粘贴（保留砖红米白排版）",
            "5. 标题/摘要手动填；正文图片若未随粘贴上传，用工具栏「图片」逐张上传 output/ 里的PNG",
            "6. 点「保存为草稿」—— 永不点「发表」，发布由你人工完成",
        ],
    }


def xhs_kit(pid, state):
    """Build the XHS publish kit."""
    out_dir = os.path.join(config.project_dir(pid), "output")
    cards = []
    if os.path.isdir(out_dir):
        for f in sorted(os.listdir(out_dir)):
            if f.lower().endswith(".png") and (
                f.startswith(("0", "1", "2")) or "card" in f.lower() or "封面" in f
            ):
                cards.append(os.path.join(out_dir, f))
    draft = state.get("draft", {})
    return {
        "cards": cards,
        "text": draft.get("xhs_md", ""),
        "titles": draft.get("xhs_titles", []),
        "tags": draft.get("xhs_tags", []),
        "publish_url": XHS_PUBLISH_URL,
        "draft_url": XHS_DRAFT_URL,
        "steps": [
            "1. 点「打开小红书创作平台」（首次需扫码登录 jzs-xhs profile）",
            "2. 上传图文 → 按 01-0N 顺序上传 output/ 里的卡片PNG",
            "3. 标题填选定那个（≤20字）；正文粘贴文案（点「复制文案」）",
            "4. 末尾 #标签 逐个输入，等下拉候选出现再点选精确匹配",
            "5. 点「保存草稿」—— 永不点「发布」",
            "提醒：发布期间同账号勿在其他网页端登录（会互踢）",
        ],
    }
