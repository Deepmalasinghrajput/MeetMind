/* ═══════════════════════════════════════════════════════════════
   MeetMind — script.js
   Handles: pipeline calls, workflow animation, transcript search,
   RAG chat, copy/export, drag-drop, UI state machine.
═══════════════════════════════════════════════════════════════ */

"use strict";

/* ── STATE ── */
const state = {
  activePanel: "input",
  activeTab: "youtube",
  selectedFile: null,
  sessionData: null,   // Full pipeline result
  isProcessing: false,
  chatHistory: [],
  searchMatches: [],
  searchIdx: 0,
};

/* ── PIPELINE STEP DEFINITIONS ── */
const PIPELINE_STEPS = [
  { id: "input",      progId: "prog-input",     wfId: "wf-input",     label: "Media Processing",      pct: 15  },
  { id: "transcribe", progId: "prog-transcribe", wfId: "wf-transcribe",label: "Whisper Transcription", pct: 40  },
  { id: "title",      progId: "prog-title",      wfId: "wf-title",     label: "Title Generation",      pct: 55  },
  { id: "summary",    progId: "prog-summary",    wfId: "wf-summary",   label: "Summarization",         pct: 70  },
  { id: "extract",    progId: "prog-extract",    wfId: "wf-extract",   label: "AI Extraction",         pct: 85  },
  { id: "rag",        progId: "prog-rag",        wfId: "wf-rag",       label: "RAG Knowledge Base",    pct: 100 },
];

/* ─────────────────────────── INIT ─────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupFileUpload();
  setupUrlInput();
  setupChatInput();
  renderInsightSkeletons(false);
  setInsightsEmpty(true);
});

/* ─────────────────────────── NAVIGATION ─────────────────────────── */
function setupNavigation() {
  document.querySelectorAll(".nav-item[data-panel]").forEach(btn => {
    btn.addEventListener("click", () => {
      const panel = btn.dataset.panel;
      switchPanel(panel);
    });
  });

  document.getElementById("exportBtn").addEventListener("click", openExportModal);
  document.getElementById("sidebarToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("collapsed");
  });
}

function switchPanel(panelId) {
  state.activePanel = panelId;

  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  document.getElementById("panel" + capitalize(panelId)).classList.add("active");

  document.querySelectorAll(".nav-item[data-panel]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.panel === panelId);
  });
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/* ─────────────────────────── TAB SWITCHING ─────────────────────────── */
function switchTab(tab) {
  state.activeTab = tab;

  document.querySelectorAll(".input-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));

  document.getElementById("tab" + capitalize(tab)).classList.add("active");
  document.getElementById("content" + capitalize(tab)).classList.add("active");
}

/* ─────────────────────────── FILE UPLOAD ─────────────────────────── */
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
  const sel = document.getElementById("fileSelectedContent");
  sel.style.display = "block";
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

/* ─────────────────────────── URL INPUT ─────────────────────────── */
function setupUrlInput() {
  const inp = document.getElementById("youtubeUrl");
  const clr = document.getElementById("urlClear");
  inp.addEventListener("input", () => {
    clr.style.display = inp.value.length ? "block" : "none";
  });
}

function clearUrl() {
  document.getElementById("youtubeUrl").value = "";
  document.getElementById("urlClear").style.display = "none";
}

/* ─────────────────────────── PIPELINE START ─────────────────────────── */
async function startPipeline() {
  if (state.isProcessing) return;

  let source = "";
  if (state.activeTab === "youtube") {
    source = document.getElementById("youtubeUrl").value.trim();
    if (!source) { showToast("Enter a YouTube URL first", "error"); return; }
    if (!source.includes("youtube.com") && !source.includes("youtu.be")) {
      showToast("Doesn't look like a YouTube URL", "error"); return;
    }
  } else {
    if (!state.selectedFile) { showToast("Select a media file first", "error"); return; }
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
      response = await fetch("/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, language }),
      });
    } else {
      const formData = new FormData();
      formData.append("file", state.selectedFile);
      formData.append("language", language);
      response = await fetch("/process", { method: "POST", body: formData });
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: "Server error" }));
      throw new Error(err.error || `HTTP ${response.status}`);
    }

    const data = await response.json();
    state.sessionData = data;
    handlePipelineSuccess(data);

  } catch (err) {
    handlePipelineError(err.message);
  }
}

/* ─────────────────────────── PIPELINE PROGRESS SIMULATION ─────────────────────────── */
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
  // Mark previous steps done
  for (let i = 0; i < currentStepIdx; i++) {
    markStepDone(PIPELINE_STEPS[i]);
  }
  // Mark current step active
  const step = PIPELINE_STEPS[currentStepIdx];
  markStepActive(step);
  updateProgressBar(step.pct * 0.9); // stay a bit below 100 until truly done
}

function markStepActive(step) {
  const el = document.getElementById(step.progId);
  if (!el) return;
  el.className = "prog-step active";
  el.querySelector(".prog-step-icon").textContent = "⚙️";
  el.querySelector(".prog-step-status").textContent = "Running…";

  // Workflow banner
  const wf = document.getElementById(step.wfId);
  if (wf) {
    document.querySelectorAll(".workflow-step").forEach(w => w.classList.remove("active"));
    wf.classList.add("active");
  }

  // Sidebar status
  updateSidebarStatus("running", step.label);
}

function markStepDone(step) {
  const el = document.getElementById(step.progId);
  if (!el) return;
  el.className = "prog-step done";
  el.querySelector(".prog-step-icon").textContent = "✅";
  el.querySelector(".prog-step-status").textContent = "Done";

  const wf = document.getElementById(step.wfId);
  if (wf) wf.classList.add("done");
}

function resetAllSteps() {
  PIPELINE_STEPS.forEach(step => {
    const el = document.getElementById(step.progId);
    if (!el) return;
    el.className = "prog-step";
    el.querySelector(".prog-step-icon").textContent = "⏳";
    el.querySelector(".prog-step-status").textContent = "—";
    const wf = document.getElementById(step.wfId);
    if (wf) { wf.classList.remove("active", "done"); }
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
  document.querySelector(".workflow-step:last-child .wf-icon").style.filter = "none";
  updateSidebarStatus("done", "Complete");
}

/* ─────────────────────────── PIPELINE SUCCESS ─────────────────────────── */
function handlePipelineSuccess(data) {
  completeAllSteps();
  state.isProcessing = false;
  setProcessingUI(false);

  setTimeout(() => {
    document.getElementById("progressCard").style.display = "none";
    populateResults(data);
    enableResultNavigation();
    switchPanel("transcript");
  }, 1200);
}

function populateResults(data) {
  // Title
  const title = data.title || "Meeting Recording";
  document.getElementById("meetingTitleDisplay").textContent = title;

  // Transcript
  if (data.transcript) {
    const el = document.getElementById("transcriptText");
    el.textContent = data.transcript;
    el.style.display = "block";
    document.getElementById("transcriptEmpty").style.display = "none";
  }

  // Insights
  setInsightsEmpty(false);
  renderInsightSkeletons(false);

  fillInsight("summaryContent",  data.summary       || "No summary available.");
  fillInsight("actionsContent",  data.action_items  || "No action items identified.");
  fillInsight("decisionsContent",data.key_decisions || "No key decisions identified.");
  fillInsight("questionsContent",data.open_questions|| "No open questions identified.");

  // RAG Chat
  if (data.rag_ready) {
    enableChat();
  }
}

function fillInsight(id, content) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  // Format lists nicely
  const lines = content.split("\n").filter(l => l.trim());
  if (lines.length > 1) {
    const ul = document.createElement("ul");
    ul.style.cssText = "padding-left:18px;display:flex;flex-direction:column;gap:8px;";
    lines.forEach(line => {
      const li = document.createElement("li");
      li.style.cssText = "color:var(--text-secondary);font-size:13.5px;line-height:1.7;";
      li.textContent = line.replace(/^[-•*]\s*/, "");
      ul.appendChild(li);
    });
    el.appendChild(ul);
  } else {
    el.textContent = content;
  }
}

function enableResultNavigation() {
  ["navTranscript", "navInsights", "navChat"].forEach(id => {
    document.getElementById(id)?.classList.remove("disabled");
  });
  document.getElementById("exportBtn").disabled = false;
  showToast("Meeting processed successfully ✓", "success");
}

function enableChat() {
  document.getElementById("chatEmpty").style.display = "none";
  document.getElementById("chatContainer").style.display = "flex";
}

/* ─────────────────────────── PIPELINE ERROR ─────────────────────────── */
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

/* ─────────────────────────── UI HELPERS ─────────────────────────── */
function setProcessingUI(on) {
  const btn = document.getElementById("processBtn");
  btn.disabled = on;
  btn.innerHTML = on
    ? `<div class="spinner" style="width:14px;height:14px;border-width:2px;"></div> Analyzing…`
    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 3l14 9-14 9V3z" fill="currentColor"/></svg> Analyze Meeting`;

  const pill = document.getElementById("processingPill");
  pill.style.display = on ? "flex" : "none";

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

function updateSidebarStatus(type, label) {
  const dot = document.querySelector(".status-dot");
  const span = document.querySelector(".pipeline-status span");
  dot.className = "status-dot " + type;
  if (span) span.textContent = label;
}

function updateLanguageBadge(lang) {
  document.getElementById("currentLang").textContent =
    lang === "hinglish" ? "HIN" : "EN";
}

function setInsightsEmpty(empty) {
  const grid = document.querySelector(".insights-grid");
  const emptyEl = document.getElementById("insightsEmpty");
  if (grid) grid.style.display = empty ? "none" : "grid";
  if (emptyEl) emptyEl.style.display = empty ? "flex" : "none";
}

function renderInsightSkeletons(show) {
  ["summaryContent","actionsContent","decisionsContent","questionsContent"].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (show) {
      el.innerHTML = `<div class="insight-skeleton">
        <div class="skeleton-line w80"></div>
        <div class="skeleton-line w90"></div>
        <div class="skeleton-line w70"></div>
      </div>`;
    }
  });
}

/* ─────────────────────────── TRANSCRIPT SEARCH ─────────────────────────── */
function searchTranscript(query) {
  const container = document.getElementById("transcriptText");
  const countEl = document.getElementById("searchCount");
  const raw = state.sessionData?.transcript || "";

  if (!query.trim() || !raw) {
    container.textContent = raw;
    countEl.style.display = "none";
    return;
  }

  const regex = new RegExp(escapeRegex(query), "gi");
  const matches = [...raw.matchAll(regex)];
  countEl.style.display = matches.length ? "inline-block" : "none";
  countEl.textContent = `${matches.length} match${matches.length !== 1 ? "es" : ""}`;

  container.innerHTML = raw.replace(regex, m => `<mark>${m}</mark>`);
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/* ─────────────────────────── COPY ─────────────────────────── */
function copyContent(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = el.innerText || el.textContent;
  navigator.clipboard.writeText(text)
    .then(() => showToast("Copied to clipboard ✓", "success"))
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
    .then(() => showToast("All insights copied ✓", "success"))
    .catch(() => showToast("Copy failed", "error"));
}

/* ─────────────────────────── EXPORT ─────────────────────────── */
function openExportModal() {
  document.getElementById("exportModal").style.display = "grid";
}

function closeExportModal(e) {
  if (e && e.target !== document.getElementById("exportModal")) return;
  document.getElementById("exportModal").style.display = "none";
}

function exportAs(format) {
  const d = state.sessionData;
  if (!d) { showToast("No data to export", "error"); return; }

  const incTitle     = document.getElementById("expTitle").checked;
  const incSummary   = document.getElementById("expSummary").checked;
  const incActions   = document.getElementById("expActions").checked;
  const incDecisions = document.getElementById("expDecisions").checked;
  const incQuestions = document.getElementById("expQuestions").checked;
  const incTranscript= document.getElementById("expTranscript").checked;

  let content = "";
  const title = d.title || "Meeting";

  if (format === "json") {
    const obj = {};
    if (incTitle)      obj.title = title;
    if (incSummary)    obj.summary = d.summary;
    if (incActions)    obj.action_items = d.action_items;
    if (incDecisions)  obj.key_decisions = d.key_decisions;
    if (incQuestions)  obj.open_questions = d.open_questions;
    if (incTranscript) obj.transcript = d.transcript;
    content = JSON.stringify(obj, null, 2);
  } else if (format === "md") {
    if (incTitle)      content += `# ${title}\n\n`;
    if (incSummary)    content += `## 📋 Summary\n\n${d.summary}\n\n`;
    if (incActions)    content += `## ✅ Action Items\n\n${d.action_items}\n\n`;
    if (incDecisions)  content += `## 🔑 Key Decisions\n\n${d.key_decisions}\n\n`;
    if (incQuestions)  content += `## ❓ Open Questions\n\n${d.open_questions}\n\n`;
    if (incTranscript) content += `## 🎙️ Full Transcript\n\n${d.transcript}\n\n`;
  } else {
    if (incTitle)      content += `MEETING: ${title}\n${"=".repeat(60)}\n\n`;
    if (incSummary)    content += `SUMMARY\n${"-".repeat(40)}\n${d.summary}\n\n`;
    if (incActions)    content += `ACTION ITEMS\n${"-".repeat(40)}\n${d.action_items}\n\n`;
    if (incDecisions)  content += `KEY DECISIONS\n${"-".repeat(40)}\n${d.key_decisions}\n\n`;
    if (incQuestions)  content += `OPEN QUESTIONS\n${"-".repeat(40)}\n${d.open_questions}\n\n`;
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
  showToast(`Exported as .${ext.toUpperCase()} ✓`, "success");
}

function slugify(str) {
  return str.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "").slice(0, 40) || "meeting";
}

/* ─────────────────────────── RAG CHAT ─────────────────────────── */
function setupChatInput() {
  const inp = document.getElementById("chatInput");
  inp.addEventListener("keydown", handleChatKey);
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
    const res = await fetch("/ask", {
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
    appendMessage("assistant", `⚠️ ${err.message}`);
  }
}

function appendMessage(role, content) {
  const msgs = document.getElementById("chatMessages");
  const avatar = role === "user" ? "👤" : "🤖";
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
    <div class="msg-avatar">🤖</div>
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

function removeTyping(el) {
  el?.remove();
}

function hideSuggestions() {
  document.getElementById("chatSuggestions").style.display = "none";
}

function clearChat() {
  const msgs = document.getElementById("chatMessages");
  msgs.innerHTML = `<div class="chat-system-msg">
    <div class="system-badge">RAG ENABLED</div>
    <p>The knowledge base is ready. Ask anything about your meeting.</p>
  </div>`;
  state.chatHistory = [];
  document.getElementById("chatSuggestions").style.display = "flex";
  document.getElementById("chatInput").value = "";
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br>");
}

/* ─────────────────────────── TOAST ─────────────────────────── */
let toastTimer = null;
function showToast(msg, type = "") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast show${type ? " " + type : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}
