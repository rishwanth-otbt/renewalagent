/**
 * IT Vendor Renewal — Executive Decision Brief
 * Frontend Rendering Engine (POC 1)
 */

// Robust API Base URL resolution:
// If served over HTTP (the FastAPI server, any port), use relative paths ("")
// If opened via file://, use "http://localhost:8000"
const API_BASE = window.location.protocol.startsWith("http")
  ? "" 
  : "http://localhost:8000";

const ALL_STATES = [
  "IDLE", "INTAKE", "EXTRACT", "COMPARE", "CALCULATE", "ASSESS", "RECOMMEND", "BRIEF_READY"
];

// Formatting Helpers
const fmtCurrency = (val) => {
  if (val === undefined || val === null) return "—";
  if (val >= 1000000) {
    return `$${(val / 1000000).toFixed(2)}M`;
  }
  return `$${val.toLocaleString()}`;
};

const fmtPct = (val) => {
  if (val === undefined || val === null) return "—";
  return `${val > 0 ? "+" : ""}${val}%`;
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  renderMovePipeline([]);
  loadCaseList();
});

let currentMoveTrace = [];
let currentResultId = null;

// The user's name for upload / PDF-export records. There is no login, so it is asked once
// and remembered in this browser.
const USER_NAME_KEY = "renewalDesk.userName";

function getSavedUserName() {
  try { return (localStorage.getItem(USER_NAME_KEY) || "").trim(); } catch (_) { return ""; }
}

function saveUserName(name) {
  try { localStorage.setItem(USER_NAME_KEY, name); } catch (_) { /* storage blocked: ask again next time */ }
}

/**
 * Export PDF: ask who is exporting, record it (PdfExports), stamp the page, then open print.
 */
async function exportPdf() {
  if (!currentResultId) {
    notify({ type: "error", title: "Generate the brief first", message: "Press Generate brief, then export." });
    return;
  }
  const answer = window.prompt("Your name (saved with this PDF export):", getSavedUserName());
  if (answer === null) return;                 // cancelled
  const name = answer.trim().slice(0, 100);
  if (!name) {
    notify({ type: "error", title: "Name is required", message: "Enter your name to export the PDF." });
    return;
  }
  saveUserName(name);
  try {
    const res = await fetch(`${API_BASE}/api/exports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result_id: currentResultId, exported_by: name }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Could not record the export");
    }
    const rec = await res.json();
    const stamp = document.getElementById("exportStamp");
    if (stamp) stamp.textContent = `Exported by ${rec.exported_by} on ${rec.exported_at}`;
  } catch (err) {
    notify({ type: "error", title: "PDF export not recorded", message: err.message });
    return;
  }
  window.print();
}

const KOZMO_MOVES = [
  { id: "M01", name: "M01 Goals" },
  { id: "M02", name: "M02 Terms" },
  { id: "M03", name: "M03 Deadlines" },
  { id: "M04", name: "M04 Performance" },
  { id: "M05", name: "M05 Licenses" },
  { id: "M10", name: "M10 Recommend" }
];

function setupEventListeners() {
  const caseSelect = document.getElementById("caseSelect");
  const reloadBtn = document.getElementById("reloadBtn");
  const printBtn = document.getElementById("printBtn");
  const uploadBtn = document.getElementById("uploadBtn");
  const fileUploadInput = document.getElementById("fileUploadInput");

  // Changing an input does not run the pipeline; it only flags "Generate brief".
  caseSelect.addEventListener("change", markInputsChanged);

  const asOfInput = document.getElementById("asOfInput");
  if (asOfInput) {
    asOfInput.addEventListener("change", markInputsChanged);
  }

  reloadBtn.addEventListener("click", () => {
    if (caseSelect.value) {
      generateBrief(caseSelect.value);
    } else {
      caseSelect.focus();
      caseSelect.scrollIntoView({ block: "center", behavior: "smooth" });
      const field = caseSelect.closest(".field");
      let hint = document.getElementById("caseHint");
      if (!hint && field) {
        hint = document.createElement("span");
        hint.id = "caseHint";
        hint.className = "field-hint";
        hint.textContent = "Pick a case first, then press Generate brief.";
        field.appendChild(hint);
      }
      caseSelect.classList.remove("needs-choice");
      void caseSelect.offsetWidth; // restart the animation on repeated clicks
      caseSelect.classList.add("needs-choice");
      clearTimeout(caseSelect._hintTimer);
      caseSelect._hintTimer = setTimeout(() => {
        caseSelect.classList.remove("needs-choice");
        hint?.remove();
      }, 3500);
    }
  });

  printBtn.addEventListener("click", exportPdf);

  setupRunPanel();

  if (uploadBtn && fileUploadInput) {
    setupUploadPanel(uploadBtn, fileUploadInput);
  }
}

// ---------------------------------------------------------------------------
// Left sidebar: upload panel + Run agent
// ---------------------------------------------------------------------------

/** The uploaded case waiting for "Run agent": { id, name } or null. */
let uploadedCase = null;

function setUploadPanelOpen(open) {
  const panel = document.getElementById("sbUpload");
  const btn = document.getElementById("uploadBtn");
  if (!panel || !btn) return;
  panel.hidden = !open;
  btn.setAttribute("aria-expanded", String(open));
  btn.classList.toggle("is-open", open);
}

function setupUploadPanel(uploadBtn, fileUploadInput) {
  const shell = document.querySelector(".app-shell");
  const drop = document.getElementById("sbDrop");
  const pickFile = () => fileUploadInput.click();

  uploadBtn.addEventListener("click", () => {
    // Collapsed icon strip has no room for the panel: go straight to the file picker.
    if (shell?.classList.contains("sb-collapsed")) { pickFile(); return; }
    setUploadPanelOpen(document.getElementById("sbUpload").hidden);
  });
  // The info icon inside the upload button only explains; it does not open the panel.
  uploadBtn.querySelector(".info-tip")?.addEventListener("click", (e) => e.stopPropagation());

  // Start-screen card opens the same panel (and the sidebar itself on small screens).
  document.getElementById("startUploadBtn")?.addEventListener("click", () => {
    if (shell?.classList.contains("sb-collapsed")) { pickFile(); return; }
    shell?.classList.add("sb-open");
    setUploadPanelOpen(true);
    drop?.focus();
  });

  drop?.addEventListener("click", pickFile);
  drop?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickFile(); }
  });
  ["dragenter", "dragover"].forEach((ev) => drop?.addEventListener(ev, (e) => {
    e.preventDefault();
    drop.classList.add("is-over");
  }));
  ["dragleave", "dragend"].forEach((ev) => drop?.addEventListener(ev, () => drop.classList.remove("is-over")));
  drop?.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("is-over");
    const file = e.dataTransfer?.files?.[0];
    if (file) uploadContractFile(file);
  });

  fileUploadInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) await uploadContractFile(file);
    fileUploadInput.value = "";
  });

  document.getElementById("sbFileClear")?.addEventListener("click", () => {
    setUploadedCase(null);
    setUploadPanelOpen(true);
  });
  document.getElementById("sbRunBtn")?.addEventListener("click", () => {
    if (!uploadedCase) return;
    // Give the run and the brief the full width: fold the sidebar to its icon strip.
    window.collapseSidebar?.();
    runAgent(uploadedCase.id);
  });
}

/** Validate, upload, then close the panel and wait for "Run agent" (no automatic run). */
async function uploadContractFile(file) {
  const drop = document.getElementById("sbDrop");
  if (!/\.json$/i.test(file.name)) {
    notify({ type: "error", title: "Only JSON files are supported", file: file.name,
             message: "Choose a contract saved as a .json file." });
    return;
  }
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch (_) {
    notify({ type: "error", title: "This file isn't valid JSON", file: file.name,
             message: "Check the file opens as JSON and try again." });
    return;
  }

  drop?.classList.add("is-busy");
  try {
    const res = await fetch(`${API_BASE}/api/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, data: parsed, uploaded_by: getSavedUserName() || null })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Server rejected JSON file");
    }
    const resp = await res.json();
    const name = resp.display_name || resp.original_filename || file.name;
    const vendor = parsed?.vendor?.name || parsed?.vendor_name || "";
    notify({ type: "success", title: "Document uploaded", file: name,
             message: "Press Run agent in the left panel to generate its brief." });

    setUploadedCase({ id: resp.case_id, name, vendor });
    setUploadPanelOpen(false);
    // Refresh the case list and select the new case, without running it.
    await loadCaseList(resp.case_id);
  } catch (err) {
    const [summary, list] = splitProblems(err.message);
    notify({ type: "error", title: "Upload failed", file: file.name, message: summary, details: list });
  } finally {
    drop?.classList.remove("is-busy");
  }
}

/** Show the uploaded file card and enable Run, or clear both. */
function setUploadedCase(c) {
  uploadedCase = c;
  const card = document.getElementById("sbFile");
  const runBtn = document.getElementById("sbRunBtn");
  if (card) card.hidden = !c;
  if (c) {
    document.getElementById("sbFileName").textContent = c.name;
    document.getElementById("sbFileSub").textContent = c.vendor ? `${c.vendor} · ready to run` : "Ready to run";
  }
  if (runBtn) {
    runBtn.disabled = !c || runInProgress;
    runBtn.title = c ? "Run the agent on this contract" : "Upload a contract first";
  }
}

/**
 * Server errors look like "Summary: problem one; problem two". Split them so the
 * notification can show the summary and the problems as a list.
 */
function splitProblems(message = "") {
  const text = String(message);
  const i = text.indexOf(": ");
  if (i === -1) return [text, []];
  const list = text.slice(i + 2).split(";").map((p) => p.trim()).filter(Boolean);
  return list.length > 1 ? [text.slice(0, i) + ".", list] : [text, []];
}

/**
 * Fetch available renewal cases from FastAPI
 */
async function loadCaseList(preferredCaseId = null) {
  const caseSelect = document.getElementById("caseSelect");
  try {
    const res = await fetch(`${API_BASE}/api/cases`);
    if (!res.ok) throw new Error("Failed to load cases");
    const data = await res.json();
    
    caseSelect.innerHTML = '<option value="">Select a case to evaluate…</option>';
    const countEl = document.getElementById("sbCaseCount");
    if (countEl) {
      const n = (data.cases || []).length;
      countEl.textContent = `${n} case${n === 1 ? "" : "s"} available`;
    }
    // Each case: its id plus the name to show (the uploaded file's own name for uploads).
    const items = data.items || (data.cases || []).map((c) => ({ id: c, name: `Case ${c}` }));
    if (items.length > 0) {
      items.forEach(({ id, name }) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = name;
        caseSelect.appendChild(opt);
      });
      renderStartCases(items);
      // Select a case that was asked for (e.g. just uploaded). Nothing runs until
      // the user presses Run agent or Generate brief.
      if (preferredCaseId && data.cases.map(String).includes(String(preferredCaseId))) {
        caseSelect.value = preferredCaseId;
      }
    } else {
      caseSelect.innerHTML = '<option value="">No cases found</option>';
      renderStartCases([]);
    }
  } catch (err) {
    console.error("Error loading case list:", err);
    caseSelect.innerHTML = '<option value="">Cannot reach API (Is backend running?)</option>';
    const box = document.getElementById("startCases");
    if (box) box.innerHTML = '<span class="start-text">Cannot reach the API. Is the backend running?</span>';
  }
}

/**
 * Start panel: quick-pick buttons for the cases already loaded.
 */
function renderStartCases(items) {
  const box = document.getElementById("startCases");
  if (!box) return;
  box.innerHTML = "";
  if (!items.length) {
    box.innerHTML = '<span class="start-text">No cases yet. Upload a contract to begin.</span>';
    return;
  }
  const MAX = 6;
  items.slice(0, MAX).forEach(({ id, name }) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "case-chip";
    b.textContent = name;
    b.title = name;
    b.addEventListener("click", () => {
      document.getElementById("caseSelect").value = id;
      markInputsChanged();
    });
    box.appendChild(b);
  });
  if (items.length > MAX) {
    const more = document.createElement("span");
    more.className = "start-more";
    more.textContent = `+${items.length - MAX} more in the list above`;
    box.appendChild(more);
  }
}

/**
 * Swap the start panel for the brief once a case has been evaluated.
 */
function showBrief() {
  document.getElementById("startPanel")?.setAttribute("hidden", "");
  document.getElementById("briefContainer")?.removeAttribute("hidden");
  document.getElementById("sbSections")?.removeAttribute("hidden");
  const printBtn = document.getElementById("printBtn");
  if (printBtn) { printBtn.disabled = false; printBtn.title = "Export as PDF / Print"; }
}

/**
 * Case or date changed: clear the "pick a case" hint on the selector.
 */
function markInputsChanged() {
  document.getElementById("caseSelect").classList.remove("needs-choice");
}

/**
 * Demo pacing: the moves appear one after another over this long, then the brief shows.
 * The backend answers in milliseconds; this delay only makes the agent's steps readable.
 */
const RUN_REVEAL_MS = 3000;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let runInProgress = false;

/** "Generate brief" (top bar) — same run as the sidebar's Run agent. */
function generateBrief(caseId) {
  return runAgent(caseId);
}

/**
 * Run the agent on a case: both run buttons show a spinner, the moves appear one by one
 * in the middle, then the brief is drawn below them.
 */
async function runAgent(caseId) {
  if (runInProgress) return;
  runInProgress = true;
  const buttons = [document.getElementById("reloadBtn"), document.getElementById("sbRunBtn")].filter(Boolean);
  buttons.forEach((b) => { b.classList.add("is-generating"); b.disabled = true; });
  const caseSelect = document.getElementById("caseSelect");
  if (caseSelect && caseSelect.value !== String(caseId)) caseSelect.value = caseId;
  try {
    await loadCaseBrief(caseId, { animate: true });
  } finally {
    runInProgress = false;
    buttons.forEach((b) => b.classList.remove("is-generating"));
    document.getElementById("reloadBtn").disabled = false;
    setUploadedCase(uploadedCase); // re-enables Run when a file is loaded
  }
}

/**
 * Fetch executive brief generated by Kozmo Move Orchestrator.
 * animate: reveal the moves one by one (RUN_REVEAL_MS in total) before the brief appears.
 */
async function loadCaseBrief(caseId, { animate = false } = {}) {
  renderPipelineRunning();
  const briefEl = document.getElementById("briefContainer");
  if (animate) startRunLogLive();
  else briefEl?.classList.add("is-loading");
  try {
    const asOf = document.getElementById("asOfInput")?.value;
    // POST /api/process runs the pipeline and saves the result (EvaluationResults).
    const res = await fetch(`${API_BASE}/api/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId, as_of: asOf || null }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Error evaluating case");
    }
    const brief = await res.json();

    // Store the move trace for the Move Flow modal
    currentMoveTrace = brief.meta?.move_trace || [];
    // Saved result id: needed to record a PDF export of this brief.
    currentResultId = brief.meta?.result_id ?? null;
    const stamp = document.getElementById("exportStamp");
    if (stamp) stamp.textContent = "";
    currentVendorName = brief.vendor?.name || "";

    if (animate) await playRunLog(currentMoveTrace, RUN_REVEAL_MS);

    // Render the Kozmo Move pipeline bar, the activity list and the run panel
    renderMovePipeline(currentMoveTrace);
    renderRunLog(currentMoveTrace);
    rpOpenMoves.clear();
    renderRunPanel();
    renderBrief(brief);
    showBrief();
    // After the step-by-step run, fold the activity list to its one-line summary.
    // The header stays clickable to open it again.
    if (animate) setTimeout(() => setRunLogOpen(false), RUN_LOG_COLLAPSE_DELAY_MS);
  } catch (err) {
    console.error("Error evaluating brief:", err);
    const [summary, list] = splitProblems(err.message);
    notify({ type: "error", title: "Couldn't generate the brief", message: summary, details: list });
    // Put the middle back as it was: the last finished run and brief, or the start panel.
    renderMovePipeline(currentMoveTrace);
    renderRunLog(currentMoveTrace);
    if (animate) {
      const prev = currentMoveTrace.length ? "briefContainer" : "startPanel";
      document.getElementById(prev)?.removeAttribute("hidden");
    }
  } finally {
    briefEl?.classList.remove("is-loading");
    document.getElementById("runLog")?.classList.remove("is-live");
  }
}

/** Short pause on the finished list before it folds, so the last green tick is seen. */
const RUN_LOG_COLLAPSE_DELAY_MS = 600;

/** Open or fold the activity list (same as clicking its header). */
function setRunLogOpen(open) {
  document.getElementById("runLog")?.classList.toggle("collapsed", !open);
  document.getElementById("runLogHead")?.setAttribute("aria-expanded", String(open));
}

/** Clear the middle and show the activity list in its "starting" state. */
function startRunLogLive() {
  const box = document.getElementById("runLog");
  if (!box) return;
  document.getElementById("startPanel")?.setAttribute("hidden", "");
  document.getElementById("briefContainer")?.setAttribute("hidden", "");
  box.classList.remove("is-running", "collapsed");
  box.classList.add("is-live");
  document.getElementById("runLogHead")?.setAttribute("aria-expanded", "true");
  document.getElementById("runLogSummary").innerHTML = "Starting the agent…";
  document.getElementById("runLogList").innerHTML = "";
  box.hidden = false;
}

/** Add the moves one at a time: each shows as running, then turns into a finished row. */
async function playRunLog(trace, totalMs) {
  const list = document.getElementById("runLogList");
  const summary = document.getElementById("runLogSummary");
  if (!list || !trace.length) return;
  const step = totalMs / trace.length;
  list.innerHTML = "";
  for (let i = 0; i < trace.length; i++) {
    const mt = trace[i];
    summary.innerHTML = `Agent running · move <strong>${i + 1}</strong> of ${trace.length}`;
    list.insertAdjacentHTML("beforeend", runLogRowHtml(mt, i, true));
    await sleep(step);
    list.lastElementChild.outerHTML = runLogRowHtml(mt, i, false);
  }
}

/**
 * Render Kozmo Move Pipeline Bar (replaces old State Machine audit)
 */
function renderMovePipeline(moveTrace) {
  const container = document.getElementById("statePipeline");
  container.innerHTML = "";

  const movesToShow = moveTrace.length > 0
    ? moveTrace
    : KOZMO_MOVES.map(m => ({ move_id: m.id, name: m.name, status: "PENDING" }));

  movesToShow.forEach((mt, idx) => {
    const pending = mt.status === "PENDING";
    const stepEl = document.createElement(pending ? "span" : "button");
    stepEl.className = pending ? "pipe-step" : "pipe-step active";

    const { total, executed, skipped } = actionCounts(mt);
    const idEl = document.createElement("span");
    idEl.textContent = mt.move_id;
    stepEl.appendChild(idEl);
    if (!pending) {
      stepEl.type = "button";
      const countEl = document.createElement("span");
      countEl.className = "pipe-count";
      countEl.textContent = `${executed}/${total}`;
      stepEl.appendChild(countEl);
      stepEl.addEventListener("click", () => openRunPanel(idx));
    }
    stepEl.title = pending ? `${mt.name} — not run yet`
      : `${mt.name} — ${executed} of ${total} actions ran${skipped ? `, ${skipped} skipped` : ""}. Click to see them.`;
    container.appendChild(stepEl);

    if (idx < movesToShow.length - 1) {
      const arrow = document.createElement("span");
      arrow.className = "pipe-arrow";
      arrow.textContent = "›";
      container.appendChild(arrow);
    }
  });
}

function renderPipelineRunning() {
  const container = document.getElementById("statePipeline");
  container.innerHTML = '<span class="pipe-step running">Running the move pipeline…</span>';
  const status = document.getElementById("rpStatus");
  if (status) status.innerHTML = '<span class="rp-status-dot running"></span>Running…';
  document.getElementById("runLog")?.classList.add("is-running");
}

/**
 * Main Render Function: Injects slim brief JSON into the template
 */
function renderBrief(data) {
  const meta = data.meta || {};
  const vendor = data.vendor || {};
  const fin = data.financials || {};
  const seats = data.seats || {};
  const history = data.history_trend || {};
  const perf = data.performance || {};
  const risks = data.risks || {};
  const rec = data.recommendation || {};
  const timeline = data.timeline || {};
  const analysis = data.further_analysis || [];
  const flags = data.sla_addendum_flags || [];

  // 1. Header & Quick KPIs
  document.getElementById("briefDocTitle").textContent = `${vendor.name ?? '—'} — Executive Decision Brief`;
  document.getElementById("serviceSubtitle").textContent = `${vendor.service ?? '—'} Renewal Assessment · ${meta.case_id ?? '—'}`;
  
  const decisionValueEl = document.getElementById("mainDecisionValue");
  const decisionBox = document.getElementById("decisionPillBox");
  decisionValueEl.textContent = rec.primary ?? "—";
  
  decisionBox.className = "decision-box";
  const decLower = (rec.primary || "").toLowerCase();
  if (decLower.includes("renew")) decisionBox.classList.add("renew");
  else if (decLower.includes("switch")) decisionBox.classList.add("switch");

  // KPI Tiles
  document.getElementById("kpiCurrentAcv").textContent = fmtCurrency(fin.current_acv);
  document.getElementById("kpiCurrentSeats").textContent = `${seats.total ?? '—'} provisioned seats`;
  
  document.getElementById("kpiProposedAcv").textContent = fmtCurrency(fin.proposed_acv);
  document.getElementById("kpiIncreasePct").textContent = `${fmtPct(fin.increase_pct)} proposed increase`;

  document.getElementById("kpiTargetAcv").textContent = fmtCurrency(fin.negotiation_target_acv);
  const potentialSavings = (fin.proposed_acv != null && fin.negotiation_target_acv != null) ? fin.proposed_acv - fin.negotiation_target_acv : null;
  document.getElementById("kpiSavingsTarget").textContent = `${fmtCurrency(potentialSavings)} targeted reduction`;

  document.getElementById("kpiNoticeDeadline").textContent = meta.notice_deadline || "—";
  const noticeEl = document.getElementById("kpiNoticeDaysRemaining");
  if (meta.notice_passed) {
    noticeEl.textContent = meta.auto_renewal
      ? `⛔ Missed ${Math.abs(meta.days_to_notice)} days ago — auto-renews`
      : `⛔ Notice window closed ${Math.abs(meta.days_to_notice)} days ago`;
  } else if (meta.notice_at_risk) {
    noticeEl.textContent = `⚠️ Imminent: ${meta.days_to_notice} days left`;
  } else {
    noticeEl.textContent = `${meta.days_to_notice ?? '—'} days left (${meta.notice_days ?? '—'}-day notice)`;
  }
  noticeEl.classList.toggle("alert-text", Boolean(meta.notice_passed || meta.notice_at_risk));

  // Metadata Strip
  document.getElementById("metaVendorName").textContent = vendor.name || "—";
  document.getElementById("metaServiceName").textContent = vendor.service || "—";
  document.getElementById("metaTerm").textContent = `${vendor.proposed_term_months ?? '—'} months proposed`;
  document.getElementById("metaRenewalDeadline").textContent = meta.renewal_deadline || "—";
  document.getElementById("metaAssessmentDate").textContent = meta.assessment_date || "—";

  // Executive Summary Banner
  document.getElementById("execDecisionHeading").textContent = `Executive Decision: ${rec.primary} before commitment`;
  document.getElementById("execDecisionRationale").textContent = rec.rationale || "—";

  // Renewal-type tags: what kind of renewal this is and which special paths fired
  const tags = [];
  const typeLabel = { EXPANSION: "Seat expansion", REDUCTION: "Seat reduction", FLAT: "Flat seat volume" }[meta.renewal_type];
  if (typeLabel) tags.push({ text: `${typeLabel} (${seats.proposed_seats ?? '—'} seats)`, cls: meta.renewal_type === "EXPANSION" ? "warn" : "" });
  tags.push({ text: meta.auto_renewal ? "Auto-renewal" : "Manual renewal", cls: "" });
  const noticeTag = {
    AUTO_RENEWED_LOCK_IN: { text: "Notice missed: auto-renew lock-in", cls: "high" },
    NOTICE_WINDOW_CLOSED: { text: "Notice window closed", cls: "warn" },
    IMMINENT_RISK: { text: `Notice due in ${meta.days_to_notice} days`, cls: "high" },
    ADEQUATE_RUNWAY: { text: `${meta.days_to_notice} days to notice`, cls: "" },
  }[meta.notice_status];
  if (noticeTag) tags.push(noticeTag);
  if (fin.cap_breach) tags.push({ text: `Breaches ${fin.price_cap_pct}% price cap`, cls: "high" });
  if ((seats.added_modules || []).length) tags.push({ text: `+ ${seats.added_modules.join(", ")}`, cls: "warn" });
  if (rec.switch_downgraded) tags.push({ text: "Switch downgraded: hard to replace", cls: "warn" });
  const tagsEl = document.getElementById("execDecisionTags");
  tagsEl.innerHTML = "";
  tags.forEach(t => {
    const span = document.createElement("span");
    span.className = `decision-tag ${t.cls}`.trim();
    span.textContent = t.text;
    tagsEl.appendChild(span);
  });

  // Decision drivers: the facts that moved the recommendation away from a clean renewal
  const driversEl = document.getElementById("execDecisionDrivers");
  driversEl.innerHTML = "";
  if ((rec.drivers || []).length) {
    const title = document.createElement("strong");
    title.textContent = rec.primary === "Renew" ? "Points to watch:" : "Why this recommendation:";
    const ul = document.createElement("ul");
    rec.drivers.forEach(d => {
      const li = document.createElement("li");
      li.textContent = d;
      ul.appendChild(li);
    });
    driversEl.append(title, ul);
  }

  // renderRuleChecks(meta);  // POLICY DISABLED for this version

  // 2. Section 1: Financial Impact
  const finTableBody = document.querySelector("#financialTable tbody");
  const currentMonths = meta.current_term_months ?? '—';
  const proposedMonths = vendor.proposed_term_months ?? '—';
  const termDelta = (typeof proposedMonths === "number" && typeof currentMonths === "number") ? proposedMonths - currentMonths : null;
  const termDeltaStr = termDelta === null ? "—" : termDelta > 0 ? `+${termDelta} months extension` : (termDelta === 0 ? "Same duration" : `${termDelta} months`);

  // Seat volume: proposed vs current (was fixed text "0% (Hold volume)")
  let seatDeltaStr = "—";
  if (seats.total != null && seats.proposed_seats != null) {
    const change = seats.proposed_seats - seats.total;
    const pct = seats.total ? Math.round((change / seats.total) * 1000) / 10 : 0;
    seatDeltaStr = change === 0 ? "0% (Hold volume)"
      : `${change > 0 ? "+" : "−"}${Math.abs(change).toLocaleString()} seats (${change > 0 ? "+" : "−"}${Math.abs(pct)}%)`;
  }
  // Per-seat price change with its real sign (was always "+")
  let perSeatDeltaStr = "—";
  if (seats.proposed_unit_price != null && seats.current_unit_price != null) {
    const d = Math.round((seats.proposed_unit_price - seats.current_unit_price) * 100) / 100;
    perSeatDeltaStr = d === 0 ? "No change" : `${d > 0 ? "+" : "−"}$${Math.abs(d).toLocaleString()} / seat`;
  }

  finTableBody.innerHTML = `
    <tr>
      <td><strong>Annual Contract Value (ACV)</strong></td>
      <td>${fmtCurrency(fin.current_acv)}</td>
      <td>${fmtCurrency(fin.proposed_acv)}</td>
      <td><span class="status-chip ${fin.increase_pct > 10 ? 'high' : (fin.increase_pct > 0 ? 'warn' : 'ok')}">${fmtPct(fin.increase_pct)} (${fmtCurrency(fin.increase_usd)})</span></td>
    </tr>
    <tr>
      <td><strong>Provisioned License Quantity</strong></td>
      <td>${seats.total?.toLocaleString() ?? "—"}</td>
      <td>${seats.proposed_seats?.toLocaleString() ?? "—"}</td>
      <td>${seatDeltaStr}</td>
    </tr>
    <tr>
      <td><strong>Average Per-Seat Cost (Annual)</strong></td>
      <td>$${seats.current_unit_price?.toLocaleString()}</td>
      <td>$${seats.proposed_unit_price?.toLocaleString()}</td>
      <td>${perSeatDeltaStr}</td>
    </tr>
    <tr>
      <td><strong>Contract Duration</strong></td>
      <td>${currentMonths} months</td>
      <td>${proposedMonths} months</td>
      <td>${termDeltaStr}</td>
    </tr>
    <tr>
      <td><strong>Approved Internal Budget</strong></td>
      <td colspan="2">${fmtCurrency(fin.approved_budget_acv)}</td>
      <td><span class="status-chip ${fin.budget_gap_usd > 0 ? 'high' : 'ok'}">${fin.budget_gap_usd > 0 ? fmtCurrency(fin.budget_gap_usd) + ' Over Budget' : 'Within Budget'}</span></td>
    </tr>
  `;

  document.getElementById("expBaseline").textContent = fmtCurrency(fin.three_year_baseline);
  document.getElementById("expProposal").textContent = fmtCurrency(fin.three_year_proposal);
  document.getElementById("expTarget").textContent = fmtCurrency(fin.three_year_target);

  const findingsList = document.getElementById("licenseFindingsList");
  if (seats.reduction_opportunity > 0) {
    findingsList.innerHTML = `
      <li>Active utilization measured at <strong>${seats.utilization_pct}%</strong> (${seats.active} active of ${seats.total} provisioned seats).</li>
      <li>Approximately <strong>${seats.inactive} licenses</strong> have zero activity in the last 90 days.</li>
      <li>Recommended optimized seat baseline: <strong>${seats.recommended_seats} seats</strong> (active plus growth headroom).</li>
      <li>Identified reduction opportunity of <strong>${seats.reduction_opportunity} licenses</strong>, representing <strong>${fmtCurrency(seats.annualized_exposure_usd)}</strong> in cost exposure.</li>
    `;
  } else {
    findingsList.innerHTML = `
      <li>Active utilization is strong at <strong>${seats.utilization_pct}%</strong> (${seats.active} of ${seats.total} seats active).</li>
      <li>Seat adoption is healthy across all business units with zero identifiable license shelfware.</li>
      <li>Recommended baseline: <strong>Retain full ${seats.total} licenses</strong> without volume reduction.</li>
      <li>Focus negotiation strictly on multi-year price locks and service levels.</li>
    `;
  }

  // 3. Section 2: Historical Trend
  document.getElementById("histAvgIncrease").textContent = `${history.avg_historical_increase_pct}%`;
  document.getElementById("histCurrentAsk").textContent = fmtPct(fin.increase_pct);
  const vsAvg = history.current_increase_vs_avg;
  document.getElementById("histVsAvg").textContent = vsAvg == null ? "—" : `${vsAvg > 0 ? "+" : ""}${vsAvg} pts`;
  document.getElementById("histTotalSpend").textContent = fmtCurrency(history.total_spend_to_date);

  const histTableBody = document.querySelector("#historyTable tbody");
  histTableBody.innerHTML = (history.previous_increases || []).map(h => `
    <tr>
      <td><strong>${h.cycle}</strong></td>
      <td>${h.seats?.toLocaleString()} seats</td>
      <td>${fmtCurrency(h.renewed_acv)}</td>
      <td><span class="status-chip warn">+${h.increase_pct}%</span></td>
      <td>${h.outcome || '—'}</td>
    </tr>
  `).join("");

  // 4. Section 3: Vendor Performance & SLA
  const perfRatingEl = document.getElementById("perfOverallRating");
  perfRatingEl.textContent = perf.overall_rating ?? "—";
  perfRatingEl.className = `status-chip ${perf.overall_rating === 'Good' ? 'good' : 'high'}`;

  const perfTableBody = document.querySelector("#perfTable tbody");
  // Targets come from the policy in force for this brief (meta.policy), not from fixed numbers.
  const pp = (meta.policy || {}).performance || {};
  const lp = (meta.policy || {}).licenses || {};
  const chip = (cls, text) => `<span class="status-chip ${cls}">${text}</span>`;
  const uptimeChip = perf.uptime_gap_pct <= (pp.good_uptime_gap ?? 0) ? chip("ok", "Met")
    : perf.uptime_gap_pct > (pp.poor_uptime_gap ?? 0) ? chip("below", "Below Target") : chip("warn", "Slightly Below");
  const slaChip = perf.support_sla_pct >= (pp.good_support_sla_pct ?? 0) ? chip("ok", "Met")
    : perf.support_sla_pct < (pp.poor_support_sla_pct ?? 0) ? chip("below", "Sub-standard") : chip("warn", "Below Good");
  const incChip = perf.critical_incidents <= (pp.good_max_incidents ?? 0)
    ? chip("ok", perf.critical_incidents === 0 ? "Zero Outages (Met)" : "Met")
    : perf.critical_incidents >= (pp.poor_incidents ?? Infinity) ? chip("below", "Requires Review") : chip("warn", "Above Good");
  const utilTarget = lp.target_utilization_pct;
  perfTableBody.innerHTML = `
    <tr>
      <td>Service Availability (Uptime)</td>
      <td>${perf.uptime_contracted}%</td>
      <td><strong>${perf.uptime_actual}%</strong></td>
      <td>${uptimeChip}</td>
    </tr>
    <tr>
      <td>Support SLA Achievement</td>
      <td>${pp.good_support_sla_pct ?? "—"}%</td>
      <td><strong>${perf.support_sla_pct}%</strong></td>
      <td>${slaChip}</td>
    </tr>
    <tr>
      <td>Critical Production Incidents</td>
      <td>≤ ${pp.good_max_incidents ?? "—"}</td>
      <td><strong>${perf.critical_incidents}</strong></td>
      <td>${incChip}</td>
    </tr>
    <tr>
      <td>License Seat Utilization</td>
      <td>${utilTarget ?? "—"}%</td>
      <td><strong>${seats.utilization_pct}%</strong></td>
      <td>${seats.utilization_pct >= utilTarget ? chip("ok", "Optimal Adoption") : chip("warn", "Optimization Target")}</td>
    </tr>
    <tr>
      <td>Roadmap Milestones Delivered</td>
      <td>${perf.roadmap_total} of ${perf.roadmap_total}</td>
      <td><strong>${perf.roadmap_delivered} of ${perf.roadmap_total}</strong></td>
      <td>${chip(perf.roadmap_delayed?.length > 0 ? "below" : "ok", perf.roadmap_delayed?.length > 0 ? "Delayed Delivery" : "On Track")}</td>
    </tr>
  `;

  const perfObsList = document.getElementById("perfObservationsList");
  perfObsList.innerHTML = (perf.key_observations || []).map(obs => `<li>${obs}</li>`).join("");

  // 5. Section 4: Risk Register & Governance Flags
  const riskOverallEl = document.getElementById("riskOverallLevel");
  riskOverallEl.textContent = `${risks.overall_level} Exposure`;
  riskOverallEl.className = `status-chip ${risks.overall_level.toLowerCase().includes('high') ? 'high' : 'warn'}`;

  const riskTableBody = document.querySelector("#riskTable tbody");
  riskTableBody.innerHTML = (risks.items || []).map(r => `
    <tr>
      <td><strong>${r.risk}</strong></td>
      <td><span class="status-chip ${r.level.toLowerCase()}">${r.level}</span></td>
      <td>${r.impact}</td>
    </tr>
  `).join("");

  document.getElementById("criticalConcernText").textContent = risks.critical_concern || "—";

  const slaFlagsList = document.getElementById("slaFlagsList");
  slaFlagsList.innerHTML = (flags || []).map(fl => `
    <div class="flag-item">
      <span class="flag-tag">${fl.type}</span>
      <span>${fl.detail}</span>
    </div>
  `).join("");

  // 6. Section 5: Recommendations & Options
  const optionsTableBody = document.querySelector("#optionsTable tbody");
  optionsTableBody.innerHTML = (rec.options || []).map(opt => `
    <tr>
      <td><strong>${opt.option}</strong></td>
      <td>${opt.assessment}</td>
    </tr>
  `).join("");

  document.getElementById("fallbackStrategyText").textContent = rec.fallback || "—";

  const objList = document.getElementById("negotiationObjectivesList");
  objList.innerHTML = (rec.negotiation_objectives || []).map(o => `<li>${o}</li>`).join("");

  // 7. Section 6: Timeline & Milestones
  document.getElementById("planDurationBadge").textContent = timeline.total_duration ?? "—";

  const phasesContainer = document.getElementById("timelinePhases");
  phasesContainer.innerHTML = (timeline.steps || []).map(st => `
    <div class="phase-card">
      <div class="phase-head">
        <span>${st.phase}</span>
        <span class="phase-dur">${st.duration}</span>
      </div>
      <div class="phase-desc">${st.description}</div>
      <div class="phase-owners">Owners: ${st.owners?.join(", ")}</div>
    </div>
  `).join("");

  const milestonesTableBody = document.querySelector("#milestonesTable tbody");
  milestonesTableBody.innerHTML = (timeline.milestones || []).map(m => `
    <tr>
      <td><strong>${m.milestone}</strong></td>
      <td>${m.date}</td>
      <td><span class="status-chip ${m.critical ? 'high' : 'neutral'}">${m.critical ? 'Strict Cutoff' : 'Planned'}</span></td>
    </tr>
  `).join("");

  // 8. Section 7: Further Analysis (Commented out for POC 1 - deferred to POC 2)
  /*
  const analysisTableBody = document.querySelector("#furtherAnalysisTable tbody");
  if (analysisTableBody) {
    analysisTableBody.innerHTML = (analysis || []).map(an => `
      <tr>
        <td><strong>${an.investigation}</strong></td>
        <td>${an.deliverable}</td>
        <td><span class="status-chip neutral">${an.time}</span></td>
      </tr>
    `).join("");
  }
  */
}



/* POLICY DISABLED for this version: rule-check strip commented out.
/**
 * Rule-check strip: the policy rules that decided the label, with this case's values.
 * /
function renderRuleChecks(meta) {
  const strip = document.getElementById("ruleCheckStrip");
  const notice = document.getElementById("policyNotice");
  if (notice) notice.hidden = meta.policy_version !== 0;
  if (!strip) return;
  const checks = meta.rule_checks || [];
  if (!checks.length) { strip.innerHTML = ""; return; }

  const version = meta.policy_version === 0 ? "built-in defaults (v0)"
    : meta.policy_version == null ? "unsaved draft" : `version ${meta.policy_version}`;
  const head = document.createElement("div");
  head.className = "rule-strip-head";
  head.innerHTML = `<span><strong>Policy rules</strong> · ${version}</span><a href="policy.html">Change policy →</a>`;

  const list = document.createElement("div");
  list.className = "rule-checks";
  checks.forEach(c => {
    const chip = document.createElement("span");
    chip.className = `rule-check ${c.passed ? "" : "failed"}`.trim();
    chip.title = `${c.group} rule (${c.id}): needs ${c.limit}; actual ${c.actual}`;
    const icon = document.createTextNode(`${c.passed ? "✓" : "✗"} ${c.rule}: `);
    const actual = document.createElement("span");
    actual.className = "rc-actual";
    actual.textContent = c.actual;
    const limit = document.createTextNode(` (needs ${c.limit})`);
    chip.append(icon, actual, limit);
    list.appendChild(chip);
  });

  const decided = document.createElement("div");
  decided.className = "rule-decided-by";
  decided.textContent = meta.decided_by || "";

  strip.innerHTML = "";
  strip.append(head, list, decided);
}
*/

// ===================================================================
// AGENT RUN — activity list (in the page) + right panel (moves → actions)
// ===================================================================

let currentVendorName = "";
const rpOpenMoves = new Set();   // indexes of moves expanded in the right panel

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ICONS = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  cross: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  skip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="12" x2="18" y2="12"/></svg>',
  chevR: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
  chevD: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
};

/** Counts for one move: actions in the template, how many ran / were skipped / failed, gates passed. */
function actionCounts(mt) {
  const actions = mt.actions || [];
  const gates = mt.gates || [];
  return {
    total: actions.length,
    executed: actions.filter(a => a.status === "EXECUTED").length,
    skipped: actions.filter(a => a.status === "SKIPPED").length,
    failed: actions.filter(a => a.status === "FAILED").length,
    gates: gates.length,
    gatesPassed: gates.filter(g => g.passed).length,
  };
}

/** Totals across the whole run. */
function runTotals(trace) {
  return trace.reduce((t, mt) => {
    const c = actionCounts(mt);
    Object.keys(c).forEach(k => { t[k] = (t[k] || 0) + c[k]; });
    t.moves += 1;
    return t;
  }, { moves: 0, total: 0, executed: 0, skipped: 0, failed: 0, gates: 0, gatesPassed: 0 });
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function setupRunPanel() {
  document.getElementById("runPanelBtn")?.addEventListener("click", () => {
    const shell = document.querySelector(".app-shell");
    if (shell.classList.contains("rp-open")) closeRunPanel();
    else openRunPanel();
  });
  document.getElementById("rpClose")?.addEventListener("click", closeRunPanel);
  document.getElementById("rpBackdrop")?.addEventListener("click", closeRunPanel);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.querySelector(".app-shell.rp-open")) closeRunPanel();
  });

  document.getElementById("runLogHead")?.addEventListener("click", (e) => {
    const head = e.currentTarget;
    const open = head.getAttribute("aria-expanded") !== "true";
    head.setAttribute("aria-expanded", String(open));
    document.getElementById("runLog").classList.toggle("collapsed", !open);
  });

  document.getElementById("rpExpandAll")?.addEventListener("click", () => {
    const allOpen = currentMoveTrace.length > 0 && rpOpenMoves.size === currentMoveTrace.length;
    rpOpenMoves.clear();
    if (!allOpen) currentMoveTrace.forEach((_, i) => rpOpenMoves.add(i));
    renderRunPanel();
  });

  renderRunPanel();
}

/** Open the right panel; with an index, expand that move and scroll it into view. */
function openRunPanel(moveIdx = null) {
  const shell = document.querySelector(".app-shell");
  const panel = document.getElementById("runPanel");
  if (moveIdx !== null) rpOpenMoves.add(moveIdx);
  renderRunPanel(moveIdx);
  panel.hidden = false;
  requestAnimationFrame(() => shell.classList.add("rp-open"));
  document.getElementById("runPanelBtn")?.setAttribute("aria-expanded", "true");
  if (moveIdx !== null) {
    const el = panel.querySelector(`.rp-move[data-idx="${moveIdx}"]`);
    setTimeout(() => el?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 240);
  }
}

function closeRunPanel() {
  const shell = document.querySelector(".app-shell");
  shell.classList.remove("rp-open");
  document.getElementById("runPanelBtn")?.setAttribute("aria-expanded", "false");
  setTimeout(() => {
    if (!shell.classList.contains("rp-open")) document.getElementById("runPanel").hidden = true;
  }, 240);
}

/**
 * Activity list between the controls and the brief — one row per move, like a tool-call log.
 */
function renderRunLog(trace) {
  const box = document.getElementById("runLog");
  const list = document.getElementById("runLogList");
  if (!box || !list) return;
  box.classList.remove("is-running");
  if (!trace.length) { box.hidden = true; return; }

  const t = runTotals(trace);
  document.getElementById("runLogSummary").innerHTML =
    `Agent ran <strong>${plural(t.moves, "move")}</strong> · <strong>${t.executed}</strong> of ${plural(t.total, "action")}` +
    (t.skipped ? ` · ${t.skipped} skipped` : "") +
    (t.failed ? ` · <span class="rl-bad">${t.failed} failed</span>` : "");

  list.innerHTML = trace.map((mt, idx) => runLogRowHtml(mt, idx, false)).join("");
  list.querySelectorAll(".rl-row").forEach(row =>
    row.addEventListener("click", () => openRunPanel(Number(row.dataset.idx))));
  box.hidden = false;
}

/** One activity row. running = the move is in progress (spinner, no counts, not clickable yet). */
function runLogRowHtml(mt, idx, running) {
  if (running) {
    return `
      <div class="rl-row is-live-row running" data-idx="${idx}">
        <span class="rl-icon run" aria-hidden="true"></span>
        <span class="rl-verb">Running move</span>
        <span class="rl-name"><span class="rl-id">${esc(mt.move_id)}</span>${esc(mt.name)}</span>
        <span class="rl-meta">working…</span>
        <span class="rl-go"></span>
      </div>`;
  }
  const c = actionCounts(mt);
  const state = c.failed ? "fail" : "ok";
  return `
      <button type="button" class="rl-row" data-idx="${idx}" title="Open ${esc(mt.move_id)} in the run panel">
        <span class="rl-icon ${state}">${state === "fail" ? ICONS.cross : ICONS.check}</span>
        <span class="rl-verb">Ran move</span>
        <span class="rl-name"><span class="rl-id">${esc(mt.move_id)}</span>${esc(mt.name)}</span>
        <span class="rl-meta">${c.executed}/${c.total} actions${c.skipped ? ` · ${c.skipped} skipped` : ""}${c.gates ? ` · ${c.gatesPassed}/${c.gates} gates` : ""}</span>
        <span class="rl-go">${ICONS.chevR}</span>
      </button>`;
}

/**
 * Right panel: run stats + a vertical timeline of moves. Each move expands to show its gates and actions.
 */
function renderRunPanel(focusIdx = null) {
  const statsEl = document.getElementById("rpStats");
  const timeline = document.getElementById("rpTimeline");
  const status = document.getElementById("rpStatus");
  const btnText = document.getElementById("runPanelBtnText");
  const expandAll = document.getElementById("rpExpandAll");
  if (!timeline) return;

  const trace = currentMoveTrace || [];

  if (!trace.length) {
    status.innerHTML = '<span class="rp-status-dot"></span>Not run yet';
    statsEl.innerHTML = `
      <div class="rp-stat"><span class="rp-stat-num">${KOZMO_MOVES.length}</span><span class="rp-stat-lbl">Moves in template</span></div>
      <div class="rp-stat"><span class="rp-stat-num">—</span><span class="rp-stat-lbl">Actions run</span></div>`;
    timeline.innerHTML = KOZMO_MOVES.map(m => `
      <li class="rp-move pending">
        <div class="rp-move-btn" aria-disabled="true">
          <span class="rp-dot"></span>
          <span class="rp-move-main"><span class="rp-move-name">${esc(m.name)}</span><span class="rp-move-meta">Not run yet — generate a brief</span></span>
        </div>
      </li>`).join("");
    if (btnText) btnText.textContent = "Agent run";
    expandAll.hidden = true;
    return;
  }

  const t = runTotals(trace);
  status.innerHTML = `<span class="rp-status-dot ${t.failed ? "bad" : "ok"}"></span>${t.failed ? "Finished with errors" : "Report ready"}${currentVendorName ? ` · ${esc(currentVendorName)}` : ""}`;
  if (btnText) btnText.innerHTML = `Agent run <span class="rp-toggle-count">${t.moves} moves · ${t.total} actions</span>`;
  expandAll.hidden = false;
  expandAll.textContent = rpOpenMoves.size === trace.length ? "Collapse all" : "Expand all";

  statsEl.innerHTML = `
    <div class="rp-stat"><span class="rp-stat-num">${t.moves}</span><span class="rp-stat-lbl">Moves run</span></div>
    <div class="rp-stat"><span class="rp-stat-num">${t.executed}<small>/${t.total}</small></span><span class="rp-stat-lbl">Actions run</span></div>
    <div class="rp-stat"><span class="rp-stat-num">${t.skipped}</span><span class="rp-stat-lbl">Skipped</span></div>
    <div class="rp-stat"><span class="rp-stat-num">${t.gatesPassed}<small>/${t.gates}</small></span><span class="rp-stat-lbl">Gates passed</span></div>`;

  timeline.innerHTML = trace.map((mt, idx) => {
    const c = actionCounts(mt);
    const open = rpOpenMoves.has(idx);
    const state = c.failed ? "fail" : "done";
    return `
      <li class="rp-move ${state}${open ? " open" : ""}${focusIdx === idx ? " focus" : ""}" data-idx="${idx}">
        <button type="button" class="rp-move-btn" aria-expanded="${open}">
          <span class="rp-dot">${state === "fail" ? ICONS.cross : ICONS.check}</span>
          <span class="rp-move-main">
            <span class="rp-move-name"><span class="rp-move-id">${esc(mt.move_id)}</span>${esc(mt.name)}</span>
            <span class="rp-move-meta">${c.executed} of ${plural(c.total, "action")} ran${c.skipped ? ` · ${c.skipped} skipped` : ""}${c.gates ? ` · ${c.gatesPassed}/${c.gates} gates` : ""}</span>
          </span>
          <span class="rp-chev">${ICONS.chevD}</span>
        </button>
        <div class="rp-move-body">${open ? renderMoveBody(mt) : ""}</div>
      </li>`;
  }).join("");

  timeline.querySelectorAll(".rp-move-btn").forEach(btn => btn.addEventListener("click", () => {
    const idx = Number(btn.closest(".rp-move").dataset.idx);
    if (rpOpenMoves.has(idx)) rpOpenMoves.delete(idx); else rpOpenMoves.add(idx);
    renderRunPanel();
  }));
}

/** Expanded move: summary, gates, then each action with what it produced or why it was skipped. */
function renderMoveBody(mt) {
  const actions = mt.actions || [];
  const gates = mt.gates || [];
  let html = "";
  if (mt.summary) html += `<p class="rp-summary">${esc(mt.summary)}</p>`;

  if (gates.length) {
    html += `<div class="rp-sub-label">Gates</div><ul class="rp-items">`;
    gates.forEach(g => {
      html += `
        <li class="rp-item ${g.passed ? "ran" : "fail"}">
          <span class="rp-item-icon">${g.passed ? ICONS.check : ICONS.cross}</span>
          <div class="rp-item-main">
            <div class="rp-item-name">${esc(g.name)} <span class="rp-item-id">${esc(g.id)}</span></div>
            <div class="rp-item-out">${esc(g.decision)}</div>
            ${g.details ? `<div class="rp-item-note">${esc(g.details)}</div>` : ""}
          </div>
        </li>`;
    });
    html += `</ul>`;
  }

  if (actions.length) {
    html += `<div class="rp-sub-label">Actions</div><ul class="rp-items">`;
    actions.forEach(a => {
      const cls = a.status === "EXECUTED" ? "ran" : a.status === "FAILED" ? "fail" : "skipped";
      const icon = cls === "ran" ? ICONS.check : cls === "fail" ? ICONS.cross : ICONS.skip;
      const dur = cls === "ran" && a.duration_ms ? `<span class="rp-item-dur">${a.duration_ms >= 0.1 ? Number(a.duration_ms).toFixed(1) : "<0.1"} ms</span>` : "";
      const out = cls === "skipped"
        ? `<div class="rp-item-note">Skipped${a.skip_reason ? `: ${esc(a.skip_reason)}` : ""}</div>`
        : (a.output_summary ? `<div class="rp-item-out">${esc(a.output_summary)}</div>` : "");
      html += `
        <li class="rp-item ${cls}">
          <span class="rp-item-icon">${icon}</span>
          <div class="rp-item-main">
            <div class="rp-item-name">${esc(a.name)} <span class="rp-item-id">${esc(a.id)}</span>${dur}</div>
            ${out}
          </div>
        </li>`;
    });
    html += `</ul>`;
  }
  return html || '<p class="rp-summary">No actions recorded for this move.</p>';
}
