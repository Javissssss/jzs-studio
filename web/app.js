"use strict";
/* ============================================================
   巨人之上 · 内容工作台 — app.js v2
   1-screen, left-ops / right-preview, no page navigation
   ============================================================ */

// ── state ──────────────────────────────────────────────────
let PID = null;
let PROJECTS = [];
let TOPIC_MODE = "weibo";
let SEL_CAND = null;
let BRIEF_TEXT = "";
let DRAFT = {};

// ── api ────────────────────────────────────────────────────
async function api(path, method = "GET", body = null, timeoutMs = 180000) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) opt.body = JSON.stringify(body);
  const ctrl = new AbortController();
  opt.signal = ctrl.signal;
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(path, opt);
    clearTimeout(timer);
    const j = await r.json().catch(() => ({ ok: false, error: "parse error" }));
    return j;
  } catch (e) {
    clearTimeout(timer);
    if (e.name === "AbortError") return { ok: false, error: "请求超时，请重试" };
    return { ok: false, error: "网络：" + e.message };
  }
}

// ── utils ──────────────────────────────────────────────────
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
let _tt;
function toast(msg, kind = "") {
  const t = document.getElementById("toast");
  t.textContent = msg; t.className = "toast show " + kind;
  clearTimeout(_tt); _tt = setTimeout(() => { t.className = "toast " + kind; }, 2500);
}
function spin(btn, on) {
  if (on) {
    btn._old = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> ' + btn._old.replace(/<[^>]+>/g, "").trim();
  } else {
    btn.disabled = false;
    if (btn._old != null) btn.innerHTML = btn._old;
  }
}
function show(id) { document.getElementById(id)?.classList.remove("hidden"); }
function hide(id) { document.getElementById(id)?.classList.add("hidden"); }
function $(id) { return document.getElementById(id); }

// ── accordion ──────────────────────────────────────────────
document.querySelectorAll(".blk-head").forEach(h => {
  h.addEventListener("click", () => h.closest(".block").classList.toggle("collapsed"));
});
function openBlock(id) { document.getElementById(id)?.classList.remove("collapsed"); }
function closeBlock(id) { document.getElementById(id)?.classList.add("collapsed"); }
function markDone(statusId, text) {
  const el = $(statusId);
  if (el) { el.textContent = text; el.style.color = "var(--ok)"; }
}

// ── health ─────────────────────────────────────────────────
async function loadHealth() {
  const h = await api("/api/health");
  const items = [["Pexels", h.pexels_key], ["Playwright", h.playwright], ["agent-browser", h.agent_browser]];
  $("health-bar").innerHTML = items.map(([n, on]) =>
    `<span class="h-item"><span class="h-dot ${on ? "on" : ""}"></span>${n}</span>`).join("");
}

// ── projects ───────────────────────────────────────────────
async function loadProjects() {
  const r = await api("/api/projects");
  PROJECTS = r.projects || [];
  const sel = $("proj-sel");
  sel.innerHTML = PROJECTS.length
    ? PROJECTS.map(p => `<option value="${esc(p.id)}">${esc(p.title || "未命名")} · ${esc(p.stage_label)}</option>`).join("")
    : `<option value="">（无项目）</option>`;
  if (PID) sel.value = PID;
}

$("proj-sel").addEventListener("change", async function () {
  const pid = this.value; if (!pid) return;
  const r = await api("/api/projects/" + pid);
  if (r.ok) loadProjectState(r.project);
});

$("btn-new").addEventListener("click", async () => {
  const r = await api("/api/projects", "POST", { title: "未命名" });
  if (!r.ok) { toast(r.error || "新建失败", "err"); return; }
  PID = r.project.id;
  await loadProjects();
  $("proj-sel").value = PID;
  resetUI();
  toast("新项目已建，开始选题", "ok");
});

$("btn-del").addEventListener("click", async () => {
  if (!PID) return;
  if (!confirm("删除该项目及所有产出？")) return;
  await api("/api/projects/" + PID, "DELETE");
  PID = null; BRIEF_TEXT = ""; DRAFT = {}; SEL_CAND = null;
  await loadProjects(); resetUI(); toast("已删除");
});

function loadProjectState(proj) {
  PID = proj.id;
  SEL_CAND = proj.topic?.title ? proj.topic : null;
  DRAFT = proj.draft || {};
  BRIEF_TEXT = "";
  resetUI();
  if (proj.topic?.title) {
    showTopicPreview(proj.topic);
    markDone("st-topic", proj.topic.title.slice(0, 14) + "…");
    openBlock("blk-brief"); closeBlock("blk-topic");
  }
  if (DRAFT.wechat_md) {
    showDraftPreview(DRAFT);
    markDone("st-brief", `公${DRAFT.wechat_md.length}字`);
    openBlock("blk-media");
  }
  if (proj.media?.manifest?.length) {
    showMediaPreview(proj.media);
    markDone("st-media", `${proj.media.manifest.filter(x => x.ok).length}/${proj.media.manifest.length}张`);
    openBlock("blk-pub");
  }
  if (proj.render?.html_url) {
    showRenderPreview(proj.render.html_url, proj.render.meta || {});
  }
}

function resetUI() {
  hide("pv-stack"); show("pv-empty");
  hide("pv-topic"); hide("pv-draft"); hide("pv-media"); hide("pv-render");
  $("cand-list").innerHTML = "";
  $("btn-pick").disabled = true;
  $("brief-preview").textContent = "";
  $("btn-copy-brief").disabled = true;
  $("ai-paste").value = "";
  $("fill-status").textContent = ""; $("fill-status").className = "fill-status";
  $("media-log").textContent = "";
  ["st-topic","st-brief","st-media","st-pub"].forEach(id => {
    const e = $(id); if (e) { e.textContent = ""; e.style.color = ""; }
  });
}

// ── mode inputs ────────────────────────────────────────────
function renderModeInputs() {
  const c = $("mode-inputs");
  if (TOPIC_MODE === "weibo") {
    c.innerHTML = `<p class="hint mt6">直接抓取微博实时热搜 Top 50，无需输入。</p>`;
  } else if (TOPIC_MODE === "toutiao") {
    c.innerHTML = `<p class="hint mt6">直接抓取今日头条热榜 Top 50，无需输入。</p>`;
  } else if (TOPIC_MODE === "manual") {
    c.innerHTML = `<textarea class="ta mt6" id="manual-input" rows="5" placeholder="每行一个题目，可用「标题 | 摘要」格式"></textarea>`;
  } else {
    c.innerHTML = `<input class="input mt6" id="direct-title" placeholder="文章标题（必填）">
      <textarea class="ta mt6" id="direct-sum" rows="3" placeholder="摘要 / 背景素材（可选）"></textarea>`;
  }
}
$("mode-seg").querySelectorAll(".seg").forEach(b => {
  b.addEventListener("click", () => {
    $("mode-seg").querySelectorAll(".seg").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    TOPIC_MODE = b.dataset.m;
    renderModeInputs();
  });
});
renderModeInputs();

// ── fetch topics ───────────────────────────────────────────
$("btn-fetch").addEventListener("click", async function () {
  if (!PID) { toast("请先新建或选择项目", "err"); return; }
  const body = { mode: TOPIC_MODE };
  if (TOPIC_MODE === "weibo" || TOPIC_MODE === "toutiao") {
    body.limit = 50;
  } else if (TOPIC_MODE === "manual") {
    body.text = $("manual-input")?.value || "";
  } else {
    body.title = ($("direct-title")?.value || "").trim();
    body.summary = ($("direct-sum")?.value || "").trim();
    if (!body.title) { toast("请填写标题", "err"); return; }
  }
  spin(this, true);
  const r = await api(`/api/projects/${PID}/topics/fetch`, "POST", body);
  spin(this, false);
  if (!r.ok) { toast(r.error || "抓取失败", "err"); return; }
  const cands = r.candidates || [];
  toast(`抓到 ${cands.length} 个候选`, "ok");
  renderCandidates(cands);
});

function renderCandidates(cands) {
  SEL_CAND = null; $("btn-pick").disabled = true;
  const box = $("cand-list");
  if (!cands.length) { box.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:8px 0">没有候选题</div>'; return; }
  box.innerHTML = cands.map((c, i) => `
    <div class="cand" data-i="${i}">
      <div class="cand-rank">${c.rank || i + 1}</div>
      <div class="cand-body">
        <div class="cand-t">${esc(c.title)}</div>
        ${c.summary ? `<div class="cand-s">${esc(c.summary)}</div>` : ""}
      </div>
      <div class="cand-badges">
        <span class="badge badge-score">${c.total_score || 0}分</span>
        ${c.niche_hits ? `<span class="badge badge-niche">垂直×${c.niche_hits}</span>` : ""}
        ${c.recommend ? `<span class="badge badge-rec">荐</span>` : ""}
      </div>
    </div>`).join("");
  const _c = cands;
  box.querySelectorAll(".cand").forEach(node => {
    node.addEventListener("click", () => {
      box.querySelectorAll(".cand").forEach(x => x.classList.remove("sel"));
      node.classList.add("sel");
      SEL_CAND = _c[+node.dataset.i];
      $("btn-pick").disabled = false;
    });
  });
}

$("btn-pick").addEventListener("click", async function () {
  if (!SEL_CAND || !PID) return;
  spin(this, true);
  const r = await api(`/api/projects/${PID}/topic/select`, "POST", { topic: SEL_CAND });
  spin(this, false);
  if (!r.ok) { toast(r.error || "选定失败", "err"); return; }
  markDone("st-topic", SEL_CAND.title.slice(0, 14) + "…");
  showTopicPreview(SEL_CAND);
  openBlock("blk-brief"); closeBlock("blk-topic");
  await loadProjects();
  toast("已选定，生成简报 →", "ok");
});

// ── preview: topic ─────────────────────────────────────────
function showTopicPreview(topic) {
  $("pv-topic-title").textContent = topic.title || "";
  $("pv-topic-meta").innerHTML = [
    topic.summary ? esc(topic.summary.slice(0, 80)) : "",
    topic.source ? `<span style="opacity:.6;margin-left:8px">${esc(topic.source)}</span>` : "",
    topic.total_score != null ? `<span style="margin-left:8px">总分 ${topic.total_score}</span>` : "",
  ].join("");
  show("pv-topic"); hide("pv-empty"); show("pv-stack");
}

// ── brief ──────────────────────────────────────────────────
$("btn-gen-brief").addEventListener("click", async function () {
  if (!PID) { toast("请先选定题目", "err"); return; }
  spin(this, true);
  const r = await api(`/api/projects/${PID}/brief/generate`, "POST", {});
  spin(this, false);
  if (!r.ok) { toast(r.error || "生成失败", "err"); return; }
  BRIEF_TEXT = r.brief;
  $("brief-preview").textContent = BRIEF_TEXT.slice(0, 600) + (BRIEF_TEXT.length > 600 ? "\n…（滚动查看）" : "");
  $("btn-copy-brief").disabled = false;
  toast("简报已生成，复制后给 AI 出稿", "ok");
});

$("btn-copy-brief").addEventListener("click", () => {
  if (!BRIEF_TEXT) return;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(BRIEF_TEXT).then(() => toast("简报已复制", "ok")).catch(() => fbCopy(BRIEF_TEXT));
  } else fbCopy(BRIEF_TEXT);
});
function fbCopy(txt) {
  const ta = document.createElement("textarea"); ta.value = txt;
  ta.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); toast("已复制", "ok"); } catch { toast("复制失败", "err"); }
  document.body.removeChild(ta);
}

// ── fill draft ─────────────────────────────────────────────
$("btn-fill").addEventListener("click", async function () {
  const txt = $("ai-paste").value.trim();
  if (!txt) { toast("请先粘贴 AI 回复", "err"); return; }
  if (!PID) { toast("请先选定题目", "err"); return; }
  spin(this, true);
  const r = await api(`/api/projects/${PID}/draft/fill`, "POST", { ai_output: txt });
  spin(this, false);
  if (!r.ok) { toast(r.error || "解析失败", "err"); return; }
  DRAFT = r.project.draft || {};
  const st = $("fill-status");
  if (r.parsed_ok) {
    st.textContent = `✓ 公众号 ${DRAFT.wechat_md?.length || 0} 字，小红书 ${DRAFT.xhs_md?.length || 0} 字，框架图 ${DRAFT.figures?.length || 0}，数据图 ${DRAFT.charts?.length || 0}`;
    st.className = "fill-status ok";
  } else {
    st.textContent = "⚠ 未识别标记，整段作为公众号正文";
    st.className = "fill-status";
  }
  markDone("st-brief", `公${DRAFT.wechat_md?.length || 0}字`);
  showDraftPreview(DRAFT);
  openBlock("blk-media"); closeBlock("blk-brief");
  await loadProjects();
  toast(r.parsed_ok ? "回填完成 →" : "回填完成（无标记）");
});

function showDraftPreview(d) {
  $("pv-draft-stats").innerHTML = [
    { v: d.wechat_md?.length || 0, k: "公号字" },
    { v: d.xhs_md?.length || 0, k: "小红书字" },
    { v: d.figures?.length || 0, k: "框架图" },
    { v: d.charts?.length || 0, k: "数据图" },
  ].map(x => `<div class="pv-stat"><span class="sv">${x.v}</span><span class="sk">${x.k}</span></div>`).join("");
  $("pv-xhs-titles").innerHTML = (d.xhs_titles || []).map(t => `<div class="pv-xhs-title">${esc(t)}</div>`).join("");
  $("pv-tags").innerHTML = (d.xhs_tags || []).map(t => `<span class="chip">${esc(t)}</span>`).join("");
  show("pv-draft");
}

// ── media + render ─────────────────────────────────────────
$("btn-media").addEventListener("click", async function () {
  if (!PID) { toast("请先回填稿件", "err"); return; }
  const log = $("media-log");
  spin(this, true);
  log.textContent = "⏳ 配图生成中（约 30-90s）…";

  const mr = await api(`/api/projects/${PID}/media/generate`, "POST", {});
  if (!mr.ok) {
    spin(this, false);
    log.textContent = "✗ 配图失败：" + (mr.error || "");
    toast("配图失败", "err"); return;
  }
  const man = mr.project.media?.manifest || [];
  const okN = man.filter(x => x.ok).length;
  log.textContent = `✓ 配图 ${okN}/${man.length}\n` +
    man.map(x => `  ${x.type}:${x.key} ${x.ok ? "✓" : "✗ " + (x.log || "").slice(0, 50)}`).join("\n");

  log.textContent += "\n⏳ 排版中…";
  const rr = await api(`/api/projects/${PID}/render`, "POST", {});
  spin(this, false);
  if (!rr.ok) {
    log.textContent += "\n✗ 排版失败：" + (rr.error || "");
    toast("排版失败", "err"); return;
  }
  const meta = rr.project.render?.meta || {};
  log.textContent += `\n✓ 排版完成：${meta.word_count || 0} 字，${meta.sections || 0} 节`;

  markDone("st-media", `${okN}/${man.length}张`);
  showMediaPreview(mr.project.media);
  showRenderPreview(rr.project.render?.html_url, meta);
  openBlock("blk-pub"); closeBlock("blk-media");
  await api(`/api/projects/${PID}/approve`, "POST", {});
  await loadProjects();
  toast(`配图排版完成 ${okN}/${man.length}`, "ok");
});

function showMediaPreview(media) {
  const man = media.manifest || [];
  const cards = media.card_urls || [];
  const all = [
    ...man.filter(x => x.url).map(x => ({ url: x.url, label: x.type + ":" + x.key, ok: x.ok })),
    ...cards.map(u => ({ url: u, label: "XHS卡片", ok: true })),
  ];
  $("pv-thumbs").innerHTML = all.length
    ? all.map(x => `<div class="pv-thumb ${x.ok ? "" : "fail"}" data-url="${esc(x.url)}" data-cap="${esc(x.label)}">
        <img src="${esc(x.url)}" alt="" loading="lazy">
        <div class="pt-label">${esc(x.label)}</div>
        <div class="pt-zoom">⤢</div></div>`).join("")
    : '<div style="font-size:12px;color:var(--muted)">无缩略图</div>';
  // attach click handlers after innerHTML set
  $("pv-thumbs").querySelectorAll(".pv-thumb[data-url]").forEach(el => {
    el.addEventListener("click", () => openLightbox(el.dataset.url, el.dataset.cap));
  });
  show("pv-media");
}

// ── lightbox ───────────────────────────────────────────────
function openLightbox(url, caption) {
  let lb = document.getElementById("lb-overlay");
  if (!lb) {
    lb = document.createElement("div");
    lb.id = "lb-overlay";
    lb.innerHTML = `
      <div class="lb-backdrop" onclick="closeLightbox()"></div>
      <div class="lb-box">
        <button class="lb-close" onclick="closeLightbox()">×</button>
        <img class="lb-img" id="lb-img">
        <div class="lb-cap" id="lb-cap"></div>
      </div>`;
    document.body.appendChild(lb);
  }
  document.getElementById("lb-img").src = url;
  document.getElementById("lb-cap").textContent = caption || "";
  lb.classList.add("lb-show");
  document.addEventListener("keydown", lbKeyHandler);
}
function closeLightbox() {
  const lb = document.getElementById("lb-overlay");
  if (lb) lb.classList.remove("lb-show");
  document.removeEventListener("keydown", lbKeyHandler);
}
function lbKeyHandler(e) { if (e.key === "Escape") closeLightbox(); }

function showRenderPreview(htmlUrl, meta) {
  if (!htmlUrl) return;
  $("pv-frame").src = htmlUrl;
  $("pv-render-link").href = htmlUrl;
  show("pv-render");
  markDone("st-pub", `${meta.word_count || 0}字`);
}

// ── publish ────────────────────────────────────────────────
$("btn-wc-copy").addEventListener("click", async function () {
  spin(this, true);
  const r = await api(`/api/projects/${PID}/publish/wechat/copy`, "POST", {});
  spin(this, false);
  toast(r.msg || (r.ok ? "富文本已复制" : "复制失败"), r.ok ? "ok" : "err");
});
$("btn-wc-open").addEventListener("click", async function () {
  spin(this, true);
  const r = await api(`/api/projects/${PID}/publish/wechat/open`, "POST", {});
  spin(this, false);
  toast(r.ok ? "已打开公众号后台（首次扫码）" : "打开失败", r.ok ? "ok" : "err");
});
$("btn-xhs-copy").addEventListener("click", async function () {
  spin(this, true);
  const r = await api(`/api/projects/${PID}/publish/xhs/copy`, "POST", {});
  spin(this, false);
  toast(r.msg || (r.ok ? "文案已复制" : "复制失败"), r.ok ? "ok" : "err");
});
$("btn-xhs-open").addEventListener("click", async function () {
  spin(this, true);
  const r = await api(`/api/projects/${PID}/publish/xhs/open`, "POST", {});
  spin(this, false);
  toast(r.ok ? "已打开小红书（首次扫码）" : "打开失败", r.ok ? "ok" : "err");
});
$("btn-archive").addEventListener("click", async function () {
  if (!PID) return;
  spin(this, true);
  const r = await api(`/api/projects/${PID}/archive`, "POST", {});
  spin(this, false);
  if (r.ok) { await loadProjects(); toast("已归档", "ok"); markDone("st-pub", "已归档"); }
  else toast(r.error || "归档失败", "err");
});

// ── init ───────────────────────────────────────────────────
(async function init() {
  await Promise.all([loadHealth(), loadProjects()]);
  if (PROJECTS.length) {
    $("proj-sel").value = PROJECTS[0].id;
    const r = await api("/api/projects/" + PROJECTS[0].id);
    if (r.ok) loadProjectState(r.project);
  }
  setInterval(loadHealth, 30000);
})();
