# -*- coding: utf-8 -*-
"""Writing perspectives ("视角"): optional thinking-framework packs, e.g. the
bundled 复杂系统专家 (complexity) pack.

Off by default. The user decides per article whether to use it and how much:

  level "off"      not used
  level "concept"  only when the article explains a concept/mechanism: use the
                   framework for those paragraphs (at most N), rest of the
                   article keeps the channel's own voice   <- recommended
  level "full"     whole article written through the framework

Plus a paragraph-level tool: explain_concept(term) rewrites ONE concept
explanation with the framework, which the editor inserts where the cursor is.

Portability: the framework pack is bundled at <repo>/perspectives/<key>/ so a
fresh clone on another computer works. A locally installed newer copy (Hermes
skills dir, or JZS_PERSPECTIVE_DIR) wins if present. The macro-data key is read
from env ATTRACTOR_API_KEY (settings page) — never committed.
"""

import os
import re
import subprocess
import sys

from . import config

PERSPECTIVES = {
    "complexity": {
        "name": "复杂系统专家",
        "slug": "shifenxiyin-perspective",
        "dir": "complexity",
        "concept_sections": ["核心心智模型", "表达风格"],
        "full_sections": ["输出规范", "核心心智模型", "决策启发式", "表达风格"],
        "macro_script": "macro_latest.py",
    },
}
DEFAULT = "complexity"
LEVELS = ("off", "concept", "full")
BUNDLED_ROOT = os.path.join(config.PRODUCT_ROOT, "perspectives")

# topic keywords -> macro indicators to pull (names understood by macro_latest.py)
MACRO_RULES = [
    (r"美联储|加息|降息|美债|美元|联储|FOMC|鲍威尔|沃什",
     ["美国-货币政策倾向", "美国-资金利率", "美国-物价", "美国-信用环境",
      "全球-美元流动性", "美国-消费就业周期", "全球-风险偏好指数", "新兴市场外部金融条件"]),
    (r"A股|人民币|央行|社融|中国经济|降准|LPR",
     ["中国-货币政策倾向", "中国-流动性", "中国-信用环境", "中国-物价",
      "中国-总需求", "中国-市场风险偏好", "中国-外部金融条件"]),
    (r"通胀|CPI|物价|油价",
     ["美国-物价", "中国-物价", "欧洲-物价周期"]),
]


def _ver(md_path):
    try:
        with open(md_path, encoding="utf-8") as f:
            head = f.read(800)
    except OSError:
        return None
    m = re.search(r"^version:\s*([\d.]+)", head, re.M)
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def _external_roots():
    env = os.environ.get("JZS_PERSPECTIVE_DIR")
    if env:
        yield env
    home = os.path.expanduser("~")
    for base in (
        os.path.join(os.environ.get("APPDATA", ""), "mx", "hermes-home"),
        os.path.join(home, ".hermes"),
        os.path.join(home, ".claude"),
    ):
        if base and os.path.isdir(base):
            yield base


def _walk_find(root, slug, max_depth=6):
    """os.walk (glob's ** skips dot-dirs like .hermes); skip heavy dirs."""
    out, base = [], root.rstrip("\\/").count(os.sep)
    for d, subs, files in os.walk(root):
        if d.count(os.sep) - base >= max_depth:
            subs[:] = []
        subs[:] = [x for x in subs if x not in ("node_modules", ".git", "sessions", "cache", "logs", "workspace")]
        if os.path.basename(d) == slug and "SKILL.md" in files:
            out.append(os.path.join(d, "SKILL.md"))
            subs[:] = []
    return out


def find_skill(key):
    """Directory of the pack: bundled copy, or a newer local install."""
    p = PERSPECTIVES.get(key)
    if not p:
        return None
    best, best_ver = None, None
    bundled = os.path.join(BUNDLED_ROOT, p["dir"], "SKILL.md")
    if os.path.isfile(bundled):
        best, best_ver = os.path.dirname(bundled), _ver(bundled) or (0,)
    for root in _external_roots():
        if os.path.isfile(os.path.join(root, "SKILL.md")) and p["slug"] in root:
            cands = [os.path.join(root, "SKILL.md")]
        else:
            cands = _walk_find(root, p["slug"])
        for md in cands:
            v = _ver(md)
            if v is not None and (best_ver is None or v > best_ver):
                best, best_ver = os.path.dirname(md), v
    return best


def available():
    out = []
    for k, v in PERSPECTIVES.items():
        d = find_skill(k)
        out.append({"key": k, "name": v["name"], "installed": bool(d),
                    "bundled": bool(d) and os.path.abspath(d).startswith(os.path.abspath(BUNDLED_ROOT)),
                    "macro_key": bool(os.environ.get("ATTRACTOR_API_KEY"))})
    return out


def _sections(md, names):
    out = []
    for name in names:
        m = re.search(r"^## [^\n]*" + re.escape(name) + r"[^\n]*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
        if m:
            out.append(f"### {name}\n" + m.group(1).strip())
    return "\n\n".join(out)


def macro_snapshot(skill_dir, topic_text, script="macro_latest.py", timeout=60):
    """Run the pack's own macro tool. Returns text, or '' if unavailable."""
    names = []
    for pat, ind in MACRO_RULES:
        if re.search(pat, topic_text or "", re.I):
            names += [x for x in ind if x not in names]
    path = os.path.join(skill_dir, script)
    if not names or not os.path.isfile(path):
        return ""
    try:
        r = subprocess.run([sys.executable, path, *names[:12]], capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace", env=os.environ.copy())
    except (OSError, subprocess.TimeoutExpired):
        return ""
    txt = (r.stdout or "").strip()
    return txt if r.returncode == 0 and "tradeDate" in txt else ""


def _load(key, sections):
    p = PERSPECTIVES.get(key)
    d = find_skill(key) if p else None
    if not d:
        return None, None, ""
    with open(os.path.join(d, "SKILL.md"), encoding="utf-8") as f:
        md = f.read()
    return p, d, _sections(md, sections)


def brief_block(key, topic_text="", level="concept", max_paras=2, macro=True):
    """Markdown block appended to the creative brief. '' if off / not installed."""
    if not key or level == "off" or level not in LEVELS:
        return ""
    p = PERSPECTIVES.get(key)
    if not p:
        return ""
    p, d, body = _load(key, p["full_sections"] if level == "full" else p["concept_sections"])
    if not d:
        return ""
    if level == "full":
        head = (
            f"\n## 八、写作视角：{p['name']}思维框架（全文使用）\n\n"
            "用下面这套框架的心智模型与表达风格来写，"
            "先拆机制、再落路标、最后给普通人一句能记住能做的话；不给买卖/仓位/点位指令。\n\n"
        )
        limit = 9000
    else:
        n = max(1, min(int(max_paras or 2), 6))
        head = (
            f"\n## 八、写作视角：{p['name']}——只用于解释概念（最多 {n} 处）\n\n"
            f"正文整体保持本账号原有文风。**只有**在需要解释一个概念/机制（例如\"为什么加息会让美元走强\"）时，"
            f"才借用下面的心智模型来讲透它，全文最多 {n} 处，每处 1-2 段；"
            "其余段落不要套框架、不要堆术语、不要提框架名。不给买卖/仓位/点位指令。\n\n"
        )
        limit = 4500
    block = head + body[:limit]
    snap = macro_snapshot(d, topic_text, p.get("macro_script", "")) if macro else ""
    if snap:
        block += (
            "\n\n### 宏观数据核查（框架自带工具实时读数，写作时据此判断，不要编造读数）\n"
            "读法：value∈[-1,1]，正负=方向，绝对值=置信度；0.5~0.6 是边沿状态。\n\n```\n" + snap + "\n```\n"
        )
    return block


def concept_prompt(key, term, context=""):
    """Prompt for rewriting ONE concept explanation (editor tool)."""
    p, d, body = _load(key, PERSPECTIVES.get(key, {}).get("concept_sections", []))
    if not d:
        raise RuntimeError("没找到该视角包（perspectives/ 目录缺失）")
    return (
        f"用{p['name']}的思维框架，向普通读者解释这个概念：「{term}」。\n"
        "要求：1-2 段，共 150-300 字；先一句话讲本质，再用一个生活化比喻讲清机制，"
        "最后一句点出读者该盯的路标；不用小标题、不用列表、不提框架名、不给投资建议；"
        "只输出这几段正文。\n\n"
        + (f"上下文（这段解释要接在这里）：\n{context[:800]}\n\n" if context else "")
        + "框架参考：\n" + body[:4000]
    )
