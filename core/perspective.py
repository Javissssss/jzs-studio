# -*- coding: utf-8 -*-
"""Writing perspectives ("视角"): plug an external thinking-framework skill into
the brief, e.g. 《十分吸引》 shifenxiyin-perspective.

The skill itself is NOT vendored into this repo (its corpus/wording belongs to
the show). We load it at runtime from the local Hermes skills dir, or from
JZS_PERSPECTIVE_DIR. Only a few sections of SKILL.md are injected, plus a fresh
macro snapshot from the skill's own `macro_latest.py` when the topic is macro.
"""

import os
import re
import subprocess
import sys

PERSPECTIVES = {
    "shifenxiyin": {
        "name": "十分吸引",
        "slug": "shifenxiyin-perspective",
        "sections": ["输出规范", "核心心智模型", "决策启发式", "表达风格"],
        "macro_script": "macro_latest.py",
    },
}

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


def _skill_roots():
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
    """Return the directory of the newest installed copy of the perspective skill."""
    p = PERSPECTIVES.get(key)
    if not p:
        return None
    best, best_ver = None, ()
    for root in _skill_roots():
        if os.path.isfile(os.path.join(root, "SKILL.md")) and p["slug"] in root:
            cands = [os.path.join(root, "SKILL.md")]
        else:
            cands = _walk_find(root, p["slug"])
        for md in cands:
            try:
                with open(md, encoding="utf-8") as f:
                    head = f.read(600)
            except OSError:
                continue
            m = re.search(r"^version:\s*([\d.]+)", head, re.M)
            ver = tuple(int(x) for x in m.group(1).split(".")) if m else (0,)
            if ver > best_ver:
                best, best_ver = os.path.dirname(md), ver
    return best


def available():
    return [{"key": k, "name": v["name"], "installed": bool(find_skill(k))} for k, v in PERSPECTIVES.items()]


def _sections(md, names):
    out = []
    for name in names:
        m = re.search(r"^## [^\n]*" + re.escape(name) + r"[^\n]*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
        if m:
            out.append(f"### {name}\n" + m.group(1).strip())
    return "\n\n".join(out)


def macro_snapshot(skill_dir, topic_text, script="macro_latest.py", timeout=60):
    """Run the skill's own macro tool. Returns text, or '' if unavailable."""
    names = []
    for pat, ind in MACRO_RULES:
        if re.search(pat, topic_text or "", re.I):
            names += [x for x in ind if x not in names]
    path = os.path.join(skill_dir, script)
    if not names or not os.path.isfile(path):
        return ""
    try:
        r = subprocess.run([sys.executable, path, *names[:12]], capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    txt = (r.stdout or "").strip()
    return txt if r.returncode == 0 and "tradeDate" in txt else ""


def brief_block(key, topic_text=""):
    """Markdown block to append to the creative brief. '' if not installed."""
    p = PERSPECTIVES.get(key)
    d = find_skill(key) if p else None
    if not d:
        return ""
    with open(os.path.join(d, "SKILL.md"), encoding="utf-8") as f:
        md = f.read()
    body = _sections(md, p["sections"])
    macro = macro_snapshot(d, topic_text, p.get("macro_script", ""))
    block = (
        f"\n## 八、写作视角：《{p['name']}》思维框架（必须使用）\n\n"
        "用下面这套框架的心智模型与表达风格来写，观点代表节目框架而非任何具体嘉宾；"
        "先拆机制、再落路标、最后给普通人一句能记住能做的话；不给买卖/仓位/点位指令。\n\n"
        + body[:9000]
    )
    if macro:
        block += (
            "\n\n### 宏观数据核查（框架自带工具实时读数，写作时据此判断，不要编造读数）\n"
            "读法：value∈[-1,1]，正负=方向，绝对值=置信度；0.5~0.6 是边沿状态。\n\n```\n" + macro + "\n```\n"
        )
    return block
