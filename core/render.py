# -*- coding: utf-8 -*-
"""WeChat HTML renderer: draft markdown + media manifest -> self-contained HTML.
Zero-dependency minimal markdown converter (article subset). Reuses the skill
template's <style> block so design stays in sync."""

import html
import os
import re
import time

from . import config

PLACEHOLDER_RE = re.compile(r"\[(FIGURE|MOOD|CHART):([^\]]+)\]\s*([^\n]*)")


def _read_template_style():
    """Extract <style>...</style> from wechat_template.html."""
    path = os.path.join(config.TEMPLATES_DIR, "wechat_template.html")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        tpl = f.read()
    m = re.search(r"<style>(.*?)</style>", tpl, re.DOTALL)
    return m.group(1) if m else ""


def inline_md(text):
    """Convert inline markdown: bold, italic, code, links. Input is raw text."""
    t = html.escape(text)
    # images inline ![alt](url) - rare in body, skip
    # links [text](url)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2" target="_blank" style="color:var(--accent-d)">\1</a>',
        t,
    )
    # bold **x**
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    # italic *x* (avoid touching **)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    # inline code `x`
    t = re.sub(
        r"`([^`]+)`",
        r'<code style="background:#fff;border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-family:ui-monospace,Consolas,monospace;font-size:14px">\1</code>',
        t,
    )
    return t


def _build_figure_html(src, caption):
    rel = os.path.basename(src) if src else ""
    if not src:
        return f"<figure><figcaption>{html.escape(caption)}（配图生成失败）</figcaption></figure>"
    return (
        f"<figure>"
        f'<a href="{rel}" data-lightbox="article" data-caption="{html.escape(caption)}" target="_blank">'
        f'<img src="{rel}" alt="{html.escape(caption)}" loading="lazy">'
        f"</a>"
        f"<figcaption>{html.escape(caption)}</figcaption></figure>"
    )


def render_article(wechat_md, manifest, topic=None, column=None):
    """Render full wechat HTML. manifest = list from media.generate_media (ordered)."""
    topic = topic or {}
    column = column or config.brand()
    wechat_md = wechat_md or ""

    # Build placeholder -> file queue (consume in order of appearance)
    file_queue = {}
    for m in manifest:
        k = (m.get("type"), m.get("key"))
        file_queue.setdefault(k, []).append(m.get("file"))

    lines = wechat_md.splitlines()
    title = topic.get("title", "未命名文章")
    lead = ""
    sections = []  # list of {heading, blocks:[html]}
    close_html = ""
    cur = None
    lead_buf = []
    in_close = False
    close_buf = []
    para_buf = []
    list_buf = None  # ('ul'|'ol', [items])

    def flush_para():
        nonlocal para_buf
        txt = _join_lines(para_buf)
        para_buf = []
        return "<p>" + inline_md(txt) + "</p>" if txt else ""

    def flush_list():
        nonlocal list_buf
        if not list_buf:
            return ""
        kind, items = list_buf
        tag = "ul" if kind == "ul" else "ol"
        out = f'<{tag} style="margin:0 0 20px 24px;line-height:1.9">'
        for it in items:
            out += f"<li>{inline_md(it)}</li>"
        out += f"</{tag}>"
        list_buf = None
        return out

    def emit(block_html):
        nonlocal cur, lead_buf
        if not block_html:
            return
        if in_close:
            close_buf.append(block_html)
        elif cur is not None:
            cur["blocks"].append(block_html)
        else:
            lead_buf.append(block_html)

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # [CLOSE] ... [/CLOSE] : accumulate RAW text into close_buf
        if "[CLOSE]" in stripped:
            # flush pending paragraph/list to the current section first
            emit(flush_para())
            emit(flush_list())
            in_close = True
            after = stripped.split("[CLOSE]", 1)[1]
            if after.strip():
                close_buf.append(after.strip())
            i += 1
            continue
        if "[/CLOSE]" in stripped:
            before = stripped.split("[/CLOSE]", 1)[0]
            if before.strip():
                close_buf.append(before.strip())
            in_close = False
            i += 1
            continue
        if in_close:
            # inside close block: collect raw lines, bypass normal parsing
            if stripped:
                close_buf.append(stripped)
            i += 1
            continue

        # blank line
        if not stripped:
            emit(flush_para())
            emit(flush_list())
            i += 1
            continue

        # H1 title
        if stripped.startswith("# ") and not stripped.startswith("## "):
            emit(flush_para())
            emit(flush_list())
            t = stripped[2:].strip()
            if t and title in ("未命名文章", "", None):
                title = t
            elif t and not topic.get("title"):
                title = t
            i += 1
            continue

        # H2 section
        if stripped.startswith("## "):
            emit(flush_para())
            emit(flush_list())
            heading = stripped[3:].strip()
            # strip leading numbering like "01 " or "一、"
            cur = {"heading": heading, "blocks": []}
            sections.append(cur)
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            emit(flush_para())
            emit(flush_list())
            emit(
                '<h3 style="font-size:20px;font-weight:700;margin:28px 0 14px">'
                + inline_md(stripped[4:].strip())
                + "</h3>"
            )
            i += 1
            continue

        # blockquote -> pull card
        if stripped.startswith(">"):
            emit(flush_para())
            emit(flush_list())
            qtext = stripped.lstrip(">").strip()
            # gather multi-line quote
            j = i + 1
            while j < n and lines[j].strip().startswith(">"):
                qtext += " " + lines[j].strip().lstrip(">").strip()
                j += 1
            if in_close:
                close_buf.append(qtext)
            else:
                emit(f'<div class="pull">{inline_md(qtext)}</div>')
            i = j
            continue

        # placeholder line (FIGURE/MOOD/CHART)
        pm = PLACEHOLDER_RE.match(stripped)
        if pm:
            emit(flush_para())
            emit(flush_list())
            ptype, pkey, pcap = pm.group(1), pm.group(2).strip(), pm.group(3).strip()
            q = file_queue.get((ptype, pkey))
            src = q.pop(0) if q else None
            emit(_build_figure_html(src, pcap))
            i += 1
            continue

        # unordered list
        if re.match(r"^[-*+]\s+", stripped):
            emit(flush_para())
            if list_buf is None or list_buf[0] != "ul":
                emit(flush_list())
                list_buf = ("ul", [])
            list_buf[1].append(re.sub(r"^[-*+]\s+", "", stripped))
            i += 1
            continue

        # ordered list
        if re.match(r"^\d+\.\s+", stripped):
            emit(flush_para())
            if list_buf is None or list_buf[0] != "ol":
                emit(flush_list())
                list_buf = ("ol", [])
            list_buf[1].append(re.sub(r"^\d+\.\s+", "", stripped))
            i += 1
            continue

        # horizontal rule
        if stripped in ("---", "***", "___"):
            emit(flush_para())
            emit(flush_list())
            i += 1
            continue

        # normal paragraph text
        para_buf.append(stripped)
        i += 1

    # final flush
    emit(flush_para())
    emit(flush_list())

    # lead = first lead_buf paragraph text (strip tags) for hero subtitle
    # (skip figure/image blocks so a cover caption never becomes the subtitle)
    for blk in lead_buf:
        if blk.startswith("<p>"):
            lead = re.sub(r"<[^>]+>", "", blk)[:80]
            break

    # word count
    body_text = re.sub(r"\[[^\]]*\]|[<>]", "", re.sub(r"<[^>]+>", "", wechat_md))
    word_count = len(re.sub(r"\s", "", body_text))
    read_min = max(1, round(word_count / 400))

    # assemble HTML
    style = _read_template_style()
    # format numbers only: strftime with CJK crashes on non-Chinese Windows locales
    t = time.localtime()
    today = f"{t.tm_year}年{t.tm_mon:02d}月{t.tm_mday:02d}日"
    parts = []
    parts.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
    parts.append(
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
    )
    parts.append(
        f'<title>{html.escape(title)}</title><style>{style}</style></head><body><div class="wrap">'
    )
    # hero
    parts.append('<div class="hero">')
    parts.append(f'<div class="eyebrow">{html.escape(column)} · {today}</div>')
    parts.append(f"<h1>{html.escape(title)}</h1>")
    if lead:
        parts.append(f'<p class="lead">{html.escape(lead)}</p>')
    parts.append(f'<div class="meta">约{word_count}字 · 读完{read_min}分钟</div>')
    parts.append("</div>")
    # toc
    if sections:
        parts.append('<nav class="toc"><b>目录</b>')
        for idx, s in enumerate(sections, 1):
            parts.append(
                f'<a href="#s{idx}">{idx:02d} {html.escape(_clean_heading(s["heading"]))}</a>'
            )
        parts.append("</nav>")
    # lead paragraphs (before first H2)
    if lead_buf:
        parts.append('<section id="s0">' + "".join(lead_buf) + "</section>")
    # sections
    for idx, s in enumerate(sections, 1):
        heading = _clean_heading(s["heading"])
        parts.append(f'<section id="s{idx}">')
        parts.append(
            f'<h2><span class="sec-num">{idx:02d}</span>{html.escape(heading)}</h2>'
        )
        parts.append("".join(s["blocks"]))
        parts.append("</section>")
    # close
    if close_buf:
        ctext = "<br>".join(inline_md(c) for c in close_buf)
        parts.append(f'<div class="close"><p>{ctext}</p></div>')
    # footer
    src_note = topic.get("source", "")
    parts.append("<footer>")
    if src_note:
        parts.append(f"选题来源：{html.escape(src_note)}<br>")
    parts.append("配图：Pexels/Unsplash/Openverse 免版权素材 + 自制框架图<br>")
    finance = config.is_finance(title + " " + topic.get("summary", ""))
    if finance:
        parts.append(f"免责声明：{config.FINANCE_DISCLAIMER}")
    parts.append("</footer>")
    # lightbox overlay (self-contained, no external deps)
    parts.append("""
<div id="lb" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;align-items:center;justify-content:center;flex-direction:column;gap:12px;cursor:zoom-out" onclick="this.style.display='none'">
  <img id="lb-img" style="max-width:92vw;max-height:85vh;border-radius:6px;object-fit:contain;box-shadow:0 8px 40px rgba(0,0,0,.6)">
  <div id="lb-cap" style="color:rgba(255,255,255,.75);font-size:13px;max-width:80vw;text-align:center"></div>
</div>
<script>
document.querySelectorAll('a[data-lightbox]').forEach(function(a){
  a.addEventListener('click',function(e){
    e.preventDefault();
    var lb=document.getElementById('lb');
    document.getElementById('lb-img').src=a.href;
    document.getElementById('lb-cap').textContent=a.dataset.caption||'';
    lb.style.display='flex';
  });
});
</script>
""")
    parts.append("</div></body></html>")
    out_html = "".join(parts)
    return out_html, {
        "images": out_html.count('<img src="'),
        "missing_images": out_html.count("（配图生成失败）"),
        "title": title,
        "lead": lead,
        "word_count": word_count,
        "read_min": read_min,
        "sections": len(sections),
        "finance": finance,
        "has_close": bool(close_buf),
    }


def _join_lines(lines):
    """Join soft-wrapped lines: no space between CJK, one space between Latin words."""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and out[-1].isascii() and out[-1].isalnum() and ln[0].isascii() and ln[0].isalnum():
            out += " "
        out += ln
    return out


def _clean_heading(h):
    """Strip leading numbering like '01 ', '一、', '1. ' from a heading."""
    h = re.sub(r"^\s*\d+[\.、\)）]\s*", "", h)
    h = re.sub(r"^\s*[一二三四五六七八九十]+[、\.]\s*", "", h)
    return h.strip()


def inline_images(html_str, base_dir, max_w=1280):
    """Embed every relative <img src> as a data URI so the file opens anywhere
    (sent over IM, opened on another computer). Big photos are downscaled to
    max_w and re-encoded as JPEG to keep the file small."""
    import base64
    import io
    import mimetypes

    def repl(m):
        src = m.group(2)
        if src.startswith(("data:", "http://", "https://", "//")):
            return m.group(0)
        path = os.path.join(base_dir, src.split("?")[0])
        if not os.path.isfile(path):
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as fh:
            data = fh.read()
        try:
            from PIL import Image

            im = Image.open(io.BytesIO(data))
            if im.width > max_w:
                im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
                buf = io.BytesIO()
                if mime == "image/png" and im.mode in ("RGBA", "LA", "P"):
                    im.save(buf, "PNG", optimize=True)
                else:
                    im.convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
                    mime = "image/jpeg"
                data = buf.getvalue()
        except Exception:
            pass
        return f'{m.group(1)}data:{mime};base64,{base64.b64encode(data).decode()}{m.group(3)}'

    return re.sub(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', repl, html_str)


def save_html(pid, html_str, title="article"):
    """Write two files: the working copy (relative image paths, used by the
    workbench preview and copy-to-WeChat) and a self-contained single file
    for sharing / opening on any computer."""
    out_dir = os.path.join(config.project_dir(pid), "output")
    os.makedirs(out_dir, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fff-]", "", title)[:30] or "article"
    path = os.path.join(out_dir, f"公众号_{safe}_终版.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_str)
    with open(single_file_path(path), "w", encoding="utf-8") as f:
        f.write(inline_images(html_str, out_dir))
    return path


def single_file_path(html_path):
    return html_path[: -len(".html")] + "_单文件.html"
