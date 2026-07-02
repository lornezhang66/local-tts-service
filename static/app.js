// 本地 TTS 服务前端：试听 / 配置 / 接入管理。无构建，纯原生 JS。
// 鉴权分层：试听用 API Key（X-API-Key），配置与管理用管理员 session cookie。
const $ = (id) => document.getElementById(id);

// ---------- 通用 ----------
async function api(path, { method = "GET", body, headers } = {}) {
  const opts = { method, headers: { ...(headers || {}) }, credentials: "same-origin" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j.error) msg = j.error; } catch (_) {}
    throw new Error(msg);
  }
  // 204 或非 JSON 直接返回
  const ct = res.headers.get("Content-Type") || "";
  return ct.includes("application/json") ? res.json() : null;
}

function setStatus(el, text, ok = true) {
  if (!el) return;
  el.textContent = text;
  el.style.color = ok ? "#52605b" : "#b00020";
}

function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
}

// 手测 API Key 存 localStorage，避免每次重填
const apiKey = () => localStorage.getItem("tts_api_key") || "";
const setApiKey = (k) => localStorage.setItem("tts_api_key", k);

// ---------- tab 切换 ----------
document.querySelectorAll("nav button").forEach((btn) => {
  btn.onclick = () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll("main > section").forEach((s) => s.classList.toggle("active", s.id === `tab-${tab}`));
    if (tab === "config" && state.loggedIn) loadConfig();
    if (tab === "admin" && state.loggedIn) refreshAdmin();
  };
});

// ---------- 试听 ----------
$("synthKey").value = apiKey();
$("synthKey").oninput = (e) => setApiKey(e.target.value.trim());
$("synthesize").onclick = async () => {
  const key = apiKey();
  if (!key) { setStatus($("synthStatus"), "请先填写 API Key", false); return; }
  $("synthesize").disabled = true;
  setStatus($("synthStatus"), "合成中...");
  try {
    const res = await fetch("/api/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": key },
      body: JSON.stringify({ text: $("text").value }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.error) msg = j.error; } catch (_) {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    $("audio").src = URL.createObjectURL(blob);
    setStatus($("synthStatus"), `完成，时长 ${res.headers.get("X-Audio-Duration") || "?"} 秒`);
  } catch (e) {
    setStatus($("synthStatus"), String(e), false);
  } finally {
    $("synthesize").disabled = false;
  }
};

// ---------- 配置 ----------
const CONFIG_KEYS = ["host", "port", "model_dir", "vocoder", "threads", "speed", "noise_scale", "length_scale", "silence_scale", "max_num_sentences", "cleanup_days", "require_auth"];
const NUM_KEYS = new Set(["port", "threads", "speed", "noise_scale", "length_scale", "silence_scale", "max_num_sentences", "cleanup_days"]);

async function loadConfig() {
  try {
    const cfg = await api("/api/config");
    for (const k of CONFIG_KEYS) {
      const el = $(k);
      if (!el) continue;
      if (el.type === "checkbox") el.checked = !!cfg[k];
      else el.value = cfg[k];
    }
    $("data_dir").value = cfg.data_dir || "";
  } catch (e) {
    setStatus($("configStatus"), `加载失败：${e}`, false);
  }
}

$("saveConfig").onclick = async () => {
  const cfg = {};
  for (const k of CONFIG_KEYS) {
    const el = $(k);
    if (!el) continue;
    cfg[k] = el.type === "checkbox" ? el.checked : (NUM_KEYS.has(k) ? Number(el.value) : el.value);
  }
  try {
    await api("/api/config", { method: "POST", body: cfg });
    setStatus($("configStatus"), "已保存（host/port 改动需重启服务生效）");
  } catch (e) {
    setStatus($("configStatus"), `保存失败：${e}`, false);
  }
};

// ---------- 登录态 ----------
const state = { loggedIn: false, username: "" };

async function checkLogin() {
  try {
    await api("/api/admin/keys");  // 200 即已登录
    state.loggedIn = true;
    state.username = "admin";
  } catch {
    state.loggedIn = false;
  }
  renderAuth();
}

function renderAuth() {
  $("authArea").classList.toggle("hidden", state.loggedIn);
  $("userArea").classList.toggle("hidden", !state.loggedIn);
  if (state.loggedIn) $("welcome").textContent = state.username;
  $("configLocked").classList.toggle("hidden", state.loggedIn);
  $("configForm").classList.toggle("hidden", !state.loggedIn);
  $("adminLocked").classList.toggle("hidden", state.loggedIn);
  $("adminBox").classList.toggle("hidden", !state.loggedIn);
  if (state.loggedIn && document.querySelector("#tab-config.active")) loadConfig();
  if (state.loggedIn && document.querySelector("#tab-admin.active")) refreshAdmin();
}

$("login").onclick = async () => {
  try {
    await api("/api/admin/login", {
      method: "POST",
      body: { username: $("loginUser").value.trim() || "admin", password: $("loginPass").value },
    });
    state.loggedIn = true;
    state.username = $("loginUser").value.trim() || "admin";
    $("loginPass").value = "";
    setStatus($("loginStatus"), "");
    renderAuth();
  } catch (e) {
    setStatus($("loginStatus"), `登录失败：${e}`, false);
  }
};
$("loginPass").addEventListener("keydown", (e) => { if (e.key === "Enter") $("login").click(); });

$("logout").onclick = async () => {
  try { await api("/api/admin/logout", { method: "POST" }); } catch (_) {}
  state.loggedIn = false;
  renderAuth();
};

// ---------- API Key 管理 ----------
async function loadKeys() {
  try {
    const { keys } = await api("/api/admin/keys");
    $("keysBody").innerHTML = keys.map((k) => `
      <tr>
        <td>${k.id}</td>
        <td>${escapeHtml(k.name)}</td>
        <td>${k.created_at}</td>
        <td>${k.last_used_at || "—"}</td>
        <td>${k.enabled ? "启用" : "停用"}</td>
        <td>
          <button class="small" data-toggle="${k.id}" data-enabled="${k.enabled ? 0 : 1}">${k.enabled ? "停用" : "启用"}</button>
          <button class="small danger" data-del="${k.id}">删除</button>
        </td>
      </tr>`).join("");
    $("keysEmpty").classList.toggle("hidden", keys.length > 0);
  } catch (e) {
    setStatus($("adminStatus"), `加载 Key 失败：${e}`, false);
  }
}

// 事件委托：避免 inline onclick
$("keysBody").addEventListener("click", async (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.dataset.toggle) {
    const id = t.dataset.toggle;
    const enabled = t.dataset.enabled === "1";
    await api(`/api/admin/keys/${id}/toggle`, { method: "POST", body: { enabled } });
    loadKeys();
  } else if (t.dataset.del) {
    if (!confirm("确认删除该 Key？删除后该 Key 立即失效。")) return;
    await api(`/api/admin/keys/${t.dataset.del}`, { method: "DELETE" });
    loadKeys();
  }
});

$("newKey").onclick = async () => {
  const name = prompt("新 Key 的名称（便于标识用途，如 obsidian / codex）：", "obsidian");
  if (name === null) return;
  try {
    const r = await api("/api/admin/keys", { method: "POST", body: { name: name || "新建" } });
    alert(`新 Key（仅显示一次，请立即复制）：\n${r.key}`);
    if (confirm("是否填入试听框便于测试？")) { setApiKey(r.key); $("synthKey").value = r.key; }
    loadKeys();
  } catch (e) {
    alert(`新建失败：${e}`);
  }
};

// ---------- 调用记录与磁盘 ----------
async function loadUsage() {
  try {
    const d = await api("/api/admin/usage");
    $("usageCards").innerHTML = d.summary.length
      ? d.summary.map((s) => `
        <div class="card">
          <div class="n">${s.total}</div>
          <div class="l">${escapeHtml(s.name || "匿名")} · 成功 ${s.ok_count} · ${Number(s.total_audio || 0).toFixed(1)}s</div>
        </div>`).join("")
      : '<div class="muted">暂无记录</div>';
    $("usageBody").innerHTML = d.recent.map((u) => `
      <tr>
        <td>${u.ts}</td>
        <td>${escapeHtml(u.name || "匿名")}</td>
        <td>${u.text_len}</td>
        <td>${u.audio_duration != null ? Number(u.audio_duration).toFixed(2) + "s" : "—"}</td>
        <td>${u.latency_ms != null ? u.latency_ms : "—"}</td>
        <td>${u.status}</td>
        <td class="muted">${escapeHtml(u.error || "")}</td>
      </tr>`).join("");
  } catch (_) { /* 静默：调用记录加载失败不打扰 */ }
}

async function loadDisk() {
  try {
    const d = await api("/api/admin/disk");
    $("diskInfo").textContent = `${d.data_dir}  ·  占用 ${fmtBytes(d.bytes)}  ·  调用记录 ${d.usage_count} 条`;
  } catch (_) {}
}

$("cleanup").onclick = async () => {
  try {
    const r = await api("/api/admin/cleanup", { method: "POST" });
    setStatus($("adminStatus"), `已清理 ${r.deleted} 条过期记录，当前占用 ${fmtBytes(r.bytes)}`);
    loadUsage();
  } catch (e) {
    setStatus($("adminStatus"), `清理失败：${e}`, false);
  }
};

async function refreshAdmin() {
  await Promise.all([loadKeys(), loadUsage(), loadDisk()]);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- 启动 ----------
checkLogin();
