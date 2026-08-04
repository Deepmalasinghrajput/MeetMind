/* ═══════════════════════════════════════════════════════════════
   MeetMind — script.js
   Pipeline, history, timestamps, PDF, follow-up email, RAG chat
═══════════════════════════════════════════════════════════════ */

"use strict";

const state = {
  activePanel: "input",
  activeTab: "youtube",
  selectedFile: null,
  sessionData: null,
  isProcessing: false,
  chatHistory: [],
  searchMatches: [],
  searchIdx: 0,
  user: null,
  authMode: "login",
};

const PIPELINE_STEPS = [
  { id: "input",      progId: "prog-input",      wfId: "wf-input",      label: "Media Processing", pct: 15 },
  { id: "transcribe", progId: "prog-transcribe", wfId: "wf-transcribe", label: "Transcription",    pct: 40 },
  { id: "title",      progId: "prog-title",      wfId: "wf-title",      label: "Title Generation", pct: 55 },
  { id: "summary",    progId: "prog-summary",    wfId: "wf-summary",    label: "Summarization",    pct: 70 },
  { id: "extract",    progId: "prog-extract",    wfId: "wf-extract",    label: "AI Extraction",    pct: 85 },
  { id: "rag",        progId: "prog-rag",        wfId: "wf-rag",        label: "RAG Knowledge",    pct: 100 },
];

const STEP_NUMBERS = {
  "prog-input": "1",
  "prog-transcribe": "2",
  "prog-title": "3",
  "prog-summary": "4",
  "prog-extract": "5",
  "prog-rag": "6",
};

document.addEventListener("DOMContentLoaded", async () => {
  setupNavigation();
  setupFileUpload();
  setupUrlInput();
  setupChatInput();
  setupUserMenu();
  renderInsightSkeletons(false);
  setInsightsEmpty(true);
  updateMeetingChrome();
  await bootstrapAuth();
});

/* ── Auth ── */
async function bootstrapAuth() {
  try {
    const res = await fetch("/api/auth/me");
    const data = await res.json();
    if (data.authenticated && data.user) {
      enterApp(data.user);
    } else {
      showAuthGate();
    }
  } catch {
    showAuthGate();
  }
}

function showAuthGate() {
  state.user = null;
  const gate = document.getElementById("authGate");
  const app = document.getElementById("appShell");
  if (gate) {
    gate.classList.remove("hidden");
    gate.style.display = "flex";
  }
  if (app) app.style.display = "none";
  showAuthMode("login");
}

function enterApp(user) {
  state.user = user;
  const gate = document.getElementById("authGate");
  const app = document.getElementById("appShell");
  if (gate) {
    gate.classList.add("hidden");
    gate.style.display = "none";
  }
  if (app) app.style.display = "flex";
  updateUserChip(user);
  checkServerReady();
  loadMeetingHistory();
  switchPanel("history");
}

function updateUserChip(user) {
  const name = user?.name || "User";
  const email = user?.email || "";
  const initial = (name.trim().charAt(0) || "U").toUpperCase();
  const nameEl = document.getElementById("userName");
  const emailEl = document.getElementById("userEmail");
  const av = document.getElementById("userAvatar");
  if (nameEl) nameEl.textContent = name;
  if (emailEl) emailEl.textContent = email;
  if (av) av.textContent = initial;

  const popName = document.getElementById("userPopName");
  const popEmail = document.getElementById("userPopEmail");
  const popAv = document.getElementById("userPopAvatar");
  if (popName) popName.textContent = name;
  if (popEmail) popEmail.textContent = email;
  if (popAv) popAv.textContent = initial;
}

function setupUserMenu() {
  const chip = document.getElementById("userChip");
  const menu = document.getElementById("userMenu");
  const popout = document.getElementById("userPopout");
  if (!chip || !menu || !popout) return;

  chip.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = menu.classList.toggle("open");
    chip.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) popout.hidden = false;
    else popout.hidden = true;
  });

  document.addEventListener("click", (e) => {
    if (!menu.contains(e.target)) closeUserMenu();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeUserMenu();
  });
}

function closeUserMenu() {
  const menu = document.getElementById("userMenu");
  const chip = document.getElementById("userChip");
  const popout = document.getElementById("userPopout");
  if (menu) menu.classList.remove("open");
  if (chip) chip.setAttribute("aria-expanded", "false");
  if (popout) popout.hidden = true;
}

function showAuthMode(mode) {
  state.authMode = mode === "register" ? "register" : "login";
  const isReg = state.authMode === "register";
  document.getElementById("tabLogin")?.classList.toggle("active", !isReg);
  document.getElementById("tabRegister")?.classList.toggle("active", isReg);
  const nameField = document.getElementById("nameField");
  const nameInput = document.getElementById("authName");
  if (nameField) nameField.style.display = isReg ? "block" : "none";
  if (nameInput) {
    nameInput.required = isReg;
    if (!isReg) nameInput.value = nameInput.value; // keep value
  }
  const title = document.getElementById("authTitle");
  const sub = document.getElementById("authSub");
  const submit = document.getElementById("authSubmit");
  const pw = document.getElementById("authPassword");
  if (title) title.textContent = isReg ? "Create your account" : "Welcome back";
  if (sub) sub.textContent = isReg
    ? "Sign up to save and organize your meetings"
    : "Sign in to access your meeting notes";
  if (submit) submit.textContent = isReg ? "Create account" : "Sign in";
  if (pw) pw.autocomplete = isReg ? "new-password" : "current-password";
  hideAuthError();
}

function hideAuthError() {
  const el = document.getElementById("authError");
  if (el) {
    el.style.display = "none";
    el.textContent = "";
  }
}

function showAuthError(msg) {
  const el = document.getElementById("authError");
  if (el) {
    el.textContent = msg || "Something went wrong";
    el.style.display = "block";
  }
}

async function submitAuth(e) {
  e.preventDefault();
  hideAuthError();
  const email = document.getElementById("authEmail")?.value.trim() || "";
  const password = document.getElementById("authPassword")?.value || "";
  const name = document.getElementById("authName")?.value.trim() || "";
  const btn = document.getElementById("authSubmit");
  const isRegister = state.authMode === "register";
  if (btn) {
    btn.disabled = true;
    btn.textContent = isRegister ? "Creating…" : "Signing in…";
  }
  try {
    if (isRegister && !name) {
      throw new Error("Please enter your full name.");
    }
    if (!email || !password) {
      throw new Error("Email and password are required.");
    }
    if (password.length < 6) {
      throw new Error("Password must be at least 6 characters.");
    }

    const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";
    const body = isRegister ? { name, email, password } : { email, password };
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    const raw = await res.text();
    let data = {};
    try { data = raw ? JSON.parse(raw) : {}; } catch { /* non-JSON body */ }

    if (res.status === 404) {
      throw new Error(
        "Auth API not found (404). Stop all old python app.py processes and start one fresh server."
      );
    }
    if (!res.ok) {
      throw new Error(data.error || `Authentication failed (${res.status})`);
    }
    if (!data.user || !data.user.id) {
      throw new Error("Server did not return a user session. Restart python app.py and try again.");
    }
    enterApp(data.user);
    showToast(isRegister ? "Account created" : "Signed in", "success");
  } catch (err) {
    showAuthError(err.message || "Authentication failed");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = isRegister ? "Create account" : "Sign in";
    }
  }
  return false;
}

async function logoutUser() {
  closeUserMenu();
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch { /* ignore */ }
  state.user = null;
  state.sessionData = null;
  state.chatHistory = [];
  _meetingLibraryCache = [];
  showAuthGate();
  showToast("Signed out", "success");
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    showAuthGate();
    showToast("Please sign in again", "error");
    throw new Error("Authentication required");
  }
  return res;
}

async function checkServerReady() {
  try {
    const res = await fetch("/ready");
    const data = await res.json();
    if (!data.ready) {
      const hint = data.message || "Server setup incomplete";
      updateSidebarStatus("error", "Setup needed");
      showToast(hint, "error");
      const banner = document.getElementById("setupBanner");
      if (banner) {
        banner.style.display = "flex";
        banner.querySelector(".setup-banner-text").textContent = hint;
      }
    } else {
      updateSidebarStatus("idle", "Ready");
      const banner = document.getElementById("setupBanner");
      if (banner) banner.style.display = "none";
    }
  } catch {
    updateSidebarStatus("error", "Server offline");
    showToast("Cannot reach server. Run: python app.py", "error");
  }
}

function setupNavigation() {
  document.querySelectorAll("[data-panel]").forEach(btn => {
    btn.addEventListener("click", () => {
      const panel = btn.dataset.panel;
      if (!panel) return;
      switchPanel(panel);
      if (panel === "history") loadMeetingHistory();
      // Close mobile drawer after navigation
      if (window.matchMedia("(max-width: 960px)").matches) {
        closeMobileSidebar();
      }
    });
  });

  document.getElementById("exportBtn")?.addEventListener("click", () => {
    openExportModal();
    if (window.matchMedia("(max-width: 960px)").matches) closeMobileSidebar();
  });

  document.getElementById("sidebarToggle")?.addEventListener("click", () => {
    document.getElementById("sidebar")?.classList.toggle("collapsed");
  });

  document.getElementById("mobileMenuBtn")?.addEventListener("click", openMobileSidebar);
  document.getElementById("sidebarClose")?.addEventListener("click", closeMobileSidebar);
  document.getElementById("sidebarOverlay")?.addEventListener("click", closeMobileSidebar);

  window.addEventListener("resize", () => {
    if (!window.matchMedia("(max-width: 960px)").matches) {
      closeMobileSidebar();
    }
  });
}

function openMobileSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  document.body.classList.add("nav-open");
  sidebar?.classList.add("mobile-open");
  if (overlay) {
    overlay.hidden = false;
    requestAnimationFrame(() => overlay.classList.add("show"));
  }
}

function closeMobileSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  document.body.classList.remove("nav-open");
  sidebar?.classList.remove("mobile-open");
  if (overlay) {
    overlay.classList.remove("show");
    setTimeout(() => { if (!overlay.classList.contains("show")) overlay.hidden = true; }, 200);
  }
}

function switchPanel(panelId) {
  state.activePanel = panelId;
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const el = document.getElementById("panel" + capitalize(panelId));
  if (el) el.classList.add("active");

  document.querySelectorAll(".nav-item[data-panel]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.panel === panelId);
  });
  document.querySelectorAll(".ff-tab[data-panel]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.panel === panelId);
  });
  updateTopbarForPanel(panelId);
  updateMeetingChrome();
}

function updateTopbarForPanel(panelId) {
  const kicker = document.getElementById("topKicker");
  const title = document.getElementById("meetingTitleDisplay");
  if (!kicker || !title) return;

  const savedTitle = state.sessionData?.title;
  const labels = {
    history: { kicker: "Meetings", title: "Your meeting library" },
    input: { kicker: "Transcribe", title: "Import a meeting" },
    insights: { kicker: "AI Notes", title: savedTitle || "Meeting notes" },
    transcript: { kicker: "Transcript", title: savedTitle || "Meeting transcript" },
    chat: { kicker: "Ask AI", title: savedTitle || "Chat with your meeting" },
  };
  const L = labels[panelId] || labels.history;
  kicker.textContent = L.kicker;
  if (panelId === "history" || panelId === "input" || !savedTitle) {
    title.textContent = L.title;
  } else if (savedTitle) {
    title.textContent = savedTitle;
  }
}

function updateMeetingChrome() {
  const tabs = document.getElementById("meetingTabs");
  if (!tabs) return;
  const hasMeeting = !!(state.sessionData?.transcript || state.sessionData?.summary || state.sessionData?.title);
  tabs.style.display = hasMeeting ? "flex" : "none";
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".input-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
  document.getElementById("tab" + capitalize(tab)).classList.add("active");
  document.getElementById("content" + capitalize(tab)).classList.add("active");
}

function setupFileUpload() {
  const dropZone = document.getElementById("fileDropZone");
  const fileInput = document.getElementById("fileInput");

  dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
  dropZone.addEventListener("drop", e => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  });
  dropZone.addEventListener("click", e => {
    if (e.target.closest(".file-preview-remove")) return;
    fileInput.click();
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) setSelectedFile(fileInput.files[0]);
  });
}

function setSelectedFile(file) {
  state.selectedFile = file;
  document.getElementById("fileDropContent").style.display = "none";
  document.getElementById("fileSelectedContent").style.display = "block";
  document.getElementById("filePreviewName").textContent = file.name;
  document.getElementById("filePreviewSize").textContent = formatBytes(file.size);
}

function clearFile() {
  state.selectedFile = null;
  document.getElementById("fileInput").value = "";
  document.getElementById("fileDropContent").style.display = "block";
  document.getElementById("fileSelectedContent").style.display = "none";
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function setupUrlInput() {
  const inp = document.getElementById("youtubeUrl");
  const clr = document.getElementById("urlClear");
  inp.addEventListener("input", () => {
    clr.style.display = inp.value.length ? "block" : "none";
  });
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      startPipeline();
    }
  });
}

function clearUrl() {
  document.getElementById("youtubeUrl").value = "";
  document.getElementById("urlClear").style.display = "none";
}

async function startPipeline() {
  if (state.isProcessing) return;

  let source = "";
  if (state.activeTab === "youtube") {
    source = document.getElementById("youtubeUrl").value.trim();
    if (!source) { showToast("Enter a YouTube URL first", "error"); return; }
    if (!source.includes("youtube.com") && !source.includes("youtu.be")) {
      showToast("Doesn't look like a YouTube URL", "error"); return;
    }
  } else if (!state.selectedFile) {
    showToast("Select a media file first", "error"); return;
  }

  const language = document.querySelector("input[name='language']:checked")?.value || "english";
  updateLanguageBadge(language);

  state.isProcessing = true;
  setProcessingUI(true);
  showProgressCard();
  hideErrorCard();

  try {
    let response;
    if (state.activeTab === "youtube") {
      response = await apiFetch("/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, language }),
      });
    } else {
      const formData = new FormData();
      formData.append("file", state.selectedFile);
      formData.append("language", language);
      response = await apiFetch("/process", { method: "POST", body: formData });
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: "Server error" }));
      if (response.status === 401 || err.auth_required) {
        throw new Error("Authentication required");
      }
      throw new Error(err.error || `HTTP ${response.status}`);
    }

    const data = await response.json();
    state.sessionData = data;
    handlePipelineSuccess(data);
    loadMeetingHistory();
  } catch (err) {
    const msg = err.message || "Processing failed";
    if (msg === "Failed to fetch" || msg.includes("NetworkError")) {
      handlePipelineError(
        "Lost connection to the server. Keep python app.py running, then try again."
      );
    } else {
      handlePipelineError(msg);
    }
  }
}

let progressInterval = null;
let currentStepIdx = 0;

function showProgressCard() {
  document.getElementById("progressCard").style.display = "block";
  currentStepIdx = 0;
  resetAllSteps();
  advanceStep();
  progressInterval = setInterval(() => {
    if (currentStepIdx < PIPELINE_STEPS.length - 1) {
      currentStepIdx++;
      advanceStep();
    }
  }, 3200);
}

function advanceStep() {
  for (let i = 0; i < currentStepIdx; i++) markStepDone(PIPELINE_STEPS[i]);
  markStepActive(PIPELINE_STEPS[currentStepIdx]);
  updateProgressBar(PIPELINE_STEPS[currentStepIdx].pct * 0.9);
}

function markStepActive(step) {
  const el = document.getElementById(step.progId);
  if (!el) return;
  el.className = "prog-step active";
  el.querySelector(".prog-step-icon").textContent = STEP_NUMBERS[step.progId] || "•";
  el.querySelector(".prog-step-status").textContent = "Running…";
  const wf = document.getElementById(step.wfId);
  if (wf) {
    document.querySelectorAll(".workflow-step").forEach(w => w.classList.remove("active"));
    wf.classList.add("active");
  }
  updateSidebarStatus("running", step.label);
}

function markStepDone(step) {
  const el = document.getElementById(step.progId);
  if (!el) return;
  el.className = "prog-step done";
  el.querySelector(".prog-step-icon").textContent = "✓";
  el.querySelector(".prog-step-status").textContent = "Done";
  const wf = document.getElementById(step.wfId);
  if (wf) wf.classList.add("done");
}

function resetAllSteps() {
  PIPELINE_STEPS.forEach(step => {
    const el = document.getElementById(step.progId);
    if (!el) return;
    el.className = "prog-step";
    el.querySelector(".prog-step-icon").textContent = STEP_NUMBERS[step.progId] || "•";
    el.querySelector(".prog-step-status").textContent = "—";
    const wf = document.getElementById(step.wfId);
    if (wf) wf.classList.remove("active", "done");
  });
  updateProgressBar(0);
}

function updateProgressBar(pct) {
  document.getElementById("progressBar").style.width = pct + "%";
}

function completeAllSteps() {
  clearInterval(progressInterval);
  PIPELINE_STEPS.forEach(markStepDone);
  updateProgressBar(100);
  document.querySelector(".workflow-step:last-child")?.classList.add("done");
  updateSidebarStatus("done", "Complete");
}

function handlePipelineSuccess(data) {
  completeAllSteps();
  state.isProcessing = false;
  setProcessingUI(false);
  setTimeout(() => {
    document.getElementById("progressCard").style.display = "none";
    populateResults(data);
    enableResultNavigation();
    // Fireflies flow: land on AI Notes after transcription
    switchPanel("insights");
    loadMeetingHistory();
    showToast("Meeting notes ready", "success");
  }, 900);
}

function populateResults(data) {
  if (data) state.sessionData = { ...state.sessionData, ...data };

  const display = document.getElementById("meetingTitleDisplay");
  if (display) display.textContent = data.title || "Meeting Recording";

  if (data.transcript || (data.segments && data.segments.length)) {
    document.getElementById("transcriptEmpty").style.display = "none";
    document.getElementById("transcriptText").style.display = "block";
    renderTranscriptView();
  }

  setInsightsEmpty(false);
  renderInsightSkeletons(false);
  fillInsight("summaryContent", data.summary || "No summary available.");
  fillInsight("actionsContent", data.action_items || "No action items identified.");
  fillInsight("decisionsContent", data.key_decisions || "No key decisions identified.");
  fillInsight("questionsContent", data.open_questions || "No open questions identified.");

  const emailCard = document.getElementById("cardEmail");
  if (emailCard) emailCard.style.display = "none";

  updateStatsPills(data.stats);
  if (data.stats?.language) updateLanguageBadge(data.stats.language);
  if (data.language) updateLanguageBadge(data.language);

  if (data.rag_ready) enableChat();
  else {
    document.getElementById("chatEmpty").style.display = "block";
    document.getElementById("chatContainer").style.display = "none";
  }

  updateMeetingChrome();
  updateTopbarForPanel(state.activePanel || "insights");
}

function updateStatsPills(stats) {
  const wrap = document.getElementById("statsPills");
  if (!wrap) return;
  if (!stats) {
    wrap.style.display = "none";
    return;
  }
  wrap.style.display = "flex";
  const words = stats.word_count || 0;
  const segs = stats.segment_count || 0;
  const secs = Math.round(stats.duration_seconds || 0);
  const mm = Math.floor(secs / 60);
  const ss = String(secs % 60).padStart(2, "0");
  document.getElementById("statWords").textContent = `${words} words`;
  document.getElementById("statDuration").textContent = `${mm}:${ss}`;
  document.getElementById("statSegments").textContent = `${segs} segs`;
}

function renderTranscriptView() {
  const container = document.getElementById("transcriptText");
  if (!container || !state.sessionData) return;

  const showTs = document.getElementById("showTimestamps")?.checked ?? true;
  const segments = state.sessionData.segments || [];
  const raw = state.sessionData.transcript || "";

  if (showTs && segments.length) {
    container.classList.add("has-segments");
    container.innerHTML = segments.map(seg => {
      const ts = escapeHtml(seg.timestamp || formatSec(seg.start));
      const text = escapeHtml(seg.text || "");
      return `<div class="transcript-seg"><span class="ts">${ts}</span><span class="seg-text">${text}</span></div>`;
    }).join("");
  } else {
    container.classList.remove("has-segments");
    container.textContent = raw;
  }
}

function formatSec(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  const m = Math.floor(s / 60);
  const r = String(s % 60).padStart(2, "0");
  return `${m}:${r}`;
}

function fillInsight(id, content) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  const lines = String(content).split("\n").filter(l => l.trim());
  if (lines.length > 1) {
    const ul = document.createElement("ul");
    ul.style.cssText = "padding-left:18px;display:flex;flex-direction:column;gap:8px;";
    lines.forEach(line => {
      const li = document.createElement("li");
      li.style.cssText = "color:var(--text-secondary);font-size:13.5px;line-height:1.7;";
      li.textContent = line.replace(/^[-•*\d.)]+\s*/, "");
      ul.appendChild(li);
    });
    el.appendChild(ul);
  } else {
    el.textContent = content;
  }
}

function enableResultNavigation() {
  document.getElementById("exportBtn").disabled = false;
  showToast("Meeting processed successfully", "success");
}

function enableChat() {
  document.getElementById("chatEmpty").style.display = "none";
  document.getElementById("chatContainer").style.display = "flex";
}

function handlePipelineError(msg) {
  clearInterval(progressInterval);
  state.isProcessing = false;
  setProcessingUI(false);
  document.getElementById("progressCard").style.display = "none";
  document.getElementById("errorMsg").textContent = msg;
  document.getElementById("errorCard").style.display = "flex";
  updateSidebarStatus("error", "Failed");
  showToast("Processing failed", "error");
}

function resetError() {
  hideErrorCard();
  resetAllSteps();
}
function hideErrorCard() {
  document.getElementById("errorCard").style.display = "none";
}

function setProcessingUI(on) {
  const btn = document.getElementById("processBtn");
  btn.disabled = on;
  btn.innerHTML = on
    ? `<div class="spinner" style="width:14px;height:14px;border-width:2px;"></div> Analyzing…`
    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 3l14 9-14 9V3z" fill="currentColor"/></svg> Analyze Meeting`;

  document.getElementById("processingPill").style.display = on ? "flex" : "none";
  if (on) animatePillText();
}

const PILL_MESSAGES = ["Processing…", "Transcribing…", "Extracting…", "Building RAG…"];
let pillMsgIdx = 0;
let pillInterval = null;
function animatePillText() {
  pillMsgIdx = 0;
  clearInterval(pillInterval);
  pillInterval = setInterval(() => {
    pillMsgIdx = (pillMsgIdx + 1) % PILL_MESSAGES.length;
    document.getElementById("processingPillText").textContent = PILL_MESSAGES[pillMsgIdx];
  }, 3000);
}

function updateSidebarStatus(_type, _label) {
  /* Status indicator removed from sidebar; processing shows in top bar. */
}

function updateLanguageBadge(lang) {
  document.getElementById("currentLang").textContent =
    String(lang).toLowerCase() === "hinglish" ? "HIN" : "EN";
}

function setInsightsEmpty(empty) {
  const grid = document.querySelector(".insights-grid");
  const emptyEl = document.getElementById("insightsEmpty");
  if (grid) grid.style.display = empty ? "none" : "grid";
  if (emptyEl) emptyEl.style.display = empty ? "flex" : "none";
}

function renderInsightSkeletons(show) {
  ["summaryContent", "actionsContent", "decisionsContent", "questionsContent"].forEach(id => {
    const el = document.getElementById(id);
    if (!el || !show) return;
    el.innerHTML = `<div class="insight-skeleton">
      <div class="skeleton-line w80"></div>
      <div class="skeleton-line w90"></div>
      <div class="skeleton-line w70"></div>
    </div>`;
  });
}

function searchTranscript(query) {
  const container = document.getElementById("transcriptText");
  const countEl = document.getElementById("searchCount");
  const raw = state.sessionData?.transcript || "";
  const segments = state.sessionData?.segments || [];
  const showTs = document.getElementById("showTimestamps")?.checked ?? true;

  if (!query.trim()) {
    renderTranscriptView();
    countEl.style.display = "none";
    return;
  }

  const regex = new RegExp(escapeRegex(query), "gi");

  if (showTs && segments.length) {
    let matches = 0;
    container.innerHTML = segments.map(seg => {
      const text = seg.text || "";
      const segMatches = [...text.matchAll(regex)].length;
      matches += segMatches;
      const highlighted = text.replace(regex, m => `<mark>${m}</mark>`);
      const ts = escapeHtml(seg.timestamp || formatSec(seg.start));
      return `<div class="transcript-seg"><span class="ts">${ts}</span><span class="seg-text">${highlighted}</span></div>`;
    }).join("");
    countEl.style.display = matches ? "inline-block" : "none";
    countEl.textContent = `${matches} match${matches !== 1 ? "es" : ""}`;
  } else {
    const matches = [...raw.matchAll(regex)];
    countEl.style.display = matches.length ? "inline-block" : "none";
    countEl.textContent = `${matches.length} match${matches.length !== 1 ? "es" : ""}`;
    container.innerHTML = escapeHtml(raw).replace(regex, m => `<mark>${m}</mark>`);
  }
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function copyContent(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText || el.textContent)
    .then(() => showToast("Copied to clipboard", "success"))
    .catch(() => showToast("Copy failed", "error"));
}

function copyAllInsights() {
  const d = state.sessionData;
  if (!d) { showToast("No data to copy", "error"); return; }
  const parts = [
    `# ${d.title || "Meeting"}`,
    `\n## Summary\n${d.summary || ""}`,
    `\n## Action Items\n${d.action_items || ""}`,
    `\n## Key Decisions\n${d.key_decisions || ""}`,
    `\n## Open Questions\n${d.open_questions || ""}`,
  ];
  navigator.clipboard.writeText(parts.join("\n"))
    .then(() => showToast("All insights copied", "success"))
    .catch(() => showToast("Copy failed", "error"));
}

async function generateFollowUpEmail() {
  const d = state.sessionData;
  if (!d) { showToast("Process a meeting first", "error"); return; }

  const btn = document.getElementById("emailDraftBtn");
  if (btn) btn.disabled = true;
  showToast("Drafting follow-up email…");

  try {
    const res = await apiFetch("/follow-up-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: d.title,
        summary: d.summary,
        action_items: d.action_items,
        key_decisions: d.key_decisions,
        open_questions: d.open_questions,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to draft email");
    document.getElementById("cardEmail").style.display = "block";
    document.getElementById("emailContent").textContent = data.email;
    d.follow_up_email = data.email;
    switchPanel("insights");
    showToast("Follow-up email ready", "success");
  } catch (err) {
    showToast(err.message || "Email draft failed", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openExportModal() {
  document.getElementById("exportModal").style.display = "grid";
}

function closeExportModal(e) {
  if (e && e.target !== document.getElementById("exportModal")) return;
  document.getElementById("exportModal").style.display = "none";
}

async function exportAs(format) {
  const d = state.sessionData;
  if (!d) { showToast("No data to export", "error"); return; }

  const incTitle = document.getElementById("expTitle").checked;
  const incSummary = document.getElementById("expSummary").checked;
  const incActions = document.getElementById("expActions").checked;
  const incDecisions = document.getElementById("expDecisions").checked;
  const incQuestions = document.getElementById("expQuestions").checked;
  const incTranscript = document.getElementById("expTranscript").checked;
  const title = d.title || "Meeting";

  if (format === "pdf") {
    try {
      const res = await apiFetch("/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          summary: d.summary,
          action_items: d.action_items,
          key_decisions: d.key_decisions,
          open_questions: d.open_questions,
          transcript: d.transcript,
          word_count: d.stats?.word_count,
          duration_seconds: d.stats?.duration_seconds,
          language: d.stats?.language || d.language,
          include_title: incTitle,
          include_summary: incSummary,
          include_actions: incActions,
          include_decisions: incDecisions,
          include_questions: incQuestions,
          include_transcript: incTranscript,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || "PDF export failed");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slugify(title)}_report.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      document.getElementById("exportModal").style.display = "none";
      showToast("Exported as .PDF", "success");
    } catch (err) {
      showToast(err.message || "PDF export failed", "error");
    }
    return;
  }

  let content = "";
  if (format === "json") {
    const obj = {};
    if (incTitle) obj.title = title;
    if (incSummary) obj.summary = d.summary;
    if (incActions) obj.action_items = d.action_items;
    if (incDecisions) obj.key_decisions = d.key_decisions;
    if (incQuestions) obj.open_questions = d.open_questions;
    if (incTranscript) obj.transcript = d.transcript;
    if (d.segments) obj.segments = d.segments;
    content = JSON.stringify(obj, null, 2);
  } else if (format === "md") {
    if (incTitle) content += `# ${title}\n\n`;
    if (incSummary) content += `## Summary\n\n${d.summary}\n\n`;
    if (incActions) content += `## Action Items\n\n${d.action_items}\n\n`;
    if (incDecisions) content += `## Key Decisions\n\n${d.key_decisions}\n\n`;
    if (incQuestions) content += `## Open Questions\n\n${d.open_questions}\n\n`;
    if (incTranscript) content += `## Full Transcript\n\n${d.transcript}\n\n`;
  } else {
    if (incTitle) content += `MEETING: ${title}\n${"=".repeat(60)}\n\n`;
    if (incSummary) content += `SUMMARY\n${"-".repeat(40)}\n${d.summary}\n\n`;
    if (incActions) content += `ACTION ITEMS\n${"-".repeat(40)}\n${d.action_items}\n\n`;
    if (incDecisions) content += `KEY DECISIONS\n${"-".repeat(40)}\n${d.key_decisions}\n\n`;
    if (incQuestions) content += `OPEN QUESTIONS\n${"-".repeat(40)}\n${d.open_questions}\n\n`;
    if (incTranscript) content += `FULL TRANSCRIPT\n${"-".repeat(40)}\n${d.transcript}\n\n`;
  }

  const ext = format === "json" ? "json" : format === "md" ? "md" : "txt";
  const mime = format === "json" ? "application/json" : "text/plain";
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${slugify(title)}_report.${ext}`;
  a.click();
  URL.revokeObjectURL(url);

  document.getElementById("exportModal").style.display = "none";
  showToast(`Exported as .${ext.toUpperCase()}`, "success");
}

function slugify(str) {
  return str.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "").slice(0, 40) || "meeting";
}

/* ── History / Meetings library ── */
let _meetingLibraryCache = [];

async function loadMeetingHistory() {
  const list = document.getElementById("historyList");
  if (!list) return;
  try {
    const res = await apiFetch("/meetings");
    const data = await res.json();
    _meetingLibraryCache = data.meetings || [];
    renderMeetingLibrary(_meetingLibraryCache);
  } catch (err) {
    if (err.message === "Authentication required") return;
    list.innerHTML = `<div class="history-empty"><p>Could not load meetings.</p></div>`;
  }
}

function filterMeetingLibrary(q) {
  const query = (q || "").trim().toLowerCase();
  if (!query) {
    renderMeetingLibrary(_meetingLibraryCache);
    return;
  }
  renderMeetingLibrary(
    _meetingLibraryCache.filter(m =>
      String(m.title || "").toLowerCase().includes(query) ||
      String(m.language || "").toLowerCase().includes(query)
    )
  );
}

function renderMeetingLibrary(meetings) {
  const list = document.getElementById("historyList");
  if (!list) return;
  if (!meetings.length) {
    list.innerHTML = `
      <div class="history-empty" id="historyEmpty">
        <div class="ff-empty-illu" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <path d="M8 10v4M12 8v8M16 11v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            <rect x="3.5" y="4.5" width="17" height="15" rx="3" stroke="currentColor" stroke-width="1.7"/>
          </svg>
        </div>
        <p class="empty-title">No meetings yet</p>
        <p>Upload a recording or paste a YouTube URL to generate notes, action items, and AI Q&amp;A.</p>
        <button class="ff-btn-primary" type="button" data-panel="input" onclick="switchPanel('input')">Transcribe your first meeting</button>
      </div>`;
    return;
  }
  list.innerHTML = meetings.map(m => {
    const secs = Math.round(m.duration_seconds || 0);
    const dur = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
    const date = (m.created_at || "").replace("T", " ").slice(0, 16);
    const initial = escapeHtml(String(m.title || "M").trim().charAt(0).toUpperCase() || "M");
    return `
      <div class="history-item" data-id="${m.id}">
        <div class="history-main" onclick="openMeeting(${m.id})">
          <div class="history-avatar">${initial}</div>
          <div>
            <div class="history-title">${escapeHtml(m.title || "Untitled meeting")}</div>
            <div class="history-meta">${escapeHtml(date)} · ${m.word_count || 0} words · ${dur} · ${escapeHtml((m.language || "en").toUpperCase())}</div>
          </div>
        </div>
        <div class="history-actions">
          <button class="btn-secondary btn-sm" type="button" onclick="openMeeting(${m.id})">Open</button>
          <button class="btn-secondary btn-sm" type="button" onclick="deleteMeeting(${m.id})">Delete</button>
        </div>
      </div>`;
  }).join("");
}

async function openMeeting(id) {
  try {
    showToast("Loading meeting…");
    const res = await apiFetch(`/meetings/${id}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to load");
    state.sessionData = data;
    state.chatHistory = [];
    clearChatKeepEmpty();
    populateResults(data);
    enableResultNavigation();
    if (data.rag_ready) enableChat();
    switchPanel("insights");
    showToast("Meeting loaded", "success");
  } catch (err) {
    showToast(err.message || "Load failed", "error");
  }
}

async function deleteMeeting(id) {
  if (!confirm("Delete this saved meeting?")) return;
  try {
    const res = await apiFetch(`/meetings/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Delete failed");
    if (state.sessionData?.id === id) state.sessionData = null;
    loadMeetingHistory();
    showToast("Meeting deleted", "success");
  } catch (err) {
    showToast(err.message || "Delete failed", "error");
  }
}

function clearChatKeepEmpty() {
  const msgs = document.getElementById("chatMessages");
  if (msgs) {
    msgs.innerHTML = `<div class="chat-system-msg">
      <div class="system-badge">Fred is online</div>
      <p>Ask anything about this meeting transcript.</p>
    </div>`;
  }
}

/* ── RAG chat ── */
function setupChatInput() {
  document.getElementById("chatInput")?.addEventListener("keydown", handleChatKey);
}

function handleChatKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendChatMessage();
  }
}

function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

function sendSuggestion(el) {
  document.getElementById("chatInput").value = el.textContent;
  sendChatMessage();
}

async function sendChatMessage() {
  const inp = document.getElementById("chatInput");
  const question = inp.value.trim();
  if (!question) return;
  if (!state.sessionData?.rag_ready) {
    showToast("Process a meeting first to enable chat", "error");
    return;
  }

  inp.value = "";
  inp.style.height = "auto";
  hideSuggestions();
  appendMessage("user", question);
  const typingEl = appendTyping();

  try {
    const res = await apiFetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    removeTyping(typingEl);
    if (data.error) throw new Error(data.error);
    appendMessage("assistant", data.answer);
  } catch (err) {
    removeTyping(typingEl);
    appendMessage("assistant", err.message);
  }
}

function appendMessage(role, content) {
  const msgs = document.getElementById("chatMessages");
  const avatar = role === "user" ? "You" : "F";
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-bubble">${escapeHtml(content)}</div>
  `;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  state.chatHistory.push({ role, content });
  return div;
}

function appendTyping() {
  const msgs = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = "msg assistant msg-typing";
  div.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-bubble"><div class="typing-dots">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div></div>
  `;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

function removeTyping(el) { el?.remove(); }
function hideSuggestions() {
  const el = document.getElementById("chatSuggestions");
  if (el) el.style.display = "none";
}

function clearChat() {
  clearChatKeepEmpty();
  state.chatHistory = [];
  const sug = document.getElementById("chatSuggestions");
  if (sug) sug.style.display = "flex";
  document.getElementById("chatInput").value = "";
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br>");
}

let toastTimer = null;
function showToast(msg, type = "") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast show${type ? " " + type : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}
