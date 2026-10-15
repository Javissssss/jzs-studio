# -*- coding: utf-8 -*-
"""Placeholder enrichment: make sure every draft gets images, even when the AI
forgot to write placeholders. Pure function, no I/O — easy to test.

Rules (only fill gaps, never duplicate what the AI already wrote):
  1. No MOOD at all      -> cover MOOD at top + up to 2 section MOODs
  2. FIGURE data unused  -> insert after H2 headings in order (one per section)
  3. CHART data unused   -> insert after the following H2s / before [CLOSE]
"""

import re

from . import config

PH_RE = re.compile(r"\[(FIGURE|MOOD|CHART):([^\]]+)\]")

# Chinese keyword -> English Pexels query (cover image)
COVER_QUERIES = [
    (("ai", "人工智能", "大模型", "chatgpt", "deepseek"), "artificial intelligence technology"),
    (("股", "基金", "美联储", "利率", "国债", "黄金"), "stock market trading screen"),
    (("经济", "财经", "通胀", "汇率"), "economy finance business"),
    (("房", "楼市"), "real estate city skyline"),
    (("教育", "学习", "考试"), "education learning classroom"),
    (("健康", "医疗"), "health wellness lifestyle"),
    (("职场", "效率", "工作"), "workplace office productivity"),
    (("创业", "副业", "赚钱"), "startup entrepreneurship office"),
    (("科技", "芯片", "手机"), "technology innovation digital"),
]
DEFAULT_COVER = "modern knowledge concept abstract"
SECTION_QUERIES = [
    "office desk productivity focus",
    "people discussing idea meeting",
    "data analysis visualization chart",
    "notebook writing inspiration",
]
MAX_SECTION_MOODS = 2


def cover_query(topic_title):
    t = (topic_title or "").lower()
    if config.is_finance(t) and not any(k in t for k in ("ai", "人工智能", "大模型")):
        return "stock market trading screen"
    for kws, q in COVER_QUERIES:
        if any(k in t for k in kws):
            return q
    return DEFAULT_COVER


def ensure_placeholders(wechat_md, topic_title="", figures=None, charts=None):
    """Return (new_md, report). report = {"mood": n, "figure": n, "chart": n} inserted."""
    figures = figures or []
    charts = charts or []
    md = wechat_md or ""
    existing = PH_RE.findall(md)
    used_keys = {(t, k.strip()) for t, k in existing}
    has_mood = any(t == "MOOD" for t, _ in existing)

    pending_figs = [
        (str(f.get("id") or f"f{i}"), f.get("caption") or "框架图")
        for i, f in enumerate(figures, 1)
        if ("FIGURE", str(f.get("id") or f"f{i}")) not in used_keys
    ]
    pending_charts = [
        (str(c.get("id") or f"c{i}"), c.get("caption") or "数据图")
        for i, c in enumerate(charts, 1)
        if ("CHART", str(c.get("id") or f"c{i}")) not in used_keys
    ]
    report = {"mood": 0, "figure": 0, "chart": 0}

    out = []
    if not has_mood:
        out += [f"[MOOD:{cover_query(topic_title)}] 封面配图", ""]
        report["mood"] += 1

    h2 = 0
    section_moods = 0
    for line in md.splitlines():
        s = line.strip()
        # leftovers go right before the closing block
        if "[CLOSE]" in s:
            out += _flush(pending_figs, "FIGURE", report)
            out += _flush(pending_charts, "CHART", report)
        out.append(line)
        if not s.startswith("## "):
            continue
        h2 += 1
        if pending_figs:
            fid, cap = pending_figs.pop(0)
            out += ["", f"[FIGURE:{fid}] {cap}", ""]
            report["figure"] += 1
        elif pending_charts:
            cid, cap = pending_charts.pop(0)
            out += ["", f"[CHART:{cid}] {cap}", ""]
            report["chart"] += 1
        elif not has_mood and h2 >= 2 and section_moods < MAX_SECTION_MOODS:
            q = SECTION_QUERIES[section_moods % len(SECTION_QUERIES)]
            out += ["", f"[MOOD:{q}] 配图", ""]
            section_moods += 1
            report["mood"] += 1

    out += _flush(pending_figs, "FIGURE", report)
    out += _flush(pending_charts, "CHART", report)
    return "\n".join(out), report


def _flush(pending, kind, report):
    lines = []
    while pending:
        key, cap = pending.pop(0)
        lines += ["", f"[{kind}:{key}] {cap}", ""]
        report[kind.lower()] += 1
    return lines
