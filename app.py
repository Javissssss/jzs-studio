# -*- coding: utf-8 -*-
"""jzs-studio Flask server. Orchestrates the 8-stage dual-platform pipeline.
Run: python app.py  (then open http://127.0.0.1:8770)"""

import os
import re
import traceback

from flask import Flask, jsonify, request, send_from_directory, abort

from core import config, state, topics, brief, media, render, cards, publish

app = Flask(__name__, static_folder=None)
config.ensure_dirs()


# ---------- helpers ----------
def _load_or_404(pid):
    s = state.load(pid)
    if s is None:
        abort(404, description=f"project not found: {pid}")
    return s


def _body():
    return request.get_json(silent=True) or {}


def _safe_pid(pid):
    if not re.fullmatch(r"[\w\-]+", pid or ""):
        abort(400, description="invalid project id")
    return pid


# ---------- static frontend ----------
@app.route("/")
def index():
    return send_from_directory(config.WEB_DIR, "index.html")


@app.route("/web/<path:fname>")
def web_static(fname):
    return send_from_directory(config.WEB_DIR, fname)


@app.route("/output/<pid>/<path:fname>")
def output_file(pid, fname):
    _safe_pid(pid)
    out_dir = os.path.join(config.project_dir(pid), "output")
    if not os.path.isdir(out_dir):
        abort(404)
    return send_from_directory(out_dir, fname)


# ---------- projects ----------
@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    return jsonify({"projects": state.list_projects()})


@app.route("/api/projects", methods=["POST"])
def api_new_project():
    b = _body()
    s = state.new_project(title=b.get("title", "未命名"))
    return jsonify({"ok": True, "project": _public(s)})


@app.route("/api/projects/<pid>", methods=["GET"])
def api_get_project(pid):
    s = _load_or_404(_safe_pid(pid))
    return jsonify({"ok": True, "project": _public(s)})


@app.route("/api/projects/<pid>", methods=["DELETE"])
def api_delete_project(pid):
    _safe_pid(pid)
    ok = state.delete(pid)
    return jsonify({"ok": ok})


def _public(s):
    """Project state safe for frontend (paths -> urls)."""
    pid = s["id"]
    pub = dict(s)
    # convert output file paths to preview urls
    render_info = dict(s.get("render", {}))
    if render_info.get("html_path"):
        render_info["html_url"] = f"/output/{pid}/" + os.path.basename(
            render_info["html_path"]
        )
    pub["render"] = render_info
    media_info = s.get("media", {})
    if isinstance(media_info, dict) and media_info.get("manifest"):
        man = []
        for m in media_info["manifest"]:
            mm = dict(m)
            if mm.get("file"):
                mm["url"] = f"/output/{pid}/" + os.path.basename(mm["file"])
            man.append(mm)
        media_info = dict(media_info)
        media_info["manifest"] = man
        pub["media"] = media_info
    if isinstance(s.get("media", {}), dict) and s["media"].get("cards"):
        pub.setdefault("media", {})
        pub["media"]["card_urls"] = [
            f"/output/{pid}/" + os.path.basename(c) for c in s["media"]["cards"]
        ]
    return pub


# ---------- stage 1: topic ----------
@app.route("/api/projects/<pid>/topics/fetch", methods=["POST"])
def api_topics_fetch(pid):
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    mode = b.get("mode", "weibo")
    try:
        r = topics.fetch_and_score(
            mode=mode,
            text=b.get("text", ""),
            title=b.get("title", ""),
            summary=b.get("summary", ""),
            extra_keywords=b.get("keywords"),
            limit=int(b.get("limit", 50)),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500
    s["candidates"] = r["scored"]
    state.log(s, f"fetched topics mode={mode} count={len(r['scored'])}")
    state.save(pid, s)
    return jsonify({"ok": True, "error": r.get("error"), "candidates": r["scored"]})


@app.route("/api/projects/<pid>/topic/select", methods=["POST"])
def api_topic_select(pid):
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    topic = b.get("topic") or {}
    if not topic.get("title"):
        return jsonify({"ok": False, "error": "topic title required"}), 400
    s["topic"] = topic
    if not s.get("title") or s["title"] in ("untitled", "未命名"):
        s["title"] = topic["title"][:30]
    s["stage"] = "brief"
    state.log(s, f"selected topic: {topic.get('title', '')[:30]}")
    state.save(pid, s)
    return jsonify({"ok": True, "project": _public(state.load(pid))})


# ---------- stage 2: brief ----------
@app.route("/api/projects/<pid>/brief/generate", methods=["POST"])
def api_brief_generate(pid):
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    topic = s.get("topic") or {}
    if not topic.get("title"):
        return jsonify({"ok": False, "error": "no topic selected"}), 400
    brief_md = brief.generate_brief(topic, extra_notes=b.get("extra_notes", ""))
    # save brief to project
    bpath = os.path.join(config.project_dir(pid), "brief.md")
    with open(bpath, "w", encoding="utf-8") as f:
        f.write(brief_md)
    s["brief"] = {"path": bpath, "length": len(brief_md)}
    state.log(s, "brief generated")
    state.save(pid, s)
    return jsonify({"ok": True, "brief": brief_md})


# ---------- stage 3: draft fill ----------
@app.route("/api/projects/<pid>/draft/fill", methods=["POST"])
def api_draft_fill(pid):
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    ai_output = b.get("ai_output", "")
    if not ai_output.strip():
        return jsonify({"ok": False, "error": "empty ai_output"}), 400
    parsed = brief.parse_ai_output(ai_output)
    # allow manual override of individual fields
    wechat_md = b.get("wechat_md") or parsed["wechat_md"]
    figures = parsed.get("figures", [])
    charts = parsed.get("charts", [])

    # ── Auto-inject rich media placeholders ──────────────────────────────
    # Strategy:
    #   1. Cover image  – always inject [MOOD:cover_query] at very top
    #   2. Figure cards – inject [FIGURE:fN] after first H2 if missing
    #   3. Section mood – inject [MOOD:section_query] into every H2 section
    #   4. Chart        – inject [CHART:cN] if data present
    import re as _re

    topic_title = s.get("topic", {}).get("title", "")
    topic_kw = re.sub(r"[^\w\s]", "", topic_title.lower())[:30].strip() or "knowledge"
    # Convert Chinese topic to safe English search query
    en_kw_map = {
        "ai": "artificial intelligence technology",
        "教育": "education learning classroom",
        "经济": "economy finance business",
        "股": "stock market trading",
        "房": "real estate housing",
        "健康": "health wellness lifestyle",
        "政策": "government policy document",
        "科技": "technology innovation digital",
        "创业": "startup entrepreneurship office",
        "职场": "workplace office professional",
    }
    cover_query = "modern knowledge concept abstract"
    for cn, en in en_kw_map.items():
        if cn in topic_title:
            cover_query = en
            break

    existing_phs = set(_re.findall(r"\[(FIGURE|MOOD|CHART):([^\]]+)\]", wechat_md))
    existing_ids = {key for _, key in existing_phs}
    existing_types = {t for t, _ in existing_phs}

    lines_out = wechat_md.splitlines()
    result_lines = []
    h2_count = 0
    figure_inserted = set()
    chart_inserted = set()

    # Insert cover MOOD at very top (before first line) unless already present
    has_cover = any(k.startswith("cover") for _, k in existing_phs)
    if not has_cover:
        result_lines.append(f"\n[MOOD:{cover_query}] 封面配图\n")

    mood_queries = [
        "office desk productivity focus",
        "people learning concept idea",
        "data analysis visualization chart",
        "city technology modern future",
        "notebook writing inspiration",
    ]
    mood_idx = 0

    fig_by_order = list(figures)  # consume in order
    fig_ptr = 0
    ch_by_order = list(charts)
    ch_ptr = 0

    for ln in lines_out:
        stripped = ln.strip()
        result_lines.append(ln)

        if stripped.startswith("## "):
            h2_count += 1
            # After each H2 heading: inject next figure card (first H2) or mood (subsequent)
            if h2_count == 1 and fig_ptr < len(fig_by_order):
                fig = fig_by_order[fig_ptr]
                fid = str(fig.get("id", f"f{fig_ptr + 1}"))
                if fid not in existing_ids:
                    result_lines.append(
                        f"\n[FIGURE:{fid}] {fig.get('caption', '框架图')}\n"
                    )
                    figure_inserted.add(fid)
                fig_ptr += 1
            elif h2_count > 1:
                # inject atmosphere image for each section
                q = mood_queries[mood_idx % len(mood_queries)]
                mood_idx += 1
                auto_key = f"sec{h2_count}"
                if auto_key not in existing_ids:
                    result_lines.append(f"\n[MOOD:{q}] 配图\n")
                # inject remaining figure cards
                if fig_ptr < len(fig_by_order):
                    fig = fig_by_order[fig_ptr]
                    fid = str(fig.get("id", f"f{fig_ptr + 1}"))
                    if fid not in existing_ids:
                        result_lines.append(
                            f"\n[FIGURE:{fid}] {fig.get('caption', '框架图')}\n"
                        )
                        figure_inserted.add(fid)
                    fig_ptr += 1

    # Inject any remaining figures/charts at end
    while fig_ptr < len(fig_by_order):
        fig = fig_by_order[fig_ptr]
        fid = str(fig.get("id", f"f{fig_ptr + 1}"))
        if fid not in existing_ids and fid not in figure_inserted:
            result_lines.append(f"\n[FIGURE:{fid}] {fig.get('caption', '框架图')}\n")
        fig_ptr += 1
    while ch_ptr < len(ch_by_order):
        ch = ch_by_order[ch_ptr]
        cid = str(ch.get("id", f"c{ch_ptr + 1}"))
        if cid not in existing_ids and cid not in chart_inserted:
            result_lines.append(f"\n[CHART:{cid}] {ch.get('caption', '数据图')}\n")
        ch_ptr += 1

    wechat_md = "\n".join(result_lines)

    s["draft"] = {
        "wechat_md": wechat_md,
        "xhs_md": b.get("xhs_md") or parsed["xhs_md"],
        "xhs_titles": b.get("xhs_titles") or parsed["xhs_titles"],
        "xhs_tags": b.get("xhs_tags") or parsed["xhs_tags"],
        "figures": figures,
        "charts": charts,
    }
    s["stage"] = "media"
    state.log(s, f"draft filled (parsed_ok={parsed['parsed_ok']})")
    state.save(pid, s)
    return jsonify(
        {
            "ok": True,
            "parsed_ok": parsed["parsed_ok"],
            "project": _public(state.load(pid)),
        }
    )


@app.route("/api/projects/<pid>/draft", methods=["GET"])
def api_draft_get(pid):
    s = _load_or_404(_safe_pid(pid))
    return jsonify({"ok": True, "draft": s.get("draft", {})})


@app.route("/api/projects/<pid>/draft", methods=["POST"])
def api_draft_edit(pid):
    """Manual edit of draft fields (after fill)."""
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    d = s.get("draft", {})
    for k in ("wechat_md", "xhs_md", "xhs_titles", "xhs_tags", "figures", "charts"):
        if k in b:
            d[k] = b[k]
    s["draft"] = d
    state.log(s, "draft edited manually")
    state.save(pid, s)
    return jsonify({"ok": True, "project": _public(s)})


# ---------- stage 4: media ----------
@app.route("/api/projects/<pid>/media/generate", methods=["POST"])
def api_media_generate(pid):
    s = _load_or_404(_safe_pid(pid))
    d = s.get("draft", {})
    wechat_md = d.get("wechat_md", "")
    if not wechat_md:
        return jsonify({"ok": False, "error": "no wechat draft"}), 400
    try:
        manifest = media.generate_media(
            pid, wechat_md, figures=d.get("figures", []), charts=d.get("charts", [])
        )
    except Exception as e:
        return jsonify(
            {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-500:],
            }
        ), 500
    # XHS cards
    card_info = {"ok": False, "pngs": [], "log": "skipped"}
    if d.get("xhs_md"):
        try:
            card_info = cards.generate_cards(
                pid, d.get("xhs_md", ""), d.get("xhs_titles", []), d.get("xhs_tags", [])
            )
        except Exception as e:
            card_info = {"ok": False, "pngs": [], "log": str(e)[:200]}
    s["media"] = {
        "manifest": manifest,
        "cards": card_info.get("pngs", []),
        "cards_ok": card_info.get("ok"),
        "cards_log": card_info.get("log", ""),
    }
    ok_count = sum(1 for m in manifest if m.get("ok"))
    state.log(
        s,
        f"media generated: {ok_count}/{len(manifest)} placeholders, cards={len(card_info.get('pngs', []))}",
    )
    state.save(pid, s)
    return jsonify({"ok": True, "project": _public(state.load(pid))})


# ---------- stage 5: render ----------
@app.route("/api/projects/<pid>/render", methods=["POST"])
def api_render(pid):
    s = _load_or_404(_safe_pid(pid))
    d = s.get("draft", {})
    wechat_md = d.get("wechat_md", "")
    if not wechat_md:
        return jsonify({"ok": False, "error": "no wechat draft"}), 400
    manifest = s.get("media", {}).get("manifest", [])
    try:
        html_str, meta = render.render_article(
            wechat_md, manifest, topic=s.get("topic", {})
        )
        path = render.save_html(pid, html_str, title=meta.get("title", "article"))
        # also save markdown
        md_path = os.path.join(
            config.project_dir(pid),
            "output",
            f"公众号_{re.sub(r'[^\\w\\u4e00-\\u9fff-]', '', meta.get('title', ''))[:30] or 'article'}_终版.md",
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(wechat_md)
    except Exception as e:
        return jsonify(
            {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-500:],
            }
        ), 500
    s["render"] = {"html_path": path, "md_path": md_path, "meta": meta}
    state.log(
        s,
        f"rendered html: {meta.get('word_count', 0)} words, {meta.get('sections', 0)} sections",
    )
    state.save(pid, s)
    return jsonify({"ok": True, "project": _public(state.load(pid))})


# ---------- stage 6: review ----------
@app.route("/api/projects/<pid>/review", methods=["GET"])
def api_review(pid):
    s = _load_or_404(_safe_pid(pid))
    return jsonify({"ok": True, "project": _public(s)})


@app.route("/api/projects/<pid>/approve", methods=["POST"])
def api_approve(pid):
    s = _load_or_404(_safe_pid(pid))
    state.set_stage(pid, "publish")
    return jsonify({"ok": True, "project": _public(state.load(pid))})


@app.route("/api/projects/<pid>/goto", methods=["POST"])
def api_goto(pid):
    """Jump back to an earlier stage for edits."""
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    stage = b.get("stage")
    if stage not in config.STAGES:
        return jsonify({"ok": False, "error": "invalid stage"}), 400
    state.set_stage(pid, stage)
    return jsonify({"ok": True, "project": _public(state.load(pid))})


# ---------- stage 7: publish ----------
@app.route("/api/projects/<pid>/publish/wechat/kit", methods=["GET"])
def api_wechat_kit(pid):
    s = _load_or_404(_safe_pid(pid))
    kit = publish.wechat_kit(pid, s)
    kit["html_url"] = (
        (f"/output/{pid}/" + os.path.basename(kit["html_path"]))
        if kit.get("html_path")
        else ""
    )
    kit["image_urls"] = [
        f"/output/{pid}/" + os.path.basename(p) for p in kit.get("images", [])
    ]
    return jsonify({"ok": True, "kit": kit})


@app.route("/api/projects/<pid>/publish/wechat/copy", methods=["POST"])
def api_wechat_copy(pid):
    s = _load_or_404(_safe_pid(pid))
    html_path = s.get("render", {}).get("html_path")
    if not html_path or not os.path.exists(html_path):
        return jsonify(
            {"ok": False, "error": "no rendered html; run render first"}
        ), 400
    ok, msg = publish.copy_html_to_clipboard(html_path)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/projects/<pid>/publish/wechat/open", methods=["POST"])
def api_wechat_open(pid):
    ok, log = publish.open_platform("wechat")
    return jsonify({"ok": ok, "log": log[-300:]})


@app.route("/api/projects/<pid>/publish/xhs/kit", methods=["GET"])
def api_xhs_kit(pid):
    s = _load_or_404(_safe_pid(pid))
    kit = publish.xhs_kit(pid, s)
    kit["card_urls"] = [
        f"/output/{pid}/" + os.path.basename(p) for p in kit.get("cards", [])
    ]
    return jsonify({"ok": True, "kit": kit})


@app.route("/api/projects/<pid>/publish/xhs/copy", methods=["POST"])
def api_xhs_copy(pid):
    s = _load_or_404(_safe_pid(pid))
    text = s.get("draft", {}).get("xhs_md", "")
    ok = publish.copy_text_to_clipboard(text)
    return jsonify({"ok": ok, "msg": "文案已复制到剪贴板" if ok else "复制失败"})


@app.route("/api/projects/<pid>/publish/xhs/open", methods=["POST"])
def api_xhs_open(pid):
    ok, log = publish.open_platform("xhs")
    return jsonify({"ok": ok, "log": log[-300:]})


# ---------- stage 8: archive ----------
@app.route("/api/projects/<pid>/archive", methods=["POST"])
def api_archive(pid):
    s = _load_or_404(_safe_pid(pid))
    out_dir = os.path.join(config.project_dir(pid), "output")
    files = sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []
    manifest_md = f"# 交付清单 - {s.get('title', '')}\n\n"
    manifest_md += f"- 项目ID: {pid}\n- 选题: {s.get('topic', {}).get('title', '')}\n"
    manifest_md += (
        f"- 阶段: {config.STAGE_LABELS.get(s.get('stage', ''), '')}\n\n## 产出文件\n\n"
    )
    for f in files:
        manifest_md += f"- output/{f}\n"
    mpath = os.path.join(config.project_dir(pid), "manifest.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(manifest_md)
    state.set_stage(pid, "done")
    return jsonify(
        {"ok": True, "manifest": manifest_md, "project": _public(state.load(pid))}
    )


# ---------- health ----------
@app.route("/api/health", methods=["GET"])
def api_health():
    import shutil

    ab = shutil.which("agent-browser") or publish._agent_browser_cmd()
    return jsonify(
        {
            "ok": True,
            "python": config.PYTHON,
            "pexels_key": bool(os.environ.get("PEXELS_API_KEY")),
            "unsplash_key": bool(os.environ.get("UNSPLASH_ACCESS_KEY")),
            "agent_browser": bool(ab) and ab != "agent-browser",
            "playwright": _check_playwright(),
            "workspace": config.WORKSPACE_DIR,
        }
    )


def _check_playwright():
    try:
        import playwright  # noqa

        return True
    except Exception:
        return False


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    print(f"[jzs-studio] starting on http://{args.host}:{args.port}")
    print(f"[jzs-studio] workspace: {config.WORKSPACE_DIR}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
