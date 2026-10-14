# -*- coding: utf-8 -*-
"""XHS card generator: turn the XHS draft into 1080x1440 brick-red/rice-white
cards (single HTML with #card1..#cardN), then screenshot via xhs_screenshot.py."""

import html
import os
import re
import subprocess

from . import config

CARD_W, CARD_H = 1080, 1440

BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;background:#e8e4dc}
.card{width:1080px;height:1440px;position:relative;overflow:hidden;
  display:flex;flex-direction:column;padding:90px 80px}
.serif{font-family:"Noto Serif SC","Songti SC",serif}
/* cover */
.cover{background:linear-gradient(150deg,#2a211c 0%,#3d2b22 45%,#5a3527 100%);color:#FAF9F5}
.cover .brand{font-size:30px;letter-spacing:.35em;color:#E8A184;font-weight:600;margin-bottom:auto}
.cover .kicker{font-size:34px;color:#c9b8a8;margin-bottom:28px;letter-spacing:.05em}
.cover h1{font-size:88px;line-height:1.28;font-weight:800;margin-bottom:40px}
.cover .hook{font-size:38px;line-height:1.7;color:#e6d9cc;font-weight:300}
.cover .pageno{margin-top:auto;font-size:26px;color:#9a8878;letter-spacing:.2em}
.cover .accentbar{width:120px;height:10px;background:#C96442;border-radius:5px;margin:36px 0}
/* content */
.content{background:#FAF9F5;color:#141413}
.content .top{display:flex;align-items:center;gap:24px;margin-bottom:48px}
.content .num{font-size:30px;font-weight:800;color:#fff;background:#C96442;
  width:64px;height:64px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.content .ct{font-size:46px;font-weight:800;line-height:1.3;color:#141413}
.content .body{font-size:38px;line-height:1.85;color:#2a2a28;flex:1}
.content .body p{margin-bottom:30px}
.content .body .hl{color:#B04A3F;font-weight:700}
.content .foot{margin-top:auto;font-size:24px;color:#87867F;letter-spacing:.15em;
  border-top:2px solid #E3DACC;padding-top:28px;display:flex;justify-content:space-between}
/* closing */
.closing{background:linear-gradient(150deg,#141413 0%,#2a211c 100%);color:#FAF9F5}
.closing .quote{font-size:56px;line-height:1.6;font-weight:700;margin-bottom:auto;margin-top:60px}
.closing .quote .hl{color:#E8A184}
.closing .tags{font-size:32px;color:#c9b8a8;line-height:1.9;margin-top:50px}
.closing .cta{font-size:30px;color:#9a8878;margin-top:36px;letter-spacing:.05em}
"""


def _split_xhs(xhs_md):
    """Split XHS draft into (hook_lines, body_chunks, golden, tags)."""
    lines = [l.strip() for l in (xhs_md or "").splitlines()]
    tags = []
    content_lines = []
    for l in lines:
        if l.startswith("#") and " " not in l.strip("#"):
            tags.append(l)
        elif re.fullmatch(r"(#[^\s#]+)+", l):
            tags.extend(re.findall(r"#[^\s#]+", l))
        else:
            content_lines.append(l)
    # drop image-guide lines (📷图X) into markers but keep text
    cleaned = []
    for l in content_lines:
        l2 = re.sub(r"📷图?\d*", "", l).strip()
        if l2:
            cleaned.append(l2)
    # chunk by blank-ish separators: group consecutive non-empty lines
    chunks = []
    cur = []
    for l in cleaned:
        cur.append(l)
        # start new chunk after a line ending with emoji/colon or every ~3 lines
        if len(cur) >= 3 or l.endswith(("👇", "：", "!", "！")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    hook = chunks[0] if chunks else []
    body = chunks[1:-1] if len(chunks) > 2 else chunks[1:]
    golden = chunks[-1] if len(chunks) > 2 else []
    return hook, body, golden, tags


def build_cards_html(xhs_md, titles, tags=None, max_content=4):
    """Build single HTML with #card1..#cardN."""
    title = (titles[0] if titles else "干货分享")[:20]
    hook, body, golden, md_tags = _split_xhs(xhs_md)
    tags = tags or md_tags or []
    cards = []
    # Card 1: cover
    hook_text = " ".join(hook)[:60] if hook else "一次讲清，建议收藏"
    cards.append(f"""
<div class="card cover serif" id="card1">
  <div class="brand">巨人之上</div>
  <div class="kicker">今日分享</div>
  <h1>{html.escape(title)}</h1>
  <div class="accentbar"></div>
  <div class="hook">{html.escape(hook_text)}</div>
  <div class="pageno">01 / 干货</div>
</div>""")
    # Content cards
    n = 2
    for chunk in body[:max_content]:
        text = "<br>".join(html.escape(c) for c in chunk)
        # highlight first line as heading-ish
        cards.append(f"""
<div class="card content" id="card{n}">
  <div class="top"><div class="num">{n - 1}</div><div class="ct serif">{html.escape(chunk[0][:16])}</div></div>
  <div class="body"><p>{text}</p></div>
  <div class="foot"><span>巨人之上</span><span>{n:02d}</span></div>
</div>""")
        n += 1
    # Closing card
    golden_text = (
        " ".join(golden) if golden else (hook[-1] if hook else "认知升级，从借力开始")
    )
    tags_text = " ".join(tags[:8]) if tags else "#干货分享 #认知升级"
    cards.append(f"""
<div class="card closing serif" id="card{n}">
  <div class="quote">{html.escape(golden_text[:50])}</div>
  <div class="tags">{html.escape(tags_text)}</div>
  <div class="cta">关注「巨人之上」· 这个时代奖励最会借力的人</div>
</div>""")
    total = n
    return (
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>{BASE_CSS}</style></head><body>
{"".join(cards)}
</body></html>""",
        total,
    )


def generate_cards(pid, xhs_md, titles, tags=None):
    """Build cards HTML -> screenshot via xhs_screenshot.py. Returns list of PNG paths."""
    out_dir = os.path.join(config.project_dir(pid), "output")
    os.makedirs(out_dir, exist_ok=True)
    html_str, count = build_cards_html(xhs_md, titles, tags)
    html_path = os.path.join(out_dir, "_xhs_cards.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    script = os.path.join(config.SCRIPTS_DIR, "xhs_screenshot.py")
    names = ["封面"] + [f"内容{i}" for i in range(1, count - 1)] + ["收口"]
    names = names[:count]
    cmd = [
        config.PYTHON,
        script,
        "--html",
        html_path,
        "--out",
        out_dir,
        "--count",
        str(count),
        "--names",
        ",".join(names),
    ]
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        ok = p.returncode == 0
        log = (p.stderr or p.stdout or "")[-400:]
    except Exception as e:
        ok, log = False, str(e)
    pngs = sorted(
        [
            os.path.join(out_dir, f)
            for f in os.listdir(out_dir)
            if f.lower().endswith(".png") and re.match(r"^\d\d_", f)
        ]
    )
    return {"ok": ok, "count": count, "pngs": pngs, "log": log, "html": html_path}
