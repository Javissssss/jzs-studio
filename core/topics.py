# -*- coding: utf-8 -*-
"""Topic sourcing for jzs-studio.

Sources:
  weibo   - Weibo realtime hot search (official AJAX, keyless)
  toutiao - Toutiao hot board (official API, keyless)
  baidu   - Baidu realtime hot search (fallback)
  manual  - user pastes candidate topics
  direct  - user specifies one topic directly
"""

import json
import os
import sys
import urllib.request

from . import config

if config.SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, config.SCRIPTS_DIR)

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

NICHE_KEYWORDS = [
    "ai",
    "\u4eba\u5de5\u667a\u80fd",
    "\u5927\u6a21\u578b",
    "chatgpt",
    "deepseek",
    "\u6548\u7387",
    "\u5de5\u5177",
    "\u751f\u4ea7\u529b",
    "\u8d22\u7ecf",
    "\u7ecf\u6d4e",
    "\u6295\u8d44",
    "\u7406\u8d22",
    "\u7f8e\u80a1",
    "a\u80a1",
    "\u57fa\u91d1",
    "\u697c\u5e02",
    "\u623f\u4ef7",
    "\u5b8f\u89c2",
    "\u7f8e\u8054\u50a8",
    "\u5229\u7387",
    "\u6c47\u7387",
    "\u9ec4\u91d1",
    "\u56fd\u503a",
    "\u6536\u76ca\u7387",
    "\u901a\u8d39",
    "\u65b9\u6cd5\u8bba",
    "\u8ba4\u77e5",
    "\u6210\u957f",
    "\u4e60\u60ef",
    "\u51b3\u7b56",
    "\u65f6\u95f4\u7ba1\u7406",
    "\u526f\u4e1a",
    "\u8d5a\u9322",
]

# ── Weibo ──────────────────────────────────────────────────────────────────
WEIBO_URL = "https://weibo.com/ajax/side/hotSearch"
WEIBO_HEADERS = {**UA, "Referer": "https://weibo.com/"}


def fetch_weibo_hot(limit=50, timeout=10):
    req = urllib.request.Request(WEIBO_URL, headers=WEIBO_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    realtime = data.get("data", {}).get("realtime", [])
    items = []
    for rank, it in enumerate(realtime[:limit], 1):
        title = (it.get("word") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": (it.get("note") or "").strip(),
                "source": "\u5fae\u535a\u70ed\u641c",
                "link": f"https://s.weibo.com/weibo?q=%23{urllib.request.quote(title)}%23",
                "rank": rank,
                "heat": str(it.get("num") or ""),
            }
        )
    return items


# ── Toutiao ────────────────────────────────────────────────────────────────
TOUTIAO_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
TOUTIAO_HEADERS = {**UA, "Referer": "https://www.toutiao.com/"}


def fetch_toutiao_hot(limit=50, timeout=10):
    req = urllib.request.Request(TOUTIAO_URL, headers=TOUTIAO_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    raw = data.get("data", [])
    items = []
    for rank, it in enumerate(raw[:limit], 1):
        title = (it.get("Title") or it.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": (it.get("Abstract") or it.get("abstract") or "").strip(),
                "source": "\u5934\u6761\u70ed\u699c",
                "link": it.get("Url") or it.get("url") or "",
                "rank": rank,
                "heat": str(it.get("HotValue") or it.get("hotValue") or ""),
            }
        )
    return items


# ── Baidu (fallback) ───────────────────────────────────────────────────────
BAIDU_URL = "https://top.baidu.com/api/board?platform=wise&tab=realtime"


def fetch_baidu_hot(limit=50, timeout=10):
    req = urllib.request.Request(BAIDU_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    raw = []
    try:
        cards = data["data"]["cards"]
        for card in cards:
            for c1 in card.get("content", []):
                inner = c1.get("content") if isinstance(c1, dict) else None
                if isinstance(inner, list):
                    raw.extend(inner)
                elif isinstance(c1, dict) and ("word" in c1 or "query" in c1):
                    raw.append(c1)
    except (KeyError, TypeError, IndexError):
        raw = []
    items = []
    for rank, it in enumerate(raw[:limit], 1):
        if not isinstance(it, dict):
            continue
        title = it.get("word") or it.get("query") or ""
        if not title:
            continue
        items.append(
            {
                "title": title.strip(),
                "summary": (it.get("desc") or "").strip(),
                "source": "\u767e\u5ea6\u70ed\u641c",
                "link": it.get("url") or "",
                "rank": rank,
                "heat": str(it.get("hotScore") or ""),
            }
        )
    return items


# ── Manual / Direct ────────────────────────────────────────────────────────
def parse_manual(text):
    items = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        sep = "|" if "|" in line else ("\t" if "\t" in line else None)
        if sep:
            parts = [p.strip() for p in line.split(sep, 1)]
            title, summary = parts[0], (parts[1] if len(parts) > 1 else "")
        else:
            title, summary = line, ""
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": summary,
                "source": "\u624b\u52a8\u8f93\u5165",
                "link": "",
                "rank": i,
                "heat": "",
            }
        )
    return items


def make_direct(title, summary=""):
    return [
        {
            "title": title.strip(),
            "summary": summary.strip(),
            "source": "\u76f4\u63a5\u6307\u5b9a",
            "link": "",
            "rank": 1,
            "heat": "",
        }
    ]


# ── Scoring ────────────────────────────────────────────────────────────────
def niche_match(title, summary=""):
    text = (title + " " + summary).lower()
    return sum(1 for kw in NICHE_KEYWORDS if kw in text)


def score_items(items, extra_keywords=None, min_score=0):
    """Score via filter_topics.TopicFilter. min_score=0 keeps all items."""
    import filter_topics

    keywords = list(NICHE_KEYWORDS)
    if extra_keywords:
        keywords = extra_keywords + keywords
    tf = filter_topics.TopicFilter(keywords)
    result = tf.filter_topics(items, min_score)
    scored = result["all_items"]
    out = []
    for s in scored:
        orig = s.get("original_item", {})
        out.append(
            {
                "title": s.get("title", ""),
                "summary": orig.get("summary", ""),
                "source": s.get("source", ""),
                "link": s.get("link", ""),
                "rank": orig.get("rank", 999),
                "heat": orig.get("heat", ""),
                "total_score": s.get("total_score", 0),
                "scores": s.get("scores", {}),
                "recommend": s.get("recommend", False),
                "niche_hits": niche_match(s.get("title", ""), orig.get("summary", "")),
            }
        )
    out.sort(key=lambda x: (x["niche_hits"], x["total_score"]), reverse=True)
    return out


def fetch_and_score(
    mode="weibo",
    text="",
    title="",
    summary="",
    extra_keywords=None,
    limit=50,
    min_score=0,
):
    """Unified entry. mode: weibo | toutiao | baidu | manual | direct"""
    if mode == "weibo":
        items = fetch_weibo_hot(limit=limit)
    elif mode == "toutiao":
        items = fetch_toutiao_hot(limit=limit)
    elif mode == "baidu":
        items = fetch_baidu_hot(limit=limit)
    elif mode == "manual":
        items = parse_manual(text)
    elif mode == "direct":
        items = make_direct(title, summary)
    else:
        raise ValueError(f"unknown mode: {mode}")
    if not items:
        return {"items": [], "scored": [], "error": "no items gathered"}
    scored = score_items(items, extra_keywords=extra_keywords, min_score=min_score)
    return {"items": items, "scored": scored, "error": None}
