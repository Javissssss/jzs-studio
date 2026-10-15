"use strict";
/* 一稿 · 内容工作台
   左：流程导航   中：当前步骤操作   右：实时预览
   单一数据源：后端返回的 project -> applyProject() 渲染全部 UI。
   长任务（写稿 / 配图）走后台 job，前端轮询 /api/jobs/<id>。 */

const $ = (id) => document.getElementById(id);
const S = { pid: null, projects: [], mode: "direct", cands: [], sel: null, project: null,
  step: "topic", wEngine: localStorage.getItem("yg-w") || "api", health: {}, edField: "wechat_md", slotTarget: 0 };

// ── api ──
async function api(path, method = "GET", body = null, { timeout = 60000, form = null } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const opt = { method, signal: ctrl.signal };
    if (form) opt.body = form;
    else if (body !== null) { opt.headers = { "Content-Type": "application/json" }; opt.body = JSON.stringify(body); }
    const r = await fetch(path, opt);
    return await r.json().catch(() => ({ ok: false, error: `服务返回异常 (HTTP ${r.status})` }));
  } catch (e) {
    return { ok: false, error: e.name === "AbortError" ? "请求超时，请重试" : "连不上服务：" + e.message };
  } finally { clearTimeout(timer); }
}

// ── utils ──
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const show = (id, on = true) => $(id)?.classList.toggle("hidden", !on);
let _tt;
function toast(msg, kind = "") {
  const t = $("toast"); t.textContent = msg; t.className = "toast show " + kind;
  clearTimeout(_tt); _tt = setTimeout(() => (t.className = "toast " + kind), 3000);
}
async function busy(btn, fn) {
  if (btn.disabled) return;
  const old = btn.innerHTML; btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span>${esc(btn.textContent.trim())}`;
  try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = old; }
}
async function copyText(txt) {
  try { await navigator.clipboard.writeText(txt); return true; } catch { /* fallback */ }
  const ta = Object.assign(document.createElement("textarea"), { value: txt });
  ta.style.cssText = "position:fixed;opacity:0"; document.body.appendChild(ta); ta.select();
  const ok = document.execCommand("copy"); ta.remove(); return ok;
}
const requirePid = () => S.pid || (toast("先新建一个项目", "err"), false);

// ── background job runner with live console ──
async function runJob(startPath, body, consoleId) {
  const box = $(consoleId), log = box.querySelector("ol"), status = box.querySelector(".console-h span:first-child"),
    sec = box.querySelector(".console-h span:last-child");
  show(consoleId); log.innerHTML = ""; status.textContent = "运行中…"; status.className = ""; sec.textContent = "";
  const r = await api(startPath, "POST", body);
  if (!r.ok) { status.textContent = "✕ 未启动"; status.className = "err"; log.innerHTML = `<li class="err">${esc(r.error)}</li>`; return null; }
  let since = 0, job = r.job;
  while (job.status === "running") {
    await new Promise((res) => setTimeout(res, 1200));
    const p = await api(`/api/jobs/${job.id}?since=${since}`);
    if (!p.ok) { await new Promise((res) => setTimeout(res, 2000)); continue; }
    job = p.job;
    job.log.forEach((l) => log.insertAdjacentHTML("beforeend", `<li class="${/✗|失败|error/i.test(l) ? "err" : ""}">${esc(l)}</li>`));
    since = job.log_total; log.scrollTop = log.scrollHeight;
    sec.textContent = `${Math.round(job.elapsed)}s`;
  }
  if (job.status === "error") {
    status.textContent = "✕ 失败"; status.className = "err";
    log.insertAdjacentHTML("beforeend", `<li class="err">${esc(job.error)}</li>`); log.scrollTop = log.scrollHeight;
    return null;
  }
  status.textContent = `✓ 完成`; status.className = "ok";
  return job.result || {};
}

// ── health & engines ──
async function loadHealth() {
  const h = await api("/api/health"); if (!h.ok) return;
  S.health = h; renderPerspState();
  const items = [
    ["写作 API", h.llm?.configured, h.llm?.configured ? h.llm.model : "未配置"],
    ["Codex", h.codex?.available, h.codex?.available ? "已找到 codex 命令" : "未安装"],
    ["生图 API", h.imagegen?.configured, h.imagegen?.configured ? h.imagegen.model : "未配置"],
    ["截图", h.playwright, "Playwright：框架图 / 卡片截图"],
  ];
  $("health-bar").innerHTML = items.map(([n, on, tip]) =>
    `<span class="h-item" title="${esc(tip)}"><span class="h-dot ${on ? "on" : ""}"></span>${n}</span>`).join("");
  const st = (id, on, okT, offT) => { const el = $(id); el.className = (el.tagName === "I" ? "" : "engine-state ") + (on ? "ok" : "off"); el.innerHTML = on ? okT : offT; };
  st("es-api", h.llm?.configured, `✓ 已就绪：${esc(h.llm.model)}，约 1–3 分钟`, `未配置写作 API。<a data-open-settings>去设置</a> 填 Base URL / Key / 模型`);
  st("es-codex", h.codex?.available, `✓ 已找到 Codex${h.codex.model ? "（" + esc(h.codex.model) + "）" : ""}，约 2–6 分钟。首次使用需在终端执行 codex login`,
    `没找到 codex 命令。终端执行 <code>npm i -g @openai/codex</code> 再 <code>codex login</code>，或在 <a data-open-settings>设置</a> 填 <code>npx -y @openai/codex</code>`);
  st("ie-stock", h.pexels_key || true, h.pexels_key ? "✓ Pexels 已配置" : "✓ 可用（未配 Pexels 时用 Openverse）", "");
  st("ie-ai", h.imagegen?.configured, `✓ ${esc(h.imagegen?.model || "")}`, "未配置，去设置填写");
  st("ie-codex", h.codex?.available, "✓ 已找到 codex", "未安装 codex");
  updateWriteBtn();
}
function updateWriteBtn() {
  const e = S.wEngine, h = S.health;
  const ready = e === "paste" || (e === "api" && h.llm?.configured) || (e === "codex" && h.codex?.available);
  $("btn-write").textContent = e === "paste" ? "解析并回填" : e === "codex" ? "让 Codex 写稿" : "AI 写全文";
  $("btn-write").disabled = !ready;
}
document.addEventListener("click", (e) => { if (e.target.closest("[data-open-settings]")) { e.preventDefault(); openSettings(); } });

// ── projects ──
async function loadProjects() {
  const r = await api("/api/projects");
  S.projects = r.projects || [];
  $("proj-sel").innerHTML = S.projects.length
    ? S.projects.map((p) => `<option value="${esc(p.id)}">${esc(p.title || "未命名")} · ${esc(p.stage_label)}</option>`).join("")
    : `<option value="">还没有项目</option>`;
  if (S.pid) $("proj-sel").value = S.pid;
}
async function openProject(pid, focus = true) {
  const r = await api("/api/projects/" + pid);
  if (r.ok) { S.cands = []; S.sel = null; applyProject(r.project, focus); }
}
async function refresh(focus = false) { if (S.pid) { await openProject(S.pid, focus); await loadProjects(); } }
async function newProject() {
  const r = await api("/api/projects", "POST", { title: "未命名" });
  if (!r.ok) return toast(r.error || "新建失败", "err");
  S.pid = r.project.id; await loadProjects(); applyProject(r.project, true);
}
$("proj-sel").addEventListener("change", (e) => e.target.value && openProject(e.target.value));
$("btn-new").addEventListener("click", newProject);
$("btn-start").addEventListener("click", newProject);
$("btn-del").addEventListener("click", async () => {
  if (!S.pid || !confirm("删除该项目及全部产出？不可恢复。")) return;
  await api("/api/projects/" + S.pid, "DELETE");
  S.pid = null; await loadProjects();
  if (S.projects.length) await openProject(S.projects[0].id); else applyProject(null);
  toast("已删除");
});

// ── navigation ──
const STEPS = ["topic", "write", "media", "publish"];
function goStep(step) {
  S.step = step;
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("hidden", !S.project || p.dataset.panel !== step));
  document.querySelectorAll("#steps li").forEach((li) => li.classList.toggle("cur", !!S.project && li.dataset.step === step));
  $("work")?.scrollTo?.(0, 0);
}
document.querySelectorAll("#steps li").forEach((li) => li.addEventListener("click", () => S.project && goStep(li.dataset.step)));

function applyProject(p, autoFocus = false) {
  S.project = p; S.pid = p?.id || null;
  const has = { topic: !!p?.topic?.title, draft: !!p?.draft?.wechat_md, render: !!p?.render?.html_url, done: p?.stage === "done" };
  show("empty", !p);
  const doneMap = { topic: has.topic, write: has.draft, media: has.render, publish: has.done };
  document.querySelectorAll("#steps li").forEach((li) => li.classList.toggle("done", !!p && doneMap[li.dataset.step]));
  const man = p?.media?.manifest || [];
  $("st-topic").textContent = has.topic ? p.topic.title : "热榜 / 手动 / 直接给题";
  $("st-write").textContent = has.draft ? `公众号 ${p.draft.wechat_md.length} 字` : "API · Codex · 粘贴";
  $("st-media").textContent = has.render ? `配图 ${man.filter((x) => x.ok).length}/${man.length} · 已排版` : "图库 · AI 生图 · Codex";
  $("st-publish").textContent = has.done ? "已归档" : "自检 · 复制 · 导出";
  $("write-topic").textContent = has.topic ? "题目：" + p.topic.title : "请先在第 1 步选定题目";

  renderTopicCard(p?.topic); renderDraftCard(p?.draft, p?.render?.meta); renderOutput(p); renderSlots(p); renderReview(p);
  $("btn-export").href = p ? `/api/projects/${p.id}/export.zip` : "#";
  $("btn-edit").disabled = !has.draft; $("btn-rerender").disabled = !has.draft || !man.length;
  if (!S.cands.length) { $("cand-list").innerHTML = ""; show("pick-row", false); show("niche-wrap", false); }
  if (autoFocus || !p) goStep(!p ? "topic" : !has.topic ? "topic" : !has.draft ? "write" : !has.render ? "media" : "publish");
}

// ── 1. topic ──
const MODE_HINT = { weibo: "微博实时热搜", toutiao: "今日头条热榜", baidu: "百度实时热搜" };
function renderModeInputs() {
  const c = $("mode-inputs");
  if (MODE_HINT[S.mode]) c.innerHTML = `<p class="muted">抓取${MODE_HINT[S.mode]} Top 50，按账号定位（AI · 财经 · 效率）打分排序。</p>`;
  else if (S.mode === "manual") c.innerHTML = `<textarea class="ta" id="manual-input" rows="6" placeholder="每行一个题目，可以写成「标题 | 摘要」"></textarea>`;
  else c.innerHTML = `<input class="input" id="direct-title" placeholder="文章标题，例如：降息之后，普通人的钱该放哪">
    <textarea class="ta" id="direct-sum" rows="3" placeholder="背景素材 / 想表达的观点（可选，越具体写得越好）"></textarea>`;
  $("btn-fetch").textContent = S.mode === "direct" ? "使用这个题目" : S.mode === "manual" ? "打分排序" : "抓取并打分";
}
$("mode-seg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  $("mode-seg").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  S.mode = b.dataset.m; renderModeInputs();
});
renderModeInputs();

$("btn-fetch").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  const body = { mode: S.mode, limit: 50 };
  if (S.mode === "manual") body.text = $("manual-input").value;
  if (S.mode === "direct") {
    body.title = $("direct-title").value.trim(); body.summary = $("direct-sum").value.trim();
    if (!body.title) return toast("请填写标题", "err");
  }
  const r = await api(`/api/projects/${S.pid}/topics/fetch`, "POST", body);
  if (!r.ok) return toast(r.error || "抓取失败，可换个来源或直接给题", "err");
  S.cands = r.candidates || [];
  if (S.mode === "direct" && S.cands.length) return pickTopic(S.cands[0]);
  renderCandidates(); toast(`拿到 ${S.cands.length} 个候选`, "ok");
}));
$("niche-only").addEventListener("change", renderCandidates);

function renderCandidates() {
  const list = S.cands.filter((c) => !$("niche-only").checked || c.niche_hits > 0);
  show("niche-wrap", S.cands.length > 0); show("pick-row", S.cands.length > 0);
  S.sel = null; $("btn-pick").disabled = true;
  const box = $("cand-list");
  if (!list.length) { box.innerHTML = `<div class="empty-note">${S.cands.length ? "没有垂直相关的题，取消勾选看全部" : "没有候选题"}</div>`; return; }
  box.innerHTML = list.map((c, i) => `<div class="cand" data-i="${i}" tabindex="0">
      <div class="cand-rank">${c.rank || i + 1}</div>
      <div class="cand-body"><div class="cand-t">${esc(c.title)}</div>${c.summary ? `<div class="cand-s">${esc(c.summary)}</div>` : ""}</div>
      <div class="cand-badges"><span class="badge">${c.total_score || 0} 分</span>
        ${c.niche_hits ? `<span class="badge badge-niche">垂直×${c.niche_hits}</span>` : ""}${c.recommend ? `<span class="badge badge-rec">荐</span>` : ""}</div>
    </div>`).join("");
  box.querySelectorAll(".cand").forEach((node) => {
    const select = () => { box.querySelectorAll(".cand").forEach((x) => x.classList.toggle("sel", x === node)); S.sel = list[+node.dataset.i]; $("btn-pick").disabled = false; };
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
  S.cands = []; S.sel = null; await loadProjects(); applyProject(r.project, true);
  toast("题目已定，开始写稿", "ok");
}
function renderTopicCard(t) {
  show("pv-topic", !!t?.title); if (!t?.title) return;
  $("pv-topic-title").textContent = t.title;
  $("pv-topic-meta").innerHTML = [t.summary && esc(t.summary.slice(0, 160)),
    [t.source, t.total_score != null && `评分 ${t.total_score}`].filter(Boolean).map(esc).join(" · ")].filter(Boolean).join("<br>");
}

// ── 2. write: api / codex / paste ──
function setWEngine(w) {
  S.wEngine = w; localStorage.setItem("yg-w", w);
  $("write-seg").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x.dataset.w === w));
  document.querySelectorAll("[data-wbox]").forEach((b) => b.classList.toggle("hidden", b.dataset.wbox !== w));
  updateWriteBtn();
}
$("write-seg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) setWEngine(b.dataset.w); });
setWEngine(S.wEngine);

$("btn-gen-brief").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  if (!S.project?.topic?.title) return toast("请先选定题目", "err");
  const r = await api(`/api/projects/${S.pid}/brief/generate`, "POST", { extra_notes: $("extra-notes").value.trim() });
  if (!r.ok) return toast(r.error || "生成失败", "err");
  $("brief-preview").textContent = r.brief; show("brief-details");
  const ok = await copyText(r.brief);
  $("brief-hint").textContent = ok ? `✓ 已复制 ${r.brief.length} 字，粘给任意 AI` : "自动复制失败，请展开全文手动复制";
  $("ai-paste").focus();
}));
$("ai-paste").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("btn-write").click(); });

$("btn-write").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  if (!S.project?.topic?.title) return toast("请先选定题目", "err");
  if (S.wEngine === "paste") {
    const txt = $("ai-paste").value.trim(); if (!txt) return toast("请先粘贴 AI 回复", "err");
    const r = await api(`/api/projects/${S.pid}/draft/fill`, "POST", { ai_output: txt });
    if (!r.ok) return toast(r.error || "解析失败", "err");
    return afterDraft(r);
  }
  const res = await runJob(`/api/projects/${S.pid}/draft/write`, { engine: S.wEngine, extra_notes: $("extra-notes").value.trim(), perspective: $("w-persp-on").checked ? "complexity" : "",
    persp_level: $("w-persp-on").checked ? S.perspLevel : "off", persp_paras: +$("w-persp-paras").value || 2,
    words: +$("w-words").value || 0, images: +$("w-images").value || 0 }, "write-console");
  if (!res) return toast("写稿失败，看下方日志", "err");
  await afterDraft(res);
}));

async function afterDraft(r) {
  const en = r.enriched || {};
  const added = Object.entries({ 氛围图: en.mood, 框架图: en.figure, 数据图: en.chart }).filter(([, n]) => n).map(([k, n]) => `${k}×${n}`).join("、");
  await refresh(false);
  const d = S.project.draft || {};
  const st = $("fill-status");
  st.className = "note " + (r.parsed_ok ? "ok" : "warn");
  st.textContent = r.parsed_ok
    ? `✓ ${r.model ? r.model + " · " : ""}公众号 ${d.wechat_md?.length || 0} 字 · 小红书 ${d.xhs_md?.length || 0} 字` + (added ? ` · 自动补了配图位：${added}` : "")
    : "⚠ 没识别到标记块，整段当作公众号正文（小红书卡片会跳过）。可点「编辑稿件」补充";
  toast("稿件就绪，下一步配图排版", "ok");
  setTimeout(() => goStep("media"), 900);
}
function renderDraftCard(d, meta) {
  show("pv-draft-stats", !!d?.wechat_md); if (!d?.wechat_md) return;
  $("pv-draft-stats").innerHTML = [[meta?.word_count ?? d.wechat_md.length, "公众号字数"], [d.xhs_md?.length || 0, "小红书字数"],
    [d.figures?.length || 0, "框架图"], [d.charts?.length || 0, "数据图"]]
    .map(([v, k]) => `<div class="pv-stat"><span class="sv">${v}</span><span class="sk">${k}</span></div>`).join("");
  $("pv-xhs-titles").innerHTML = (d.xhs_titles || []).map((t) => `<div class="pv-xhs-title">${esc(t)}</div>`).join("");
  $("pv-tags").innerHTML = (d.xhs_tags || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
}

// ── 3. media ──
const imgEngine = () => document.querySelector('input[name="img-eng"]:checked').value;
document.querySelectorAll('input[name="img-eng"]').forEach((r) => {
  if (r.value === localStorage.getItem("yg-img")) r.checked = true;
  r.addEventListener("change", () => localStorage.setItem("yg-img", r.value));
});
$("btn-produce").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  if (!S.project?.draft?.wechat_md) return toast("请先写稿", "err");
  const res = await runJob(`/api/projects/${S.pid}/produce`, { image_engine: imgEngine() }, "media-console");
  await refresh(false);
  if (!res) return toast("生产失败，看日志", "err");
  toast("终版已生成，右侧预览", "ok");
}));
$("btn-rerender").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  const r = await api(`/api/projects/${S.pid}/render`, "POST", {});
  if (!r.ok) return toast(r.error || "排版失败", "err");
  applyProject(r.project); toast("已重新排版", "ok");
}));

const ENGINE_LABEL = { template: "模板", stock: "图库", ai: "AI 生图", codex: "Codex", manual: "手动", none: "已移除" };
function renderSlots(p) {
  const man = p?.media?.manifest || [];
  $("slot-count").textContent = man.length ? `${man.filter((x) => x.ok).length}/${man.length}` : "";
  if (!man.length) { $("slots").innerHTML = `<div class="muted">一键生产后这里会列出每个配图位</div>`; return; }
  $("slots").innerHTML = man.map((x, i) => `<div class="slot" tabindex="0" data-idx="${i + 1}">
      ${x.ok && x.url ? `<div class="slot-img" data-url="${esc(x.url)}" data-cap="${esc(x.caption || x.key)}"><img src="${esc(x.url)}?t=${esc(p.updated)}" alt="${esc(x.caption)}" loading="lazy"></div>`
        : `<div class="slot-img fail">${esc(x.log || "没有图片").slice(0, 80)}</div>`}
      <div class="slot-meta"><span class="cap" title="${esc(x.caption)}">${i + 1}. ${esc(x.caption || x.key)}</span>
        <span class="tags"><span class="tag">${esc(x.type)}</span><span class="tag ${x.engine === "manual" ? "manual" : ""}">${ENGINE_LABEL[x.engine] || x.engine || ""}</span></span></div>
      <div class="slot-act"><button data-act="up">替换</button><button data-act="paste">粘贴</button>${x.ok ? `<button data-act="rm">移除</button>` : ""}</div>
    </div>`).join("");
}
$("slots").addEventListener("click", async (e) => {
  const slot = e.target.closest(".slot"); if (!slot) return;
  const idx = +slot.dataset.idx, act = e.target.closest("[data-act]")?.dataset.act;
  if (act === "up") { S.slotTarget = idx; $("slot-file").value = ""; $("slot-file").click(); }
  else if (act === "paste") { slot.focus(); await pasteFromClipboard(idx); }
  else if (act === "rm") {
    const r = await api(`/api/projects/${S.pid}/media/slot/${idx}`, "DELETE");
    if (r.ok) { applyProject(r.project); toast("已移除，重新生产会自动补图"); } else toast(r.error, "err");
  } else if (e.target.closest(".slot-img[data-url]")) { const t = e.target.closest(".slot-img"); openLightbox(t.dataset.url, t.dataset.cap); }
});
$("slot-file").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  await uploadSlot(S.slotTarget, { form: fd });
});
async function uploadSlot(idx, { form = null, dataUrl = null }) {
  toast("上传中…");
  const r = form ? await api(`/api/projects/${S.pid}/media/slot/${idx}`, "POST", null, { form })
    : await api(`/api/projects/${S.pid}/media/slot/${idx}`, "POST", { data_url: dataUrl });
  if (!r.ok) return toast(r.error || "上传失败", "err");
  applyProject(r.project); toast(`配图位 ${idx} 已替换并重新排版`, "ok");
}
const blobToDataUrl = (b) => new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
async function pasteFromClipboard(idx) {
  try {
    for (const item of await navigator.clipboard.read()) {
      const type = item.types.find((t) => t.startsWith("image/"));
      if (type) return uploadSlot(idx, { dataUrl: await blobToDataUrl(await item.getType(type)) });
    }
    toast("剪贴板里没有图片", "err");
  } catch { toast("浏览器不让直接读剪贴板：选中这张卡片后按 Ctrl+V", "err"); }
}
document.addEventListener("paste", async (e) => {
  const slot = document.activeElement?.closest?.(".slot"); if (!slot) return;
  const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/")); if (!file) return;
  e.preventDefault(); await uploadSlot(+slot.dataset.idx, { dataUrl: await blobToDataUrl(file) });
});

function renderOutput(p) {
  const htmlUrl = p?.render?.html_url, cards = p?.media?.card_urls || [];
  show("pv-article-empty", !htmlUrl);
  const frame = $("pv-frame");
  if (htmlUrl) {
    const src = htmlUrl + "?t=" + encodeURIComponent(p.updated || "");
    if (frame.dataset.src !== src) { frame.src = src; frame.dataset.src = src; }
    $("pv-render-link").href = htmlUrl;
  } else { frame.removeAttribute("src"); frame.dataset.src = ""; }
  show("pv-render-link", !!htmlUrl);
  const single = p?.render?.single_url, sl = $("pv-single-link");
  sl.hidden = !single; if (single) sl.href = single;
  const cv = $("pv-cover"), cu = p?.render?.cover_url;
  cv.hidden = !cu; if (cu) cv.src = cu + "?t=" + encodeURIComponent(p.updated || "");
  $("xhs-count").textContent = cards.length ? `${cards.length}` : "";
  $("pv-cards").innerHTML = cards.length
    ? cards.map((u, i) => `<img src="${esc(u)}?t=${esc(p.updated)}" alt="小红书卡片 ${i + 1}" data-cap="卡片 ${i + 1}/${cards.length}" loading="lazy">`).join("")
    : `<div class="empty-note">一键生产后生成小红书卡片</div>`;
}
document.querySelector(".tabs").addEventListener("click", (e) => {
  const t = e.target.closest("button"); if (!t) return;
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === t));
  document.querySelectorAll(".pane").forEach((x) => x.classList.toggle("hidden", x.dataset.pane !== t.dataset.tab));
});

// ── perspective (复杂系统专家): off by default, user decides per article ──
S.perspLevel = "concept";
function syncPersp() {
  const on = $("w-persp-on").checked;
  show("persp-opts", on);
  show("persp-paras-w", S.perspLevel === "concept");
}
$("w-persp-on").addEventListener("change", syncPersp);
$("persp-level").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  S.perspLevel = b.dataset.l;
  $("persp-level").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  syncPersp();
});
function renderPerspState() {
  const p = (S.health?.perspectives || []).find((x) => x.key === "complexity");
  const st = $("persp-state"); if (!st) return;
  if (!p?.installed) { st.textContent = "· 未找到框架包（perspectives/）"; $("w-persp-on").disabled = true; return; }
  $("w-persp-on").disabled = false;
  st.textContent = p.macro_key ? "· 宏观数据已接入" : "· 宏观数据未配置（设置里填 ATTRACTOR_API_KEY，可选）";
}
syncPersp();

// ── editor ──
$("btn-edit").addEventListener("click", () => {
  S.edField = "wechat_md";
  $("ed-seg").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x.dataset.f === S.edField));
  $("ed-text").value = S.project?.draft?.[S.edField] || ""; $("editor").showModal();
});
$("ed-seg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  S.project.draft[S.edField] = $("ed-text").value; S.edField = b.dataset.f;
  $("ed-seg").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  $("ed-text").value = S.project.draft[S.edField] || "";
});
$("ed-cancel").addEventListener("click", () => $("editor").close());
$("ed-explain").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  const ta = $("ed-text"), sel = ta.value.slice(ta.selectionStart, ta.selectionEnd).trim();
  const term = ($("ed-term").value.trim() || sel).slice(0, 60);
  if (!term) return toast("先输入或选中一个概念", "err");
  const pos = ta.selectionEnd || ta.value.length;
  const r = await api("/api/perspective/explain", "POST",
    { perspective: "complexity", term, context: ta.value.slice(Math.max(0, pos - 600), pos) }, { timeout: 150000 });
  if (!r.ok) return toast(r.error || "生成失败", "err");
  const lineEnd = ta.value.indexOf("\n", pos), at = lineEnd < 0 ? ta.value.length : lineEnd;
  ta.value = ta.value.slice(0, at) + "\n\n" + r.text.trim() + "\n" + ta.value.slice(at);
  ta.focus(); ta.setSelectionRange(at + 2, at + 2 + r.text.trim().length);
  toast("已插入，确认后点「保存并重新排版」", "ok");
}));
$("ed-save").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  S.project.draft[S.edField] = $("ed-text").value;
  const { wechat_md, xhs_md } = S.project.draft;
  const r = await api(`/api/projects/${S.pid}/draft`, "POST", { wechat_md, xhs_md });
  if (!r.ok) return toast(r.error || "保存失败", "err");
  $("editor").close();
  if (S.project.media?.manifest?.length) await api(`/api/projects/${S.pid}/render`, "POST", {});
  await refresh(false); toast("已保存", "ok");
}));

// ── 4. publish ──
function renderReview(p) {
  const meta = p?.render?.meta, d = p?.draft || {};
  if (!meta) { $("review-list").innerHTML = `<li>完成第 3 步后在这里自检</li>`; return; }
  const cardsN = (p.media?.cards || []).length;
  const items = [
    [meta.word_count >= 1500, `正文 ${meta.word_count} 字` + (meta.word_count < 1500 ? "（偏短，建议 2500+）" : "")],
    [meta.missing_images === 0, meta.missing_images ? `${meta.missing_images} 张配图缺失：去第 3 步替换或移除` : `配图 ${meta.images} 张全部到位`],
    [meta.has_close, meta.has_close ? "结尾互动块已加" : "缺少结尾互动块 [CLOSE]…[/CLOSE]"],
    [true, meta.finance ? "财经题，页脚已加免责声明" : "非财经题，无需免责声明"],
    [(d.xhs_titles || []).length > 0, (d.xhs_titles || []).length ? `小红书标题：${d.xhs_titles[0]}` : "缺少小红书标题"],
    [cardsN > 0, `小红书卡片 ${cardsN} 张`],
  ];
  $("review-list").innerHTML = items.map(([ok, t]) => `<li class="${ok ? "ok" : "warn"}">${esc(t)}</li>`).join("");
}
const pubAction = (id, path, okMsg) => $(id).addEventListener("click", (e) => busy(e.currentTarget, async () => {
  if (!requirePid()) return;
  const r = await api(`/api/projects/${S.pid}/${path}`, "POST", {});
  toast(r.msg || (r.ok ? okMsg : r.error || "操作失败"), r.ok ? "ok" : "err");
  if (r.ok && S.project?.stage === "review") { await api(`/api/projects/${S.pid}/approve`, "POST", {}); refresh(false); }
}));
$("btn-wc-draft").onclick = async () => {
  if (!S.health?.wechat_mp?.configured) { toast("先在「设置」里填公众号 AppID / AppSecret", "err"); return; }
  const res = await runJob(`/api/projects/${S.pid}/publish/wechat/draft`, {}, "pub-console");
  if (res) toast("已存入公众号草稿箱，去后台「草稿箱」查看", "ok");
};
pubAction("btn-wc-copy", "publish/wechat/copy", "富文本已复制，去公众号编辑器 Ctrl+V");
pubAction("btn-wc-open", "publish/wechat/open", "已打开公众号后台（首次需扫码）");
pubAction("btn-xhs-copy", "publish/xhs/copy", "文案已复制");
pubAction("btn-xhs-open", "publish/xhs/open", "已打开小红书创作平台（首次需扫码）");
$("btn-export").addEventListener("click", (e) => { if (!S.pid) { e.preventDefault(); requirePid(); } });
$("btn-archive").addEventListener("click", (e) => busy(e.currentTarget, async () => {
  const r = await api(`/api/projects/${S.pid}/archive`, "POST", {});
  if (!r.ok) return toast(r.error || "归档失败", "err");
  await loadProjects(); applyProject(r.project); toast("已归档", "ok");
}));

// ── settings ──
async function openSettings() {
  const r = await api("/api/settings"); if (!r.ok) return toast(r.error, "err");
  const groups = { JZS_BRAND: "full", JZS_LLM_BASE_URL: "full", JZS_IMG_BASE_URL: "full", JZS_CODEX_CMD: "full" };
  $("settings-fields").innerHTML = r.settings.map((f) => `<label class="${groups[f.key] || ""}">
      <span>${esc(f.label)} ${f.secret && f.set ? `<span class="set-badge">● 已设置</span>` : ""}</span>
      <input class="input" name="${esc(f.key)}" type="${f.secret ? "password" : "text"}" autocomplete="off"
        value="${esc(f.value)}" placeholder="${f.secret ? (f.set ? "留空不修改" : "未设置") : ""}">
    </label>`).join("");
  $("settings").showModal();
}
$("btn-settings").addEventListener("click", openSettings);
$("settings-save").addEventListener("click", async (e) => {
  e.preventDefault();
  const vals = {}; $("settings-fields").querySelectorAll("input").forEach((i) => (vals[i.name] = i.value));
  const r = await api("/api/settings", "POST", vals);
  if (!r.ok) return toast(r.error || "保存失败", "err");
  $("settings").close(); toast("设置已保存", "ok"); loadHealth();
});

// ── lightbox / theme ──
function openLightbox(url, cap) { $("lb-img").src = url; $("lb-cap").textContent = cap || ""; $("lb").hidden = false; }
$("lb").addEventListener("click", () => ($("lb").hidden = true));
document.addEventListener("keydown", (e) => e.key === "Escape" && ($("lb").hidden = true));
document.addEventListener("click", (e) => { const t = e.target.closest(".cards img"); if (t) openLightbox(t.src, t.dataset.cap); });
$("btn-theme").addEventListener("click", () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = t; localStorage.setItem("yg-theme", t);
});

// ── init ──
(async function init() {
  await Promise.all([loadHealth(), loadProjects()]);
  if (S.projects.length) await openProject(S.projects[0].id); else applyProject(null);
  setInterval(loadHealth, 60000);
})();
