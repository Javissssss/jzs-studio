# -*- coding: utf-8 -*-
"""Creative brief generator - the heart of the semi-automatic writing flow.

Generates a comprehensive brief (topic + style rules + structure + image plan)
that the user copies into ANY AI (ws/Codex/通义/Kimi/豆包). The AI output uses
markers so the app can parse drafts back automatically.
"""

import os
import re
import json

from . import config

# Output markers for parsing AI response back
M_WECHAT = ("===WECHAT_START===", "===WECHAT_END===")
M_XHS = ("===XHS_START===", "===XHS_END===")
M_TITLE = ("===XHS_TITLE_START===", "===XHS_TITLE_END===")
M_TAGS = ("===XHS_TAGS_START===", "===XHS_TAGS_END===")
M_FIGURES = ("===FIGURES_START===", "===FIGURES_END===")
M_CHARTS = ("===CHARTS_START===", "===CHARTS_END===")


def _read_ref(name):
    path = os.path.join(config.REFERENCES_DIR, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            # style docs were written for the original column; use current brand
            return f.read().replace("巨人之上", config.brand())
    return ""


def _extract_section(md, header_keywords, stop_at_next_h2=True):
    """Extract a section from markdown by header keyword."""
    lines = md.splitlines()
    out = []
    capturing = False
    for ln in lines:
        is_h2 = ln.startswith("## ")
        if is_h2 and any(k in ln for k in header_keywords):
            capturing = True
            out.append(ln)
            continue
        if capturing and is_h2 and stop_at_next_h2:
            break
        if capturing:
            out.append(ln)
    return "\n".join(out).strip()


def plan_images(topic_title, topic_summary=""):
    """Propose an image plan based on topic type. Returns list of dicts."""
    text = (topic_title + " " + topic_summary).lower()
    plan = []
    # finance detection
    finance_kw = [
        "美联储",
        "利率",
        "汇率",
        "黄金",
        "国债",
        "收益率",
        "通胀",
        "美股",
        "a股",
        "基金",
        "楼市",
        "房价",
        "降息",
        "加息",
        "财经",
        "经济",
    ]
    is_finance = any(k in text for k in finance_kw)
    # how-to / method detection
    method_kw = ["如何", "怎么", "方法", "技巧", "指南", "步骤", "习惯", "提效", "效率"]
    is_method = any(k in text for k in method_kw)
    # comparison detection
    compare_kw = ["对比", "区别", "vs", "哪个好", "选择", "差异"]
    is_compare = any(k in text for k in compare_kw)

    # Always: 1 cover
    plan.append(
        {
            "pos": "封面",
            "type": "AI信息图/素材图",
            "engine": "imagegen或search_images",
            "desc": f"围绕「{topic_title[:12]}」的2.35:1横版封面，无文字",
        }
    )
    if is_compare:
        plan.append(
            {
                "pos": "正文核心",
                "type": "对比框架图",
                "engine": "figure_cards:compare",
                "desc": "两栏对照，讲清差异",
            }
        )
    if is_method:
        plan.append(
            {
                "pos": "正文核心",
                "type": "流程/清单框架图",
                "engine": "figure_cards:flow或checklist",
                "desc": "把方法拆成可执行步骤",
            }
        )
    if is_finance:
        plan.append(
            {
                "pos": "正文数据",
                "type": "数据图表",
                "engine": "antv或figure_cards",
                "desc": "关键数字可视化（走势/对比）",
            }
        )
    # Default knowledge framework
    if not (is_compare or is_method):
        plan.append(
            {
                "pos": "正文核心",
                "type": "机制流程框架图",
                "engine": "figure_cards:flow",
                "desc": "把核心机制拆成3-5步",
            }
        )
    # Atmosphere images
    plan.append(
        {
            "pos": "正文穿插",
            "type": "氛围配图2-3张",
            "engine": "search_images(Pexels)",
            "desc": "与主题相关的场景图，figcaption标注图源",
        }
    )
    return plan


def generate_brief(topic, extra_notes="", perspective="", words=0, persp_level="concept", persp_paras=2, n_images=0):
    """Generate the unified dual-platform creative brief (markdown string)."""
    title = topic.get("title", "")
    summary = topic.get("summary", "")
    source = topic.get("source", "")
    angle = topic.get("angle", "") or summary

    wechat_style = _read_ref("wechat-style.md")
    xhs_style = _read_ref("xhs-style.md")

    wechat_rules = _extract_section(wechat_style, ["文风铁律"])
    wechat_struct = _extract_section(wechat_style, ["结构模板"])
    wechat_pos = _extract_section(wechat_style, ["定位与受众"])
    xhs_copy = _extract_section(xhs_style, ["文案撰写"])
    xhs_tag = _extract_section(xhs_style, ["标签"])

    img_plan = plan_images(title, summary)
    img_table = "| 位置 | 类型 | 引擎 | 内容描述 |\n|------|------|------|---------|\n"
    for p in img_plan:
        img_table += f"| {p['pos']} | {p['type']} | {p['engine']} | {p['desc']} |\n"

    finance_note = ""
    if config.is_finance(title + " " + summary):
        finance_note = f"\n> ⚠️ 本文涉及财经，正文末尾必须加免责声明：「{config.FINANCE_DISCLAIMER}」\n"

    length = f"约{int(words)}字（±10%），严格控制篇幅" if words else "2500-4000字"
    brief = f"""# 「{config.brand()}」双平台创作简报

把这份简报整段复制给任意 AI（ws / Codex / 通义 / Kimi / 豆包网页版均可），
让它按末尾「输出格式」产出稿件，再把 AI 的完整回复粘回工作台「回填稿件」步骤。

---

## 一、你的任务

围绕下面选定的题目，写两份内容：
1. **微信公众号长文**（{length}，深度）
2. **小红书笔记**（正文≤1000字 + 标题×2 + 标签6-8个，降维干货）

## 二、选定题目

- **标题**：{title}
- **摘要/素材**：{summary or "（无，请自行展开）"}
- **切入角度**：{angle}
- **来源**：{source}
{finance_note}
## 三、账号定位（务必遵守）

{wechat_pos or '频道「{config.brand()}」：给AI时代想借力提效的普通人（非开发者），主张"不自己造轮子，先找别人造好的缆车"。'}

## 四、公众号长文要求

### 文风铁律
{wechat_rules}

### 结构模板
{wechat_struct}

### 配图规划（⚠️ 占位符是强制要求，不写会导致配图全部跳过）
{img_table}
**占位符写法**（每张图单独占一行，格式严格，不能省略）：
- 知识框架图（必须写 1 张）：`[FIGURE:f1] 图说文字`（f1/f2… 编号与下方 FIGURES 块 id 对应；**首选 kind=mindmap 逻辑脑图**，其它 kind 只在确实是纯流程/对比/时间线时用）
- 氛围图（每篇至少1张）：`[MOOD:英文搜索词] 图说文字`（搜索词用英文具象名词，如 `[MOOD:bond market finance]`）
- 数据图：`[CHART:c1] 图说文字`（c1… 与下方 CHARTS 块 id 对应）

⚠️ **关键**：正文里每一个 [FIGURE:xxx] / [MOOD:xxx] / [CHART:xxx] 都必须单独占一行，前后空行，不能合并进段落。工作台会据此自动配图，你只需留占位符 + 在末尾提供结构化数据。

### 框架图数据结构（FIGURES 块用）
- **mindmap（逻辑脑图，首选）**：不是目录！要把全文的关键信息组织成「中心结论 → 3-6 个逻辑分支 → 每支 2-4 条带数据的要点」，分支之间体现因果/传导/对立关系：
  `{{"title":"图标题(≤14字)","subtitle":"一句话背景","root":"中心命题(≤10字)","root_note":"关键数据","takeaway":"一句话结论，可用**加粗**",
    "branches":[{{"label":"分支名(≤8字)","tag":"起因/链一/链二/误区/行动…","relation":"与中心的关系(≤6字，如：倒逼、传导、对冲)","note":"可选一句","children":["关键词：具体数据或判断", "…"]}}]}}`
  要求：children 必须是**具体信息**（数字、因果、判断），禁止只写章节名；每条 ≤22 字，用「关键词：说明」格式
- flow（流程）：`{{"title","subtitle","steps":[{{"label","desc"}}]}}`
- compare（对比）：`{{"title","subtitle","left":{{"name","items":[str]}},"right":{{"name","items":[str]}}}}`
- checklist（清单）：`{{"title","subtitle","items":[{{"text","note"}}]}}`
- timeline（时间线）：`{{"title","subtitle","events":[{{"date","text"}}]}}`

## 五、小红书文案要求

{xhs_copy}

**标签**：{xhs_tag or "6-8个，前3精准后3-5泛流量"}

## 六、输出格式（严格按此结构，便于工作台自动解析回填）

请你的回复**只包含**以下标记块，标记行务必原样保留：

{M_WECHAT[0]}
（公众号正文 Markdown。H2 用 ## 开头；配图位置按上面占位符写法单独成行；结尾带互动问句；财经带免责声明）
{M_WECHAT[1]}

{M_XHS[0]}
（小红书正文，≤1000字，含📷图X指引、URL每行一个、末尾#标签）
{M_XHS[1]}

{M_TITLE[0]}
标题一（20字内）
标题二（20字内）
{M_TITLE[1]}

{M_TAGS[0]}
#标签1 #标签2 #标签3 #标签4 #标签5 #标签6
{M_TAGS[1]}

{M_FIGURES[0]}
[
  {{"id":"f1","kind":"mindmap","caption":"图说文字","data":{{"title":"...","subtitle":"...","root":"...","root_note":"...","takeaway":"...","branches":[{{"label":"...","tag":"...","relation":"...","children":["关键词：数据/判断"]}}]}}}}
]
{M_FIGURES[1]}

{M_CHARTS[0]}
[
  {{"id":"c1","type":"line","caption":"图说","data":[{{"time":"2020","value":100}}]}}
]
{M_CHARTS[1]}

（FIGURES/CHARTS 块是 JSON 数组，id 必须与正文占位符一致；没有框架图/数据图就给空数组 []）
"""
    if extra_notes:
        brief += f"\n## 七、额外要求（用户补充）\n\n{extra_notes}\n"
    if n_images:
        brief += (f"\n## 配图数量（用户指定）\n\n全文正好 {int(n_images)} 张图：1 张 [FIGURE] 知识脑图，"
                  f"至少 1 张 [MOOD] 氛围图（第一张氛围图会被用作封面），其余按内容选 [CHART] 或 [MOOD]。\n")
    if perspective and persp_level != "off":
        from . import perspective as _pv

        brief += _pv.brief_block(perspective, f"{title} {summary} {angle}", level=persp_level, max_paras=persp_paras)
    return brief


_TOC_HEAD = re.compile(r"^#{1,3}\s*(目录|目\s*录|contents|toc)\s*$", re.I)
_READ_TIME = re.compile(r"^\s*[（(]?\s*(全文)?约\s*[\d,，.]+\s*字[，,、\s]*(阅读|读完|预计阅读)[^\n]{0,12}分钟[。.)）]?\s*$")


def strip_self_toc(md):
    """Models often write their own '## 目录' + bullet list + '约N字读完N分钟'.
    The renderer builds both automatically, so drop them (keep any placeholders
    like [FIGURE:..] that the model parked inside that section)."""
    lines = (md or "").splitlines()
    out, in_toc = [], False
    for ln in lines:
        st = ln.strip()
        if _TOC_HEAD.match(st):
            in_toc = True
            continue
        if in_toc:
            if st.startswith("## ") or st == "---":
                in_toc = False
                if st == "---":
                    continue
            elif not st or re.match(r"^([-*+]|\d+[.、)])\s+", st) or _READ_TIME.match(st):
                continue
            elif st.startswith("["):  # placeholder: keep
                out.append(ln)
                continue
            else:
                in_toc = False
        if _READ_TIME.match(st):
            continue
        out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def parse_ai_output(text):
    """Parse the AI response back into structured drafts using markers.
    Returns dict with wechat_md, xhs_md, xhs_titles[], xhs_tags[].
    Tolerant: if markers missing, put everything in wechat_md."""

    def grab(s, markers):
        m = re.search(
            re.escape(markers[0]) + r"(.*?)" + re.escape(markers[1]), s, re.DOTALL
        )
        return m.group(1).strip() if m else ""

    wechat = grab(text, M_WECHAT)
    xhs = grab(text, M_XHS)
    title_block = grab(text, M_TITLE)
    tags_block = grab(text, M_TAGS)
    figures_block = grab(text, M_FIGURES)
    charts_block = grab(text, M_CHARTS)

    def parse_json_array(block):
        if not block:
            return []
        try:
            v = json.loads(block)
            return v if isinstance(v, list) else []
        except Exception:
            # tolerant: try to find the outermost [...]
            m = re.search(r"\[.*\]", block, re.DOTALL)
            if m:
                try:
                    v = json.loads(m.group(0))
                    return v if isinstance(v, list) else []
                except Exception:
                    return []
            return []

    figures = parse_json_array(figures_block)
    charts = parse_json_array(charts_block)

    titles = (
        [t.strip() for t in title_block.splitlines() if t.strip()]
        if title_block
        else []
    )
    tags = []
    if tags_block:
        tags = [
            t.strip()
            for t in re.split(r"[\s,，]+", tags_block)
            if t.strip().startswith("#")
        ]
        if not tags:
            tags = [t.strip() for t in tags_block.splitlines() if t.strip()]

    # Fallback: no markers at all -> treat whole text as wechat draft
    parsed_ok = bool(wechat or xhs)
    if not parsed_ok:
        wechat = text.strip()

    wechat = strip_self_toc(wechat)
    return {
        "wechat_md": wechat,
        "xhs_md": xhs,
        "xhs_titles": titles,
        "xhs_tags": tags,
        "figures": figures,
        "charts": charts,
        "parsed_ok": parsed_ok,
    }
