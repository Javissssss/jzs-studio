# -*- coding: utf-8 -*-
"""一稿 (jzs-studio) Flask server: topic -> draft -> images -> layout -> publish.
Run: python app.py  (then open http://127.0.0.1:8770)"""

import json
import os
import re
import time
import traceback

from flask import Flask, jsonify, request, send_from_directory, abort
from werkzeug.exceptions import HTTPException

from core import config, state, topics, brief, enrich, llm, media, render, cards, publish
from core import codex, imagegen, jobs, settings as app_settings

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
def _apply_ai_output(pid, s, ai_output, overrides=None):
    """Parse an AI reply into the project draft (+ auto image placeholders)."""
    o = overrides or {}
    parsed = brief.parse_ai_output(ai_output)
    figures = parsed.get("figures", [])
    charts = parsed.get("charts", [])
    wechat_md, report = enrich.ensure_placeholders(
        o.get("wechat_md") or parsed["wechat_md"], s.get("topic", {}).get("title", ""), figures, charts
    )
    s["draft"] = {
        "wechat_md": wechat_md,
        "xhs_md": o.get("xhs_md") or parsed["xhs_md"],
        "xhs_titles": o.get("xhs_titles") or parsed["xhs_titles"],
        "xhs_tags": o.get("xhs_tags") or parsed["xhs_tags"],
        "figures": figures,
        "charts": charts,
    }
    with open(os.path.join(config.project_dir(pid), "ai_output.md"), "w", encoding="utf-8") as f:
        f.write(ai_output)
    s["stage"] = "media"
    state.log(s, f"draft filled (parsed_ok={parsed['parsed_ok']}, enriched={report})")
    state.save(pid, s)
    return {
        "ok": True,
        "parsed_ok": parsed["parsed_ok"],
        "enriched": report,
        "project": _public(state.load(pid)),
    }


@app.route("/api/projects/<pid>/draft/fill", methods=["POST"])
def api_draft_fill(pid):
    s = _load_or_404(_safe_pid(pid))
    b = _body()
    ai_output = b.get("ai_output", "")
    if not ai_output.strip():
        return jsonify({"ok": False, "error": "请先粘贴 AI 回复"}), 400
    return jsonify(_apply_ai_output(pid, s, ai_output, b))


CODEX_WRITE_TAIL = """

---
你在本地以 Codex 身份执行：不要修改任何文件，不要运行命令，
直接把完整稿件作为最终回复输出（只含上面「输出格式」里的标记块）。
"""


def _writer(pid, engine, extra_notes):
    """Return fn(logf) that writes the full draft with the chosen engine."""

    def fn(logf):
        s = _load_or_404(pid)
        topic = s.get("topic") or {}
        brief_md = brief.generate_brief(topic, extra_notes=extra_notes)
        with open(os.path.join(config.project_dir(pid), "brief.md"), "w", encoding="utf-8") as f:
            f.write(brief_md)
        logf(f"简报已生成（{len(brief_md)} 字）")
        if engine == "codex":
            text = codex.run(brief_md + CODEX_WRITE_TAIL, os.path.join(config.project_dir(pid), "codex"), logf)
            model = "Codex"
        else:
            logf(f"调用 {llm.settings()['model']} 写稿中…")
            text = llm.write_draft(brief_md)
            model = llm.settings()["model"]
        if not text.strip():
            raise RuntimeError("引擎没有返回内容")
        logf(f"收到 {len(text)} 字，解析中")
        out = _apply_ai_output(pid, state.load(pid), text)
        out["model"] = model
        out["project"] = None  # client refetches
        return out

    return fn


def _start_job(kind, pid, fn):
    """Start a background job, or run inline when ?wait=1 (tests, scripts)."""
    if request.args.get("wait") == "1":
        try:
            result, log = jobs.run_sync(fn)
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 502
        return jsonify({"ok": True, "status": "done", "result": result, "log": log})
    try:
        job = jobs.start(kind, pid, fn)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True, "job": jobs.public(job)})


@app.route("/api/projects/<pid>/draft/write", methods=["POST"])
def api_draft_write(pid):
    """Write the full draft. engine: api (OpenAI-compatible) | codex (codex exec)."""
    s = _load_or_404(_safe_pid(pid))
    if not (s.get("topic") or {}).get("title"):
        return jsonify({"ok": False, "error": "请先选定题目"}), 400
    b = _body()
    engine = b.get("engine", "api")
    if engine not in ("api", "codex"):
        return jsonify({"ok": False, "error": "engine 只能是 api / codex"}), 400
    if engine == "api" and not llm.is_configured():
        return jsonify({"ok": False, "error": "未配置写作模型：点右上角「设置」填写 Base URL / API Key / 模型"}), 502
    if engine == "codex" and not codex.find_cmd():
        return jsonify({"ok": False, "error": "没找到 codex 命令：npm i -g @openai/codex 后 codex login，或在设置里填 Codex 命令"}), 502
    return _start_job("write", pid, _writer(pid, engine, b.get("extra_notes", "")))


@app.route("/api/jobs/<jid>", methods=["GET"])
def api_job(jid):
    job = jobs.get(jid)
    if not job:
        abort(404, description="job not found")
    return jsonify({"ok": True, "job": jobs.public(job, int(request.args.get("since", 0)))})


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
def _keep_manual(s):
    """Manually supplied images survive regeneration (keyed by placeholder)."""
    return {m["raw"]: m for m in s.get("media", {}).get("manifest", []) if m.get("engine") == "manual" and m.get("ok")}


def _do_media(pid, s, mood_engine="stock", logf=None):
    """Generate article images + XHS cards. Mutates and saves state."""
    logf = logf or (lambda m: None)
    d = s.get("draft", {})
    if mood_engine == "codex":
        try:
            _codex_art(pid, s, logf)
        except RuntimeError as e:  # fall back to stock images, never lose the whole run
            logf(f"✗ Codex 失败，氛围图改用图库：{e}"[:300])
            mood_engine = "stock"
        d = s.get("draft", {})
    manifest = media.generate_media(
        pid, d["wechat_md"], figures=d.get("figures", []), charts=d.get("charts", []),
        mood_engine="ai" if mood_engine == "ai" else "stock",
        title=s.get("topic", {}).get("title", ""), keep=_keep_manual(s), logf=logf,
    )
    if mood_engine == "codex":
        _apply_codex_art(pid, manifest, logf)
    card_info = {"ok": False, "pngs": [], "log": "skipped (no xhs draft)"}
    if d.get("xhs_md"):
        logf("生成小红书卡片…")
        try:
            card_info = cards.generate_cards(
                pid, d["xhs_md"], d.get("xhs_titles", []), d.get("xhs_tags", [])
            )
        except Exception as e:
            card_info = {"ok": False, "pngs": [], "log": str(e)[:200]}
    s["media"] = {
        "manifest": manifest,
        "engine": mood_engine,
        "cards": card_info.get("pngs", []),
        "cards_ok": card_info.get("ok"),
        "cards_log": card_info.get("log", ""),
    }
    ok_count = sum(1 for m in manifest if m.get("ok"))
    logf(f"配图 {ok_count}/{len(manifest)} · 卡片 {len(s['media']['cards'])} 张")
    state.log(s, f"media({mood_engine}): {ok_count}/{len(manifest)} images, {len(s['media']['cards'])} cards")
    s["stage"] = "render"
    state.save(pid, s)


CODEX_ART_PROMPT = """你是公众号插画师兼信息设计师。当前目录是一个空工作目录，请直接在这里写文件，不要联网。

文章标题：{title}

任务一（框架图数据）：为下列框架图占位符写出结构化数据，保存为 figures.json（JSON 数组）：
{fig_list}
每项格式 {{"id","kind","caption","data"}}，kind 取 flow/compare/checklist/timeline，data schema：
- flow: {{"title","subtitle","steps":[{{"label","desc"}}]}}（3-5 步）
- compare: {{"title","subtitle","left":{{"name","items":[str]}},"right":{{"name","items":[str]}}}}
- checklist: {{"title","subtitle","items":[{{"text","note"}}]}}
- timeline: {{"title","subtitle","events":[{{"date","text"}}]}}
内容要紧扣下面正文，不要空泛。没有框架图占位符就写 []。

任务二（插画）：为下列配图位各画一张插画，每张一个文件 slot_<序号>.html：
{mood_list}
要求：纯 HTML + 内联 SVG/CSS，不引用任何外部资源和字体文件；根元素 <div id="figure" style="width:1080px;height:608px">；
扁平编辑插画风，配色克制（主色不超过 3 个），画面里不放大段文字；字体只用 "Microsoft YaHei"。

正文（节选）：
{body}

全部写完后，最终回复只需一行：DONE
"""


def _codex_art(pid, s, logf):
    """Let Codex design missing framework data + draw SVG illustrations for MOOD slots."""
    d = s.get("draft", {})
    phs = media.parse_placeholders(d.get("wechat_md", ""))
    have = {str(f.get("id")) for f in d.get("figures", []) if f.get("data")}
    figs = [p for p in phs if p["type"] == "FIGURE" and p["key"] not in have]
    moods = [(i, p) for i, p in enumerate(phs, 1) if p["type"] == "MOOD"]
    keep = _keep_manual(s)
    moods = [(i, p) for i, p in moods if p["raw"] not in keep]
    if not figs and not moods:
        logf("Codex：没有需要它处理的配图位")
        return
    wd = os.path.join(config.project_dir(pid), "codex_art")
    if os.path.isdir(wd):
        import shutil

        shutil.rmtree(wd, ignore_errors=True)
    prompt = CODEX_ART_PROMPT.format(
        title=s.get("topic", {}).get("title", ""),
        fig_list="\n".join(f"- id={p['key']}：{p['caption']}" for p in figs) or "（无）",
        mood_list="\n".join(f"- 序号 {i:02d}：{p['caption'] or p['key']}（意象：{p['key']}）" for i, p in moods) or "（无）",
        body=d.get("wechat_md", "")[:6000],
    )
    logf(f"Codex 设计 {len(figs)} 张框架图、绘制 {len(moods)} 张插画…")
    codex.run(prompt, wd, logf, writable=True)
    fj = os.path.join(wd, "figures.json")
    if os.path.exists(fj):
        try:
            with open(fj, encoding="utf-8") as f:
                new = [x for x in json.load(f) if isinstance(x, dict) and x.get("id")]
            byid = {str(x.get("id")): x for x in d.get("figures", [])}
            byid.update({str(x["id"]): x for x in new})
            d["figures"] = list(byid.values())
            s["draft"] = d
            logf(f"Codex 框架图数据 {len(new)} 份")
        except (ValueError, OSError) as e:
            logf(f"figures.json 解析失败：{e}")


def _apply_codex_art(pid, manifest, logf):
    """Screenshot slot_XX.html drawn by Codex into the MOOD slots."""
    wd = os.path.join(config.project_dir(pid), "codex_art")
    out_dir = os.path.join(config.project_dir(pid), "output")
    for i, m in enumerate(manifest, 1):
        if m["type"] != "MOOD" or m.get("engine") == "manual":
            continue
        src = os.path.join(wd, f"slot_{i:02d}.html")
        if not os.path.exists(src):
            m.update({"ok": False, "file": None, "engine": "codex", "log": "Codex 没有画这张"})
            continue
        try:
            png = media.screenshot_html(src, os.path.join(out_dir, f"codex_{i:02d}.png"))
            m.update({"ok": True, "file": png, "engine": "codex", "log": ""})
        except Exception as e:  # noqa: BLE001
            m.update({"ok": False, "file": None, "engine": "codex", "log": f"截图失败：{e}"[:300]})


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


IMAGE_ENGINES = ("stock", "ai", "codex")


@app.route("/api/projects/<pid>/produce", methods=["POST"])
def api_produce(pid):
    """One click: images + cards + layout, in the background.
    image_engine: stock (Pexels 图库) | ai (生图 API) | codex (Codex 画插画+设计框架)"""
    s = _load_or_404(_safe_pid(pid))
    if not s.get("draft", {}).get("wechat_md"):
        return jsonify({"ok": False, "error": "还没有公众号稿件，请先写稿"}), 400
    eng = _body().get("image_engine", "stock")
    if eng not in IMAGE_ENGINES:
        return jsonify({"ok": False, "error": "image_engine 只能是 stock / ai / codex"}), 400
    if eng == "ai" and not imagegen.is_configured():
        return jsonify({"ok": False, "error": "未配置生图接口：点右上角「设置」填写"}), 502
    if eng == "codex" and not codex.find_cmd():
        return jsonify({"ok": False, "error": "没找到 codex 命令"}), 502

    def fn(logf):
        st = state.load(pid)
        _do_media(pid, st, eng, logf)
        logf("排版中…")
        _do_render(pid, state.load(pid))
        meta = state.load(pid)["render"]["meta"]
        logf(f"排版完成：{meta.get('word_count', 0)} 字 · {meta.get('images', 0)} 图")
        return {"meta": meta}

    return _start_job("produce", pid, fn)


ALLOWED_IMG = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "webp": ".webp", "gif": ".gif"}


@app.route("/api/projects/<pid>/media/slot/<int:idx>", methods=["POST", "DELETE"])
def api_media_slot(pid, idx):
    """Manually set (upload / paste) or clear the image of slot idx (1-based), then re-render."""
    import base64

    s = _load_or_404(_safe_pid(pid))
    man = s.get("media", {}).get("manifest", [])
    if not 1 <= idx <= len(man):
        return jsonify({"ok": False, "error": "配图位不存在，请先一键生产"}), 400
    entry = man[idx - 1]
    if request.method == "DELETE":
        entry.update({"ok": False, "file": None, "engine": "none", "log": "已移除，重新生产时会自动补图"})
    else:
        raw, ext = None, None
        f = request.files.get("file")
        if f:
            ext = ALLOWED_IMG.get((f.filename or "").rsplit(".", 1)[-1].lower())
            raw = f.read()
        else:
            m = re.match(r"data:image/(\w+);base64,(.+)", _body().get("data_url", ""), re.DOTALL)
            if m:
                ext, raw = ALLOWED_IMG.get(m.group(1).lower()), base64.b64decode(m.group(2))
        if not raw or not ext:
            return jsonify({"ok": False, "error": "只支持 png / jpg / webp / gif 图片"}), 400
        if len(raw) > 15 * 1024 * 1024:
            return jsonify({"ok": False, "error": "图片超过 15MB"}), 400
        path = os.path.join(config.project_dir(pid), "output", f"manual_{idx:02d}_{int(time.time())}{ext}")
        with open(path, "wb") as fh:
            fh.write(raw)
        entry.update({"ok": True, "file": path, "engine": "manual", "log": ""})
    state.log(s, f"slot {idx} -> {entry['engine']}")
    state.save(pid, s)
    _do_render(pid, state.load(pid))
    return jsonify({"ok": True, "project": _public(state.load(pid))})


# ---------- settings ----------
@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return jsonify({"ok": True, "settings": app_settings.public()})


@app.route("/api/settings", methods=["POST"])
def api_settings_set():
    try:
        app_settings.update(_body())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "settings": app_settings.public()})


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
                     download_name=f"yigao_{safe}.zip")


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
            "llm": llm.public_info(),
            "imagegen": imagegen.public_info(),
            "codex": codex.public_info(),
            "brand": config.brand(),
            "product": config.PRODUCT_NAME,
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
    print(f"[{config.PRODUCT_NAME}] starting on http://{args.host}:{args.port}")
    print(f"[{config.PRODUCT_NAME}] workspace: {config.WORKSPACE_DIR}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
