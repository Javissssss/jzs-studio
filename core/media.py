# -*- coding: utf-8 -*-
"""Media generation: turn draft placeholders into real images.

Placeholder types in wechat draft:
  [FIGURE:id] caption  -> framework card via figure_cards.py (data from FIGURES block)
  [MOOD:query] caption -> atmosphere photo via search_images.py (Pexels)
  [CHART:id] caption   -> data chart via embedded SVG template + playwright
"""

import html
import json
import os
import re
import subprocess
import sys
import tempfile

from . import config

PLACEHOLDER_RE = re.compile(r"\[(FIGURE|MOOD|CHART):([^\]]+)\]\s*([^\n]*)")


def parse_placeholders(wechat_md):
    """Return ordered list of placeholders: {type,key,caption,raw}."""
    out = []
    for m in PLACEHOLDER_RE.finditer(wechat_md or ""):
        out.append(
            {
                "type": m.group(1),
                "key": m.group(2).strip(),
                "caption": m.group(3).strip(),
                "raw": m.group(0),
            }
        )
    return out


def _run_script(script_name, args, timeout=180):
    """Run a skill script via subprocess, return (ok, stdout, stderr)."""
    script = os.path.join(config.SCRIPTS_DIR, script_name)
    cmd = [config.PYTHON, script] + args
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return p.returncode == 0, p.stdout or "", p.stderr or ""
    except Exception as e:
        return False, "", str(e)


def gen_figure(fig, out_dir, idx):
    """Render one framework figure. fig={id,kind,caption,data}."""
    kind = fig.get("kind", "flow")
    if kind not in ("flow", "compare", "checklist", "timeline", "mindmap"):
        kind = "mindmap" if fig.get("data", {}).get("branches") else "flow"
    data = fig.get("data") or {}
    if not data.get("title"):
        data["title"] = fig.get("caption", "")[:20] or "要点"
    # write data json to temp
    fd, data_path = tempfile.mkstemp(suffix=".json", prefix="jzs_fig_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    out_png = os.path.join(out_dir, f"fig_{fig.get('id', idx):0>2}.png")
    ok, so, se = _run_script(
        "figure_cards.py", ["--kind", kind, "--data", data_path, "--out", out_png]
    )
    try:
        os.remove(data_path)
    except OSError:
        pass
    return {"ok": ok, "file": out_png if ok else None, "log": (se or so).strip()[-300:]}


def gen_mood(query, out_dir, idx):
    """Fetch one atmosphere image via search_images.py (Pexels chain)."""
    prefix = f"mood_{idx:02d}"
    ok, so, se = _run_script(
        "search_images.py",
        ["--query", query, "--count", "1", "--out", out_dir, "--prefix", prefix],
    )
    file = None
    if ok:
        # find downloaded file
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            cand = os.path.join(out_dir, prefix + "_01" + ext)
            if os.path.exists(cand):
                file = cand
                break
    return {
        "ok": ok and file is not None,
        "file": file,
        "log": (se or so).strip()[-300:],
    }


# ---- Chart rendering (embedded SVG template, brick-red/rice-white) ----
CHART_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
:root{{--bg:#FAF9F5;--fg:#141413;--muted:#87867F;--border:#E3DACC;--accent:#C96442;--accent-d:#B04A3F}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);font-family:"Microsoft YaHei","微软雅黑","PingFang SC",sans-serif;color:var(--fg)}}
#figure{{width:{width}px;background:var(--bg);padding:36px 40px 30px}}
.ct{{font-family:"Microsoft YaHei","微软雅黑","PingFang SC",sans-serif;font-size:26px;font-weight:700;margin-bottom:6px}}
.cs{{font-size:15px;color:var(--muted);margin-bottom:26px}}
svg{{display:block}}
.axis{{stroke:var(--border);stroke-width:1}}
.grid{{stroke:var(--border);stroke-width:1;stroke-dasharray:3 4;opacity:.6}}
.bar{{fill:var(--accent)}}
.bar:last-child{{fill:var(--accent-d)}}
.line{{fill:none;stroke:var(--accent);stroke-width:3}}
.dot{{fill:var(--accent-d)}}
.lbl{{font-size:13px;fill:var(--muted);font-family:ui-monospace,Consolas,monospace}}
.val{{font-size:13px;fill:var(--accent-d);font-weight:700}}
.area{{fill:var(--accent);opacity:.10}}
</style></head><body><div id="figure">
<div class="ct">{title}</div><div class="cs">{subtitle}</div>
{svg}
</div></body></html>"""


def _chart_svg(ctype, data, width=900, height=420):
    """Build inline SVG for line/bar/column chart from data [{time,value}] or [{category,value}]."""
    pad_l, pad_r, pad_t, pad_b = 60, 30, 20, 50
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    vals = [float(d.get("value", 0)) for d in data] or [0]
    labels = [str(d.get("time") or d.get("category") or "") for d in data]
    vmax, vmin = max(vals), min(vals)
    if ctype in ("bar", "column") and vmin > 0:
        vmin = 0  # bars must start at zero, otherwise heights lie
    if vmax == vmin:
        vmax = vmin + 1
    span = vmax - vmin
    n = len(data)
    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    # gridlines + y labels
    for g in range(5):
        y = pad_t + ih * g / 4
        gv = vmax - span * g / 4
        parts.append(
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + iw}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="lbl" x="{pad_l - 10}" y="{y + 4:.1f}" text-anchor="end">{gv:.{0 if span >= 8 else 1}f}</text>'
        )
    parts.append(
        f'<line class="axis" x1="{pad_l}" y1="{pad_t + ih}" x2="{pad_l + iw}" y2="{pad_t + ih}"/>'
    )

    def xpos(i):
        return pad_l + (iw * (i + 0.5) / n)

    def ypos(v):
        return pad_t + ih * (1 - (float(v) - vmin) / span)

    if ctype in ("line", "area"):
        pts = [(xpos(i), ypos(v)) for i, v in enumerate(vals)]
        if ctype == "area":
            poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(
                f'<polygon class="area" points="{pad_l},{pad_t + ih} {poly} {pad_l + iw},{pad_t + ih}"/>'
            )
        path = " ".join(
            ("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
            for i, (x, y) in enumerate(pts)
        )
        parts.append(f'<path class="line" d="{path}"/>')
        for x, y in pts:
            parts.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4"/>')
    else:  # bar / column
        bw = iw / n * 0.6
        for i, v in enumerate(vals):
            x = xpos(i) - bw / 2
            y = ypos(v)
            h = pad_t + ih - y
            parts.append(
                f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3"/>'
            )
            parts.append(
                f'<text class="val" x="{xpos(i):.1f}" y="{y - 6:.1f}" text-anchor="middle">{v:g}</text>'
            )
    # x labels
    for i, lb in enumerate(labels):
        parts.append(
            f'<text class="lbl" x="{xpos(i):.1f}" y="{pad_t + ih + 24:.1f}" text-anchor="middle">{html.escape(lb[: max(6, int(iw / n / 15))])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def gen_chart(chart, out_dir, idx):
    """Render a data chart to PNG via embedded SVG template + playwright."""
    ctype = chart.get("type", "column")
    if ctype not in ("line", "bar", "column", "area"):
        ctype = "column"
    data = chart.get("data") or []
    if not data:
        return {"ok": False, "file": None, "log": "empty chart data"}
    width = 980
    svg = _chart_svg(ctype, data, width=width, height=420)
    html = CHART_HTML.format(
        width=width,
        title=chart.get("title") or chart.get("caption", "数据"),
        subtitle=chart.get("subtitle", ""),
        svg=svg,
    )
    fd, html_path = tempfile.mkstemp(suffix=".html", prefix="jzs_chart_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    out_png = os.path.join(out_dir, f"chart_{chart.get('id', idx):0>2}.png")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "file": None, "log": "playwright not installed"}
    try:
        url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            pg = b.new_page(
                viewport={"width": width, "height": 560}, device_scale_factor=2
            )
            pg.goto(url, timeout=15000)
            pg.wait_for_load_state("domcontentloaded", timeout=10000)
            el = pg.query_selector("#figure")
            if el:
                el.screenshot(path=out_png)
            else:
                pg.screenshot(path=out_png)
            b.close()
        return {"ok": True, "file": out_png, "log": ""}
    except Exception as e:
        return {"ok": False, "file": None, "log": str(e)[:300]}
    finally:
        try:
            os.remove(html_path)
        except OSError:
            pass


def gen_ai_image(entry, out_dir, idx, title=""):
    """MOOD/any slot -> AI image via OpenAI-compatible images API."""
    from . import imagegen

    try:
        f = imagegen.generate(imagegen.build_prompt(entry, title), os.path.join(out_dir, f"ai_{idx:02d}"))
        return {"ok": True, "file": f, "log": "", "engine": "ai"}
    except RuntimeError as e:
        return {"ok": False, "file": None, "log": str(e)[:300], "engine": "ai"}


def screenshot_html(html_path, out_png, width=1080):
    """Screenshot #figure (or whole page) of a local html file."""
    from playwright.sync_api import sync_playwright

    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        pg = b.new_page(viewport={"width": width, "height": 800}, device_scale_factor=2)
        pg.goto(url, timeout=20000)
        pg.wait_for_load_state("networkidle", timeout=15000)
        el = pg.query_selector("#figure")
        (el or pg).screenshot(path=out_png, **({} if el else {"full_page": True}))
        b.close()
    return out_png


ENGINES = ("stock", "ai")  # per-run engine for MOOD slots; codex handled in app


def generate_media(pid, wechat_md, figures=None, charts=None, mood_engine="stock",
                   title="", keep=None, logf=None):
    """Generate all media for a draft. Returns manifest list aligned to placeholders.
    keep: {placeholder raw text: entry} manually supplied images to preserve."""
    logf = logf or (lambda m: None)
    keep = keep or {}
    figures = figures or []
    charts = charts or []
    fig_by_id = {str(f.get("id")): f for f in figures}
    chart_by_id = {str(c.get("id")): c for c in charts}
    out_dir = os.path.join(config.project_dir(pid), "output")
    os.makedirs(out_dir, exist_ok=True)

    placeholders = parse_placeholders(wechat_md)
    manifest = []
    mood_n = 0
    for i, ph in enumerate(placeholders, 1):
        entry = {
            "raw": ph["raw"],
            "type": ph["type"],
            "key": ph["key"],
            "caption": ph["caption"],
            "file": None,
            "ok": False,
            "log": "",
        }
        logf(f"[{i}/{len(placeholders)}] {ph['type']} {ph['caption'] or ph['key']}")
        kept = keep.get(ph["raw"])
        if kept and kept.get("file") and os.path.exists(kept["file"]):
            entry.update({"ok": True, "file": kept["file"], "engine": kept.get("engine", "manual"), "log": ""})
            manifest.append(entry)
            continue
        if ph["type"] == "FIGURE":
            fig = fig_by_id.get(ph["key"]) or (
                figures[i - 1] if i - 1 < len(figures) else None
            )
            if fig:
                r = gen_figure(fig, out_dir, i)
                entry.update(r)
            else:
                entry["log"] = f"no figure data for id={ph['key']}"
        elif ph["type"] == "MOOD":
            mood_n += 1
            if mood_engine == "ai":
                entry.update(gen_ai_image(entry, out_dir, i, title))
            else:
                entry.update(gen_mood(ph["key"], out_dir, mood_n))
                entry.setdefault("engine", "stock")
        elif ph["type"] == "CHART":
            ch = chart_by_id.get(ph["key"]) or (
                charts[i - 1] if i - 1 < len(charts) else None
            )
            if ch:
                r = gen_chart(ch, out_dir, i)
                entry.update(r)
            else:
                entry["log"] = f"no chart data for id={ph['key']}"
        entry.setdefault("engine", "template")
        if not entry["ok"]:
            logf(f"  ✗ {entry['log'][:120]}")
        manifest.append(entry)
    return manifest
