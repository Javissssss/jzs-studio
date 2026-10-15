# -*- coding: utf-8 -*-
"""jzs-studio Flask server. Orchestrates the 8-stage dual-platform pipeline.
Run: python app.py  (then open http://127.0.0.1:8770)"""

import os
import re
import traceback

from flask import Flask, jsonify, request, send_from_directory, abort
from werkzeug.exceptions import HTTPException

from core import config, state, topics, brief, enrich, media, render, cards, publish

app = Flask(__name__, static_folder=None)
config.ensure_dirs()


# ---------- helpers ----------
@app.errorhandler(HTTPException)
def _json_error(e):
    """API errors as JSON so the UI can show a readable toast."""
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": e.description}), e.code
    return e


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

    # fill image gaps the AI left (cover/section moods, unused figure/chart data)
    wechat_md, enrich_report = enrich.ensure_placeholders(
        wechat_md, s.get("topic", {}).get("title", ""), figures, charts
    )

    s["draft"] = {
        "wechat_md": wechat_md,
        "xhs_md": b.get("xhs_md") or parsed["xhs_md"],
        "xhs_titles": b.get("xhs_titles") or parsed["xhs_titles"],
        "xhs_tags": b.get("xhs_tags") or parsed["xhs_tags"],
        "figures": figures,
        "charts": charts,
    }
    s["stage"] = "media"
    state.log(s, f"draft filled (parsed_ok={parsed['parsed_ok']}, enriched={enrich_report})")
    state.save(pid, s)
    return jsonify(
        {
            "ok": True,
            "parsed_ok": parsed["parsed_ok"],
            "enriched": enrich_report,
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


# ---------- stage 4+5: media & render ----------
def _do_media(pid, s):
    """Generate article images + XHS cards. Mutates and saves state."""
    d = s.get("draft", {})
    manifest = media.generate_media(
        pid, d["wechat_md"], figures=d.get("figures", []), charts=d.get("charts", [])
    )
    card_info = {"ok": False, "pngs": [], "log": "skipped (no xhs draft)"}
    if d.get("xhs_md"):
        try:
            card_info = cards.generate_cards(
                pid, d["xhs_md"], d.get("xhs_titles", []), d.get("xhs_tags", [])
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
    state.log(s, f"media: {ok_count}/{len(manifest)} images, {len(s['media']['cards'])} cards")
    s["stage"] = "render"
    state.save(pid, s)


def _do_render(pid, s):
    """Render WeChat HTML + markdown. Mutates and saves state."""
    d = s.get("draft", {})
    manifest = s.get("media", {}).get("manifest", [])
    html_str, meta = render.render_article(d["wechat_md"], manifest, topic=s.get("topic", {}))
    path = render.save_html(pid, html_str, title=meta.get("title", "article"))
    md_path = path[: -len(".html")] + ".md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(d["wechat_md"])
    s["render"] = {"html_path": path, "md_path": md_path, "meta": meta}
    s["stage"] = "review"
    state.log(s, f"rendered: {meta.get('word_count', 0)} chars, {meta.get('sections', 0)} sections")
    state.save(pid, s)


def _step(pid, *steps):
    """Run media/render steps with uniform error handling."""
    s = _load_or_404(_safe_pid(pid))
    if not s.get("draft", {}).get("wechat_md"):
        return jsonify({"ok": False, "error": "还没有公众号稿件，请先回填"}), 400
    try:
        for fn in steps:
            fn(pid, s)
    except Exception as e:
        return jsonify(
            {"ok": False, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-500:]}
        ), 500
    return jsonify({"ok": True, "project": _public(state.load(pid))})


@app.route("/api/projects/<pid>/media/generate", methods=["POST"])
def api_media_generate(pid):
    return _step(pid, _do_media)


@app.route("/api/projects/<pid>/render", methods=["POST"])
def api_render(pid):
    return _step(pid, _do_render)


@app.route("/api/projects/<pid>/produce", methods=["POST"])
def api_produce(pid):
    """One click: images + cards + layout."""
    return _step(pid, _do_media, _do_render)


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


@app.route("/api/projects/<pid>/export.zip", methods=["GET"])
def api_export(pid):
    """Download all deliverables (output/ + brief + manifest) as one zip."""
    import io
    import zipfile

    from flask import send_file

    s = _load_or_404(_safe_pid(pid))
    pdir = config.project_dir(pid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(pdir):
            for f in files:
                if f == "state.json" or f.startswith("_"):
                    continue  # internal files
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, pdir))
    buf.seek(0)
    safe = re.sub(r"[^\w\u4e00-\u9fff-]", "", s.get("title", ""))[:30] or pid
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"jzs_{safe}.zip")


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
