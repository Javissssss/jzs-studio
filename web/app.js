"use strict";
/* ============================================================
   巨人之上 · 内容工作台 — app.js v3
   Left: 4 operation blocks. Right: live preview.
   All UI state is derived from the project returned by the API
   (single source of truth: applyProject()).
   ============================================================ */

const $ = (id) => document.getElementById(id);
const S = { pid: null, projects: [], mode: "weibo", cands: [], sel: null, brief: "", project: null, edField: "wechat_md" };

// ── api ────────────────────────────────────────────────────
async function api(path, method = "GET", body = null, timeoutMs = 240000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(path, {
      method, signal: ctrl.signal,
      headers: { "Content-Type": "application/json" },
      body: body === null ? undefined : JSON.stringify(body),
    });
    return await r.json().catch(() => ({ ok: false, error: `服务返回异常 (HTTP ${r.status})` }));
  } catch (e) {
    return { ok: false, error: e.name === "AbortError" ? "请求超时，请重试" : "连不上服务：" + e.message };
  } finally { clearTimeout(timer); }
}

// ── utils ──────────────────────────────────────────────────
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const show = (id, on = true) => $(id)?.classList.toggle("hidden", !on);
let _tt;
function toast(msg, kind = "") {
  const t = $("toast");
  t.textContent = msg; t.className = "toast show " + kind;
  clearTimeout(_tt); _tt = setTimeout(() => (t.className = "toast " + kind), 2800);
}
async function busy(btn, fn) {
  if (btn.disabled) return;
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span> ${btn.textContent.trim()}`;
  try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = old; }
}
async function copyText(txt) {
  try { await navigator.clipboard.writeText(txt); return true; } catch { /* fall through */ }
  const ta = Object.assign(document.createElement("textarea"), { value: txt });
  ta.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(ta); ta.select();
  const ok = document.execCommand("copy");
  ta.remove(); return ok;
}
function requirePid() {
  if (S.pid) return true;
  toast("先点左上角 ＋ 新建项目", "err"); return false;
}

// ── accordion ──────────────────────────────────────────────
document.querySelectorAll(".blk-head").forEach((h) =>
  h.addEventListener("click", () => h.closest(".block").classList.toggle("collapsed")));
function focusBlock(id) {
  document.querySelectorAll(".block").forEach((b) => b.classList.toggle("collapsed", b.id !== id));
}

// ── health ─────────────────────────────────────────────────
async function loadHealth() {
  const h = await api("/api/health");
  const items = [
    ["Pexels", h.pexels_key, "氛围配图素材源（设置 PEXELS_API_KEY）"],
    ["Playwright", h.playwright, "框架图 / 数据图 / 小红书卡片截图"],
    ["agent-browser", h.agent_browser, "富文本复制 + 扫码登录平台（可选）"],
  ];
  S.llm = h.llm || {};
  items.unshift(["写作模型", S.llm.configured, S.llm.configured ? `内置写作：${S.llm.model}` : "未配置：在 .env 填 JZS_LLM_*，即可一键写全文"]);
  $("write-hint").textContent = S.llm.configured
    ? `由 ${S.llm.model} 写公众号 + 小红书双稿，约 1–3 分钟。`
    : "还没配置写作模型：在项目根目录 .env 填 JZS_LLM_BASE_URL / API_KEY / MODEL 后重启。也可用下方外部 AI。";
  $("btn-write").disabled = !S.llm.configured;
  if (!S.llm.configured) $("manual-flow").open = true;
  $("health-bar").innerHTML = items.map(([n, on, tip]) =>
    `<span class="h-item" title="${esc(tip)}${on ? "" : " · 未就绪"}"><span class="h-dot ${on ? "on" : ""}"></span>${n}</span>`).join("");
}

// ── projects ───────────────────────────────────────────────
async function loadProjects() {
  const r = await api("/api/projects");
  S.projects = r.projects || [];
  $("proj-sel").innerHTML = S.projects.length
    ? S.projects.map((p) => `<option value="${esc(p.id)}">${esc(p.title || "未命名")} · ${esc(p.stage_label)}</option>`).join("")
    : `<option value="">（还没有项目）</option>`;
  if (S.pid) $("proj-sel").value = S.pid;
}
async function openProject(pid) {
  const r = await api("/api/projects/" + pid);
  if (r.ok) { S.cands = []; S.sel = null; S.brief = ""; applyProject(r.project, true); }
}
async function newProject() {
  const r = await api("/api/projects", "POST", { title: "未命名" });
  if (!r.ok) return toast(r.error || "新建失败", "err");
  S.pid = r.project.id; S.cands = []; S.sel = null; S.brief = "";
  await loadProjects();
  applyProject(r.project, true);
  toast("新项目已建，先选个题", "ok");
}
$("proj-sel").addEventListener("change", (e) => e.target.value && openProject(e.target.value));
$("btn-new").addEventListener("click", newProject);
$("btn-start").addEventListener("click", newProject);
$("btn-del").addEventListener("click", async () => {
  if (!S.pid || !confirm("删除该项目及全部产出？此操作不可恢复。")) return;
  await api("/api/projects/" + S.pid, "DELETE");
  S.pid = null; S.project = null;
  await loadProjects();
  if (S.projects.length) await openProject(S.projects[0].id); else applyProject(null);
  toast("已删除");
});

// ── single render function: project -> whole UI ────────────
const STAGE_ORDER = ["topic", "brief", "draft", "media", "render", "review", "publish", "done"];
const STEP_OF = { topic: "topic", brief: "brief", draft: "brief", media: "media", render: "media", review: "review", publish: "publish", done: "publish" };

function applyProject(p, autoFocus = false) {
  S.project = p;
  S.pid = p?.id || null;
  const has = {
    topic: !!p?.topic?.title,
    draft: !!p?.draft?.wechat_md,
    media: !!p?.media?.manifest,
    render: !!p?.render?.html_url,
    done: p?.stage === "done",
  };

  // empty state
  show("pv-empty", !p);
  show("pv-stack", !!p);

  // stepper
  const cur = STEP_OF[p?.stage] || "topic";
  const steps = ["topic", "brief", "media", "review", "publish"];
  const curIdx = p ? steps.indexOf(cur) : -1;
  document.querySelectorAll("#stepper li").forEach((li, i) => {
    li.className = !p ? "" : i < curIdx || (has.done && i === curIdx) ? "done" : i === curIdx ? "cur" : "";
  });

  // block done marks + status text
  const mark = (blk, st, on, text) => {
    $(blk).classList.toggle("done", on);
    $(st).textContent = on ? text : "";
  };
  mark("blk-topic", "st-topic", has.topic, p?.topic?.title || "");
  mark("blk-brief", "st-brief", has.draft, has.draft ? `公众号 ${p.draft.wechat_md.length} 字` : "");
  const man = p?.media?.manifest || [];
  const okN = man.filter((x) => x.ok).length;
  mark("blk-media", "st-media", has.render, has.render ? `配图 ${okN}/${man.length} · 已排版` : "");
  mark("blk-pub", "st-pub", has.done, "已归档");

  // previews
  renderTopicCard(p?.topic);
  renderDraftCard(p?.draft, p?.render?.meta);
  renderOutput(p);
  renderReview(p);
  $("btn-export").href = p ? `/api/projects/${p.id}/export.zip` : "#";
  ["btn-rerender", "btn-edit"].forEach((id) => ($(id).disabled = !has.draft));
  if (!S.cands.length) $("cand-list").innerHTML = "";
  $("btn-pick").disabled = !S.sel;

  if (autoFocus && p) {
    focusBlock(!has.topic ? "blk-topic" : !has.draft ? "blk-brief" : !has.render ? "blk-media" : "blk-pub");
  }
}

// ── 1. topic ───────────────────────────────────────────────
const MODE_HINT = { weibo: "抓取微博实时热搜 Top 50", toutiao: "抓取今日头条热榜 Top 50", baidu: "抓取百度实时热搜 Top 50" };
function renderModeInputs() {
  const c = $("mode-inputs");
  if (MODE_HINT[S.mode]) c.innerHTML = `<p class="hint">${MODE_HINT[S.mode]}，按账号定位（AI · 财经 · 效率）评分排序。</p>`;
  else if (S.mode === "manual") c.innerHTML = `<textarea class="ta" id="manual-input" rows="5" placeholder="每行一个题目，可写成「标题 | 摘要」"></textarea>`;
  else c.innerHTML = `<input class="input" id="direct-title" placeholder="文章标题（必填）">
      <textarea class="ta" id="direct-sum" rows="3" placeholder="摘要 / 背景素材（可选）"></textarea>`;
  $("btn-fetch").textContent = S.mode === "direct" ? "使用这个题目" : S.mode === "manual" ? "评分排序" : "抓取并评分";
}
$("mode-seg").addEventListener("click", (e) => {
  const b = e.target.closest(".seg"); if (!b) return;
  $("mode-seg").querySelectorAll(".seg").forEach((x) => x.classList.toggle("active", x === b));
  S.mode = b.dataset.m; renderModeInputs();
});
renderModeInputs();

$("btn-fetch").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  const body = { mode: S.mode, limit: 50 };
  if (S.mode === "manual") body.text = $("manual-input").value;
  if (S.mode === "direct") {
    body.title = $("direct-title").value.trim();
    body.summary = $("direct-sum").value.trim();
    if (!body.title) return toast("请填写标题", "err");
  }
  const r = await api(`/api/projects/${S.pid}/topics/fetch`, "POST", body);
  if (!r.ok) return toast(r.error || "抓取失败（可换个来源或手动输入）", "err");
  S.cands = r.candidates || [];
  // direct mode: one candidate, select it straight away
  if (S.mode === "direct" && S.cands.length) return pickTopic(S.cands[0]);
  renderCandidates();
  toast(`拿到 ${S.cands.length} 个候选`, "ok");
}));
$("niche-only").addEventListener("change", renderCandidates);

function renderCandidates() {
  const nicheOnly = $("niche-only").checked;
  const list = S.cands.filter((c) => !nicheOnly || c.niche_hits > 0);
  show("niche-wrap", S.cands.length > 0);
  S.sel = null; $("btn-pick").disabled = true;
  const box = $("cand-list");
  if (!list.length) { box.innerHTML = `<div class="empty-note">${S.cands.length ? "没有垂直相关的题，取消勾选看全部" : "没有候选题"}</div>`; return; }
  box.innerHTML = list.map((c, i) => `
    <div class="cand" data-i="${i}" tabindex="0">
      <div class="cand-rank">${c.rank || i + 1}</div>
      <div class="cand-body">
        <div class="cand-t">${esc(c.title)}</div>
        ${c.summary ? `<div class="cand-s">${esc(c.summary)}</div>` : ""}
      </div>
      <div class="cand-badges">
        <span class="badge badge-score">${c.total_score || 0} 分</span>
        ${c.niche_hits ? `<span class="badge badge-niche">垂直 ×${c.niche_hits}</span>` : ""}
        ${c.recommend ? `<span class="badge badge-rec">荐</span>` : ""}
      </div>
    </div>`).join("");
  box.querySelectorAll(".cand").forEach((node) => {
    const select = () => {
      box.querySelectorAll(".cand").forEach((x) => x.classList.toggle("sel", x === node));
      S.sel = list[+node.dataset.i]; $("btn-pick").disabled = false;
    };
    node.addEventListener("click", select);
    node.addEventListener("dblclick", () => { select(); pickTopic(S.sel); });
    node.addEventListener("keydown", (e) => e.key === "Enter" && (select(), pickTopic(S.sel)));
  });
}
$("btn-pick").addEventListener("click", (e) => busy(e.currentTarget, () => pickTopic(S.sel)));

async function pickTopic(topic) {
  if (!topic || !S.pid) return;
  const r = await api(`/api/projects/${S.pid}/topic/select`, "POST", { topic });
  if (!r.ok) return toast(r.error || "选定失败", "err");
  S.cands = []; S.sel = null;
  await loadProjects();
  applyProject(r.project, true);
  toast("题目已定，下一步生成简报", "ok");
}

function renderTopicCard(t) {
  show("pv-topic", !!t?.title);
  if (!t?.title) return;
  $("pv-topic-title").textContent = t.title;
  $("pv-topic-meta").innerHTML = [
    t.summary && esc(t.summary.slice(0, 120)),
    [t.source, t.total_score != null && `评分 ${t.total_score}`].filter(Boolean).map(esc).join(" · "),
  ].filter(Boolean).join("<br>");
}

// ── 2. brief + fill ────────────────────────────────────────
$("btn-gen-brief").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  if (!S.project?.topic?.title) return toast("请先选定题目", "err");
  const r = await api(`/api/projects/${S.pid}/brief/generate`, "POST", { extra_notes: $("extra-notes").value.trim() });
  if (!r.ok) return toast(r.error || "生成失败", "err");
  S.brief = r.brief;
  $("brief-preview").textContent = S.brief;
  show("brief-details");
  const ok = await copyText(S.brief);
  $("brief-hint").innerHTML = ok
    ? `✓ 简报已复制（${S.brief.length} 字）。粘给任意 AI，把完整回复贴到下面。`
    : "简报已生成，但自动复制失败，请展开全文手动复制。";
  toast(ok ? "简报已复制到剪贴板" : "请手动复制简报", ok ? "ok" : "err");
  $("ai-paste").focus();
}));

$("ai-paste").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("btn-fill").click();
});
$("btn-fill").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  const txt = $("ai-paste").value.trim();
  if (!txt) return toast("请先粘贴 AI 回复", "err");
  const r = await api(`/api/projects/${S.pid}/draft/fill`, "POST", { ai_output: txt });
  if (!r.ok) return toast(r.error || "解析失败", "err");
  await afterDraft(r, "回填完成，下一步一键生产");
}));

$("btn-write").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  if (!S.project?.topic?.title) return toast("请先选定题目", "err");
  const log = $("write-log");
  const t0 = Date.now();
  log.innerHTML = `<li class="run">${esc(S.llm.model)} 正在写稿… <span id="write-sec">0</span>s</li>`;
  const tick = setInterval(() => { const el = $("write-sec"); if (el) el.textContent = Math.round((Date.now() - t0) / 1000); }, 1000);
  let r;
  try {
    r = await api(`/api/projects/${S.pid}/draft/write`, "POST", { extra_notes: $("extra-notes").value.trim() }, 360000);
  } finally { clearInterval(tick); }
  const sec = Math.round((Date.now() - t0) / 1000);
  if (!r.ok) {
    log.innerHTML = `<li class="err">✕ ${esc(r.error || "生成失败")}</li>`;
    return toast("生成失败，可改用外部 AI", "err");
  }
  log.innerHTML = `<li class="ok">✓ ${esc(r.model)} 用时 ${sec}s</li>`;
  await afterDraft(r, "全文已生成，下一步一键生产");
}));

async function afterDraft(r, msg) {
  const d = r.project.draft || {};
  const en = r.enriched || {};
  const added = Object.entries({ 氛围图: en.mood, 框架图: en.figure, 数据图: en.chart })
    .filter(([, n]) => n).map(([k, n]) => `${k}×${n}`).join("、");
  const st = $("fill-status");
  st.className = "fill-status " + (r.parsed_ok ? "ok" : "warn");
  st.textContent = r.parsed_ok
    ? `✓ 公众号 ${d.wechat_md?.length || 0} 字 · 小红书 ${d.xhs_md?.length || 0} 字` + (added ? ` · 自动补位 ${added}` : "")
    : "⚠ 没识别到标记块，已把整段当作公众号正文（小红书卡片会跳过）";
  await loadProjects();
  applyProject(r.project, true);
  toast(msg, "ok");
}

function renderDraftCard(d, meta) {
  show("pv-draft", !!d?.wechat_md);
  if (!d?.wechat_md) return;
  $("pv-draft-stats").innerHTML = [
    [meta?.word_count ?? d.wechat_md.length, meta ? "公众号字数" : "公众号稿长"], [d.xhs_md?.length || 0, "小红书字数"],
    [d.figures?.length || 0, "框架图"], [d.charts?.length || 0, "数据图"],
  ].map(([v, k]) => `<div class="pv-stat"><span class="sv">${v}</span><span class="sk">${k}</span></div>`).join("");
  $("pv-xhs-titles").innerHTML = (d.xhs_titles || []).map((t) => `<div class="pv-xhs-title">${esc(t)}</div>`).join("");
  $("pv-tags").innerHTML = (d.xhs_tags || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
}

// ── 3. produce ─────────────────────────────────────────────
function logLines(lines) {
  $("media-log").innerHTML = lines.map(([cls, t]) => `<li class="${cls}">${esc(t)}</li>`).join("");
}
$("btn-produce").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  if (!S.project?.draft?.wechat_md) return toast("请先回填稿件", "err");
  logLines([["run", "配图生成中（框架图 / 氛围图 / 数据图 / 小红书卡片）…"]]);
  const mr = await api(`/api/projects/${S.pid}/media/generate`, "POST", {});
  if (!mr.ok) { logLines([["err", "✗ 配图失败：" + (mr.error || "")]]); return toast("配图失败", "err"); }
  const lines = mediaLines(mr.project.media);
  logLines([...lines, ["run", "排版中…"]]);
  applyProject(mr.project);
  await doRender(lines);
}));
$("btn-rerender").addEventListener("click", (e) => busy(e.currentTarget, () => doRender([])));

function mediaLines(m) {
  const man = m?.manifest || [];
  const okN = man.filter((x) => x.ok).length;
  const lines = [[okN === man.length ? "ok" : "err", `配图 ${okN}/${man.length}`]];
  man.filter((x) => !x.ok).forEach((x) => lines.push(["err", `  ✗ ${x.type}:${x.key} ${(x.log || "").slice(0, 60)}`]));
  const cardN = (m?.cards || []).length;
  lines.push([cardN ? "ok" : "", cardN ? `小红书卡片 ${cardN} 张` : "小红书卡片：跳过（无小红书稿）"]);
  return lines;
}
async function doRender(prev) {
  const rr = await api(`/api/projects/${S.pid}/render`, "POST", {});
  if (!rr.ok) { logLines([...prev, ["err", "✗ 排版失败：" + (rr.error || "")]]); return toast("排版失败", "err"); }
  const meta = rr.project.render?.meta || {};
  logLines([...prev, ["ok", `排版完成：${meta.word_count || 0} 字 · ${meta.sections || 0} 节 · ${meta.images || 0} 图`]]);
  await loadProjects();
  applyProject(rr.project, true);
  toast("终版已生成，右侧预览", "ok");
}

function renderOutput(p) {
  const htmlUrl = p?.render?.html_url;
  const man = p?.media?.manifest || [];
  const cards = p?.media?.card_urls || [];
  show("pv-output", !!(htmlUrl || man.length));
  if (!htmlUrl && !man.length) return;
  const frame = $("pv-frame");
  if (htmlUrl) {
    const src = htmlUrl + "?t=" + encodeURIComponent(p.updated || "");
    if (frame.dataset.src !== src) { frame.src = src; frame.dataset.src = src; }
    $("pv-render-link").href = htmlUrl;
  }
  $("xhs-count").textContent = cards.length ? `(${cards.length})` : "";
  $("media-count").textContent = man.length ? `(${man.filter((x) => x.ok).length}/${man.length})` : "";
  $("pv-cards").innerHTML = cards.length
    ? cards.map((u, i) => `<img src="${esc(u)}" alt="小红书卡片 ${i + 1}" data-cap="卡片 ${i + 1}/${cards.length}" loading="lazy">`).join("")
    : `<div class="empty-note">还没有小红书卡片</div>`;
  $("pv-thumbs").innerHTML = man.map((x) => x.ok && x.url
    ? `<div class="pv-thumb" data-url="${esc(x.url)}" data-cap="${esc(x.caption || x.key)}"><img src="${esc(x.url)}" alt="${esc(x.caption)}" loading="lazy"><div class="pt-label">${esc(x.type)} · ${esc(x.caption || x.key)}</div></div>`
    : `<div class="pv-thumb fail"><div class="pt-fail">生成失败<br>${esc((x.log || "").slice(0, 60))}</div><div class="pt-label">${esc(x.type)}:${esc(x.key)}</div></div>`).join("");
}

document.querySelector(".tabs").addEventListener("click", (e) => {
  const t = e.target.closest(".tab"); if (!t) return;
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  document.querySelectorAll(".tab-pane").forEach((x) => x.classList.toggle("hidden", x.dataset.pane !== t.dataset.tab));
});

// ── editor ─────────────────────────────────────────────────
$("btn-edit").addEventListener("click", () => {
  S.edField = "wechat_md";
  $("ed-seg").querySelectorAll(".seg").forEach((x) => x.classList.toggle("active", x.dataset.f === S.edField));
  $("ed-text").value = S.project?.draft?.[S.edField] || "";
  $("editor").showModal();
});
$("ed-seg").addEventListener("click", (e) => {
  const b = e.target.closest(".seg"); if (!b) return;
  S.project.draft[S.edField] = $("ed-text").value; // keep unsaved edits when switching
  S.edField = b.dataset.f;
  $("ed-seg").querySelectorAll(".seg").forEach((x) => x.classList.toggle("active", x === b));
  $("ed-text").value = S.project.draft[S.edField] || "";
});
$("ed-save").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  S.project.draft[S.edField] = $("ed-text").value;
  const { wechat_md, xhs_md } = S.project.draft;
  const r = await api(`/api/projects/${S.pid}/draft`, "POST", { wechat_md, xhs_md });
  if (!r.ok) return toast(r.error || "保存失败", "err");
  $("editor").close();
  applyProject(r.project);
  await doRender([["ok", "稿件已保存"]]);
}));

// ── 4. review + publish ────────────────────────────────────
function renderReview(p) {
  const meta = p?.render?.meta;
  const d = p?.draft || {};
  if (!meta) { $("review-list").innerHTML = `<li>完成第 3 步后在这里自检</li>`; return; }
  const items = [
    [meta.word_count >= 1500, `正文 ${meta.word_count} 字` + (meta.word_count < 1500 ? "（偏短，建议 2500+）" : "")],
    [meta.missing_images === 0, meta.missing_images ? `${meta.missing_images} 张配图失败，可编辑稿件删掉对应占位符` : `配图 ${meta.images} 张全部到位`],
    [meta.has_close, meta.has_close ? "结尾互动块已加" : "缺少结尾互动块 [CLOSE]…[/CLOSE]"],
    [true, meta.finance ? "财经题，页脚已自动加免责声明" : "非财经题，无需免责声明"],
    [(d.xhs_titles || []).length > 0, (d.xhs_titles || []).length ? `小红书标题：${d.xhs_titles[0]}` : "缺少小红书标题"],
    [(p.media?.cards || []).length > 0, `小红书卡片 ${(p.media?.cards || []).length} 张`],
  ];
  $("review-list").innerHTML = items.map(([ok, t]) => `<li class="${ok ? "ok" : "warn"}">${esc(t)}</li>`).join("");
}

const pubAction = (id, path, okMsg) => $(id).addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  const r = await api(`/api/projects/${S.pid}/${path}`, "POST", {});
  toast(r.msg || (r.ok ? okMsg : r.error || "操作失败"), r.ok ? "ok" : "err");
  if (r.ok && S.project?.stage === "review") {
    const a = await api(`/api/projects/${S.pid}/approve`, "POST", {});
    if (a.ok) { applyProject(a.project); loadProjects(); }
  }
}));
pubAction("btn-wc-copy", "publish/wechat/copy", "富文本已复制，去公众号编辑器 Ctrl+V");
pubAction("btn-wc-open", "publish/wechat/open", "已打开公众号后台（首次需扫码）");
pubAction("btn-xhs-copy", "publish/xhs/copy", "文案已复制");
pubAction("btn-xhs-open", "publish/xhs/open", "已打开小红书创作平台（首次需扫码）");

$("btn-export").addEventListener("click", (e) => { if (!S.pid) { e.preventDefault(); requirePid(); } });
$("btn-archive").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  const r = await api(`/api/projects/${S.pid}/archive`, "POST", {});
  if (!r.ok) return toast(r.error || "归档失败", "err");
  await loadProjects(); applyProject(r.project);
  toast("已归档，交付清单已写入项目目录", "ok");
}));

// ── lightbox ───────────────────────────────────────────────
function openLightbox(url, cap) {
  $("lb-img").src = url; $("lb-cap").textContent = cap || "";
  $("lb-overlay").hidden = false;
}
$("lb-overlay").addEventListener("click", () => ($("lb-overlay").hidden = true));
document.addEventListener("keydown", (e) => e.key === "Escape" && ($("lb-overlay").hidden = true));
document.addEventListener("click", (e) => {
  const t = e.target.closest(".pv-thumb[data-url], .pv-cards img");
  if (t) openLightbox(t.dataset.url || t.src, t.dataset.cap);
});

// ── init ───────────────────────────────────────────────────
(async function init() {
  await Promise.all([loadHealth(), loadProjects()]);
  if (S.projects.length) await openProject(S.projects[0].id);
  else applyProject(null);
  setInterval(loadHealth, 60000);
})();

// ── theme ──────────────────────────────────────────────────
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem("jzs-theme", t);
  document.querySelectorAll("#theme-pick button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
}
document.querySelectorAll("#theme-pick button").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.t)));
setTheme(document.documentElement.dataset.theme || "ink");
