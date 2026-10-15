# -*- coding: utf-8 -*-
"""Save an article straight into the WeChat Official Account draft box (草稿箱)
through the official API. Pure stdlib.

Config (env or .env):
  JZS_WX_APPID / JZS_WX_SECRET   公众号后台 → 设置与开发 → 基本配置
  JZS_WX_AUTHOR                  optional, default = brand
Note: the caller's public IP must be in the account's IP whitelist.

Flow: access_token → upload body images (media/uploadimg → mmbiz URLs)
      → upload cover (material/add_material → thumb media_id) → draft/add.
WeChat strips <style>/<script>/classes, so the body is rebuilt here with
inline styles from the same markdown + media manifest.
"""

import html
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
import uuid

from . import config

API = "https://api.weixin.qq.com/cgi-bin"
ACCENT = "#C0392B"
FONT = '"Microsoft YaHei","微软雅黑","PingFang SC",sans-serif'


def settings():
    return {
        "appid": os.environ.get("JZS_WX_APPID", "").strip(),
        "secret": os.environ.get("JZS_WX_SECRET", "").strip(),
        "author": os.environ.get("JZS_WX_AUTHOR", "").strip() or config.brand(),
    }


def is_configured():
    s = settings()
    return bool(s["appid"] and s["secret"])


def public_info():
    s = settings()
    return {"configured": is_configured(), "appid": (s["appid"][:6] + "…") if s["appid"] else ""}


# ---------------- HTTP ----------------
def _check(data, what):
    if isinstance(data, dict) and data.get("errcode"):
        code, msg = data.get("errcode"), data.get("errmsg", "")
        hint = {
            40164: "调用 IP 不在公众号白名单：后台 → 设置与开发 → 基本配置 → IP 白名单，加上本机公网 IP",
            40125: "AppSecret 不对",
            40013: "AppID 不对",
            48001: "该公众号没有此接口权限（个人订阅号未认证时草稿/素材接口可能受限）",
            45009: "接口调用次数超限，明天再试",
        }.get(code, "")
        raise RuntimeError(f"{what}失败 errcode={code} {msg} {hint}".strip())
    return data


def _get_json(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_json(url, payload, timeout=60):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_file(url, path, field="media", timeout=60):
    boundary = uuid.uuid4().hex
    fname = os.path.basename(path)
    ctype = mimetypes.guess_type(fname)[0] or "image/png"
    with open(path, "rb") as f:
        raw = f.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode("utf-8") + raw + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


_token = {"v": "", "exp": 0}


def access_token():
    if _token["v"] and time.time() < _token["exp"]:
        return _token["v"]
    s = settings()
    if not is_configured():
        raise RuntimeError("未配置公众号：在「设置」里填写 AppID / AppSecret")
    try:
        d = _post_json(f"{API}/stable_token", {"grant_type": "client_credential", "appid": s["appid"], "secret": s["secret"]})
    except urllib.error.URLError as e:
        raise RuntimeError(f"连不上微信接口：{e}") from None
    _check(d, "获取 access_token ")
    _token.update(v=d["access_token"], exp=time.time() + int(d.get("expires_in", 7200)) - 300)
    return _token["v"]


def _shrink(path, max_bytes, max_w=1600):
    """WeChat limits: body images ≤1MB (jpg/png). Re-encode as JPEG if needed."""
    if os.path.getsize(path) <= max_bytes and path.lower().endswith((".jpg", ".jpeg", ".png")):
        return path
    from PIL import Image

    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    out = os.path.splitext(path)[0] + "_wx.jpg"
    q = 88
    while True:
        im.save(out, "JPEG", quality=q, optimize=True)
        if os.path.getsize(out) <= max_bytes or q <= 50:
            return out
        q -= 8


def upload_body_image(path):
    tok = access_token()
    d = _check(_post_file(f"{API}/media/uploadimg?access_token={tok}", _shrink(path, 1_000_000)), "上传正文图片")
    return d["url"]


def upload_cover(path):
    tok = access_token()
    d = _check(
        _post_file(f"{API}/material/add_material?access_token={tok}&type=image", _shrink(path, 2_000_000)),
        "上传封面",
    )
    return d["media_id"]


def add_draft(article):
    tok = access_token()
    d = _check(_post_json(f"{API}/draft/add?access_token={tok}", {"articles": [article]}), "存草稿")
    return d["media_id"]


# ---------------- inline-styled body ----------------
def _inline(t):
    t = html.escape(t)
    t = re.sub(r"\*\*([^*]+)\*\*", rf'<strong style="color:{ACCENT}">\1</strong>', t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r'<code style="background:#f6f2ee;padding:1px 5px;border-radius:3px">\1</code>', t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", t)  # 公众号正文外链不可点，保留文字
    return t


P = f'margin:0 0 20px;font-size:16px;line-height:1.9;color:#333;letter-spacing:.5px;text-align:justify;font-family:{FONT}'


def build_body(wechat_md, manifest, img_url, lead_title=""):
    """img_url(entry)->mmbiz url or None. Returns inline-styled HTML for WeChat."""
    by_raw = {m["raw"]: m for m in manifest}
    out, para, lst = [], [], []
    sec = 0

    def flush():
        if para:
            out.append(f'<p style="{P}">' + _inline("".join(x.strip() for x in para)) + "</p>")
            para.clear()
        if lst:
            items = "".join(
                f'<li style="margin:0 0 8px;font-size:16px;line-height:1.8;color:#333">{_inline(x)}</li>' for x in lst
            )
            out.append(f'<ul style="margin:0 0 20px;padding-left:22px">{items}</ul>')
            lst.clear()

    for line in (wechat_md or "").splitlines():
        s = line.strip()
        if "[CLOSE]" in s or "[/CLOSE]" in s:
            flush()
            s = s.replace("[CLOSE]", "").replace("[/CLOSE]", "").strip()
            if s:
                out.append(
                    f'<section style="margin:32px 0 20px;padding:18px 18px;background:#faf6f3;border-radius:8px;'
                    f'border-top:3px solid {ACCENT};font-size:16px;line-height:1.9;color:#333">{_inline(s)}</section>'
                )
            continue
        ph = re.match(r"^\[(FIGURE|MOOD|CHART):([^\]]*)\]\s*(.*)$", s)
        if ph:
            flush()
            m = by_raw.get(s) or next((x for x in manifest if x["raw"].startswith(s[: s.find("]") + 1])), None)
            url = img_url(m) if m and m.get("ok") else None
            cap = ph.group(3).strip()
            if url:
                out.append(
                    '<section style="margin:24px 0;text-align:center">'
                    f'<img src="{url}" style="width:100%;display:block;border-radius:6px">'
                    + (f'<p style="margin:8px 0 0;font-size:13px;color:#999;text-align:center">{html.escape(cap)}</p>' if cap else "")
                    + "</section>"
                )
            continue
        if s.startswith("## "):
            flush()
            sec += 1
            h = re.sub(r"^\s*(\d{1,2}(?:[.、)）]|\s)|[一二三四五六七八九十]+[、.])\s*", "", s[3:].strip())
            out.append(
                '<section style="margin:36px 0 18px">'
                f'<p style="margin:0;font-size:14px;font-weight:bold;color:{ACCENT};letter-spacing:2px">PART {sec:02d}</p>'
                f'<h2 style="margin:6px 0 0;padding-bottom:8px;font-size:20px;line-height:1.5;color:#1a1a1a;'
                f'border-bottom:2px solid {ACCENT};font-family:{FONT}">{_inline(h)}</h2></section>'
            )
            continue
        if s.startswith("### "):
            flush()
            out.append(f'<h3 style="margin:24px 0 12px;font-size:17px;color:#1a1a1a;border-left:4px solid {ACCENT};padding-left:10px">{_inline(s[4:])}</h3>')
            continue
        if s.startswith("# "):
            continue  # title goes into the draft title
        if s.startswith(">"):
            flush()
            out.append(
                f'<section style="margin:0 0 20px;padding:14px 16px;background:#faf6f3;border-left:4px solid {ACCENT};'
                f'font-size:15px;line-height:1.8;color:#555">{_inline(s.lstrip("> ").strip())}</section>'
            )
            continue
        if re.match(r"^([-*+]|\d+[.、)])\s+", s):
            if para:
                flush()
            lst.append(re.sub(r"^([-*+]|\d+[.、)])\s+", "", s))
            continue
        if s in ("---", "***"):
            flush()
            out.append('<p style="margin:28px 0;text-align:center;color:#ccc;letter-spacing:8px">· · ·</p>')
            continue
        if not s:
            flush()
            continue
        if lst:
            flush()
        if "不构成任何买卖推荐" in s or "不构成投资建议" in s:
            flush()
            out.append(f'<p style="margin:24px 0 0;font-size:12px;color:#aaa;text-align:center">{_inline(s)}</p>')
            continue
        para.append(s)
    flush()
    return f'<section style="padding:4px 2px;font-family:{FONT}">' + "".join(out) + "</section>"


# ---------------- cover ----------------
def make_cover(bg_path, title, out_path, brand=""):
    """900x383 (2.35:1) cover: photo + dark gradient + title in Microsoft YaHei."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    W, H = 1800, 766
    if bg_path and os.path.exists(bg_path):
        im = Image.open(bg_path).convert("RGB")
        r = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
        l, t = (im.width - W) // 2, (im.height - H) // 2
        im = im.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(1.2))
    else:
        im = Image.new("RGB", (W, H), "#2b2b2b")
    shade = Image.new("L", (W, 1))
    for x in range(W):
        shade.putpixel((x, 0), int(225 - 150 * x / W))
    im = Image.composite(Image.new("RGB", (W, H), "#0d0d0d"), im, shade.resize((W, H)))
    dr = ImageDraw.Draw(im)

    def font(size, bold=True):
        for f in (r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
                  r"C:\Windows\Fonts\msyh.ttc", "/System/Library/Fonts/PingFang.ttc"):
            if os.path.exists(f):
                return ImageFont.truetype(f, size)
        return ImageFont.load_default()

    # wrap title to max 2 lines, ~11 chars per line at 96px
    f_t = font(96)
    maxw = int(W * 0.66)
    lines, cur = [], ""
    for ch in title:
        if dr.textlength(cur + ch, font=f_t) > maxw:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    lines.append(cur)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1][:-1] + "…"
    y = (H - len(lines) * 128) // 2 + 10
    dr.rectangle([110, y - 52, 190, y - 40], fill=ACCENT)
    if brand:
        dr.text((210, y - 70), brand, font=font(40, False), fill="#e8e8e8")
    for ln in lines:
        dr.text((110, y), ln, font=f_t, fill="#ffffff")
        y += 128
    im.save(out_path, "JPEG", quality=90)
    return out_path


# ---------------- one call ----------------
def publish_draft(wechat_md, manifest, title, digest, cover_src, out_dir, logf=None):
    logf = logf or (lambda m: None)
    logf("获取公众号 access_token…")
    access_token()
    cache = {}

    def img_url(m):
        f = m.get("file")
        if not f or not os.path.exists(f):
            return None
        if f not in cache:
            logf(f"上传正文图：{os.path.basename(f)}")
            cache[f] = upload_body_image(f)
        return cache[f]

    content = build_body(wechat_md, manifest, img_url)
    cover = make_cover(cover_src, title, os.path.join(out_dir, "wx_cover.jpg"), brand=config.brand())
    logf("上传封面…")
    thumb = upload_cover(cover)
    article = {
        "article_type": "news",
        "title": title[:64],
        "author": settings()["author"][:16],
        "digest": (digest or "")[:110],
        "content": content,
        "thumb_media_id": thumb,
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
    }
    logf("写入草稿箱…")
    media_id = add_draft(article)
    with open(os.path.join(out_dir, "wx_content.html"), "w", encoding="utf-8") as f:
        f.write(content)
    return {"media_id": media_id, "cover": cover, "images": len(cache)}
