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
  const flowModalBtn = document.getElementById("flowModalBtn");
  const closeFlowModalBtn = document.getElementById("closeFlowModalBtn");
  const moveFlowModal = document.getElementById("moveFlowModal");

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

  if (flowModalBtn && moveFlowModal) {
    flowModalBtn.addEventListener("click", () => {
      openMoveFlowModal();
    });
  }

  if (closeFlowModalBtn && moveFlowModal) {
    closeFlowModalBtn.addEventListener("click", () => {
      moveFlowModal.style.display = "none";
    });
  }

  if (moveFlowModal) {
    moveFlowModal.addEventListener("click", (e) => {
      if (e.target === moveFlowModal) {
        moveFlowModal.style.display = "none";
      }
    });
  }

  if (uploadBtn && fileUploadInput) {
    uploadBtn.addEventListener("click", () => {
      fileUploadInput.click();
    });
    document.getElementById("startUploadBtn")?.addEventListener("click", () => fileUploadInput.click());
    // The info icon inside the upload button only explains; it does not open the file picker.
    uploadBtn.querySelector(".info-tip")?.addEventListener("click", (e) => e.stopPropagation());

    fileUploadInput.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
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

        // Upload custom contract JSON to backend
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
        notify({ type: "success", title: "Document uploaded",
                 file: resp.display_name || resp.original_filename,
                 message: "Added as a new case. Generating its brief now." });

        // Refresh case list and immediately display the uploaded case
        await loadCaseList(resp.case_id);
      } catch (err) {
        const [summary, list] = splitProblems(err.message);
        notify({ type: "error", title: "Upload failed", file: file.name, message: summary, details: list });
      } finally {
        fileUploadInput.value = "";
      }
    });
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
      // Only evaluate straight away when a case was asked for (e.g. just uploaded).
      // Otherwise the start panel stays up until the user picks a case.
      if (preferredCaseId && data.cases.map(String).includes(String(preferredCaseId))) {
        caseSelect.value = preferredCaseId;
        loadCaseBrief(preferredCaseId);
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
 * Case or date changed: highlight "Generate brief" until the user clicks it.
 */
function markInputsChanged() {
  const caseSelect = document.getElementById("caseSelect");
  const reloadBtn = document.getElementById("reloadBtn");
  caseSelect.classList.remove("needs-choice");
  reloadBtn.classList.toggle("needs-generate", !!caseSelect.value);
}

const MIN_LOADING_MS = 1000;

/**
 * "Generate brief" click: spinner on the button for at least 1 second, then show the brief.
 */
async function generateBrief(caseId) {
  const reloadBtn = document.getElementById("reloadBtn");
  reloadBtn.classList.remove("needs-generate");
  reloadBtn.classList.add("is-generating");
  reloadBtn.disabled = true;
  try {
    await loadCaseBrief(caseId, MIN_LOADING_MS);
  } finally {
    reloadBtn.classList.remove("is-generating");
    reloadBtn.disabled = false;
  }
}

/**
 * Fetch executive brief generated by Kozmo Move Orchestrator.
 * minMs: keep the loading state at least this long before rendering.
 */
async function loadCaseBrief(caseId, minMs = 0) {
  renderPipelineRunning();
  const briefEl = document.getElementById("briefContainer");
  briefEl?.classList.add("is-loading");
  const minDelay = new Promise((resolve) => setTimeout(resolve, minMs));
  try {
    const asOf = document.getElementById("asOfInput")?.value;
    // POST /api/process runs the pipeline and saves the result (EvaluationResults).
    const [res] = await Promise.all([
      fetch(`${API_BASE}/api/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId, as_of: asOf || null }),
      }),
      minDelay,
    ]);
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Error evaluating case");
    }
    const brief = await res.json();

    // Store the move trace for the Move Flow modal
    currentMoveTrace = brief.meta?.move_trace || [];
    // Saved result id: needed to record a PDF export of this brief.
    currentResultId = brief.meta?.result_id ?? null;
    const stamp = document.getElementById("exportStamp");
    if (stamp) stamp.textContent = "";

    // Render the Kozmo Move pipeline bar
    renderMovePipeline(currentMoveTrace);
    renderBrief(brief);
    showBrief();
  } catch (err) {
    console.error("Error evaluating brief:", err);
    const [summary, list] = splitProblems(err.message);
    notify({ type: "error", title: "Couldn't generate the brief", message: summary, details: list });
  } finally {
    briefEl?.classList.remove("is-loading");
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
    const stepEl = document.createElement("span");
    stepEl.className = mt.status === "PENDING" ? "pipe-step" : "pipe-step active";

    // Count executed vs skipped actions
    const actions = mt.actions || [];
    const executed = actions.filter(a => a.status === "EXECUTED").length;
    const skipped = actions.filter(a => a.status === "SKIPPED").length;

    stepEl.textContent = mt.move_id;
    stepEl.title = mt.status === "PENDING" ? `${mt.name} — not run yet`
      : `${mt.name} — ${executed} executed, ${skipped} skipped`;
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
  container.innerHTML = '<span class="pipe-step active">Executing Kozmo Move Pipeline...</span>';
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
  renderSidebarCase(meta, vendor, rec);

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


/**
 * Sidebar "Current brief" card: vendor, decision and policy at a glance.
 */
function renderSidebarCase(meta, vendor, rec) {
  const card = document.getElementById("sbCaseCard");
  if (!card) return;
  card.hidden = false;
  document.getElementById("sbCaseVendor").textContent = vendor.name || "—";
  document.getElementById("sbCaseService").textContent = vendor.service || "";
  const decision = document.getElementById("sbCaseDecision");
  const primary = rec.primary || "—";
  const low = primary.toLowerCase();
  decision.textContent = primary;
  decision.className = `sb-decision${low.includes("renew") ? " renew" : low.includes("switch") ? " switch" : ""}`;
  document.getElementById("sbCaseNotice").textContent = meta.notice_deadline ? `Notice by ${meta.notice_deadline}` : "";
  // POLICY DISABLED for this version
  // document.getElementById("sbCasePolicy").textContent = meta.policy_version === 0 ? "Default policy"
  //   : meta.policy_version == null ? "Draft policy" : `Policy v${meta.policy_version}`;
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
// KOZMO MOVE FLOW MODAL — Execution Trace Viewer
// ===================================================================

/**
 * Open the Move Flow Modal and populate with current trace data
 */
function openMoveFlowModal() {
  const modal = document.getElementById("moveFlowModal");
  const tabsContainer = document.getElementById("moveTabsContainer");
  const detailContainer = document.getElementById("moveDetailContainer");

  if (!currentMoveTrace || currentMoveTrace.length === 0) {
    detailContainer.innerHTML = `
      <div class="move-empty-state">
        <p>No move trace available. Please evaluate a case first using <strong>Re-evaluate</strong>.</p>
      </div>`;
    tabsContainer.innerHTML = "";
    modal.style.display = "flex";
    return;
  }

  // Build tabs
  tabsContainer.innerHTML = currentMoveTrace.map((mt, idx) => {
    const actions = mt.actions || [];
    const executed = actions.filter(a => a.status === "EXECUTED").length;
    const skipped = actions.filter(a => a.status === "SKIPPED").length;
    return `
      <button class="move-tab-btn ${idx === 0 ? 'active' : ''}" data-move-idx="${idx}" onclick="selectMoveTab(${idx})">
        <span class="tab-move-id">${mt.move_id}</span>
        <span class="tab-move-stats">${executed}✓ ${skipped > 0 ? skipped + '⊘' : ''}</span>
      </button>`;
  }).join("");

  // Show first move detail
  renderMoveDetail(0);
  modal.style.display = "flex";
}

/**
 * Handle tab click — switch active tab and render detail
 */
function selectMoveTab(idx) {
  // Update active tab
  document.querySelectorAll(".move-tab-btn").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.moveIdx) === idx);
  });
  renderMoveDetail(idx);
}

/**
 * Render the detail card for a specific move
 */
function renderMoveDetail(index) {
  const container = document.getElementById("moveDetailContainer");
  const mt = currentMoveTrace[index];

  if (!mt) {
    container.innerHTML = '<p>No data for this move.</p>';
    return;
  }

  const actions = mt.actions || [];
  const gates = mt.gates || [];
  const executed = actions.filter(a => a.status === "EXECUTED").length;
  const skipped = actions.filter(a => a.status === "SKIPPED").length;

  // Header
  let html = `
    <div class="move-header-card">
      <div class="move-header-top">
        <span class="move-id-badge">${mt.move_id}</span>
        <h4 class="move-title">${mt.name}</h4>
        <span class="move-verb-tag">${mt.verb}</span>
      </div>
      <p class="move-summary">${mt.summary || '—'}</p>
      <div class="move-stats-bar">
        <span class="stat-pill executed">${executed} Executed</span>
        <span class="stat-pill skipped">${skipped} Skipped</span>
        <span class="stat-pill gates">${gates.length} Gate${gates.length !== 1 ? 's' : ''}</span>
      </div>
    </div>`;

  // Gates Section
  if (gates.length > 0) {
    html += `<div class="move-section-label">Gates & Conditions</div>`;
    html += `<div class="gates-grid">`;
    gates.forEach(g => {
      const passClass = g.passed ? "gate-passed" : "gate-failed";
      const passIcon = g.passed ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
      html += `
        <div class="gate-card ${passClass}">
          <div class="gate-header">
            <span class="gate-id">${g.id}</span>
            <span class="gate-icon ${g.passed ? 'pass' : 'fail'}" title="${g.passed ? 'Passed' : 'Failed'}">${passIcon}</span>
          </div>
          <div class="gate-name">${g.name}</div>
          <div class="gate-decision">${g.decision}</div>
          ${g.details ? `<div class="gate-details">${g.details}</div>` : ''}
        </div>`;
    });
    html += `</div>`;
  }

  // Actions Section
  if (actions.length > 0) {
    html += `<div class="move-section-label">Actions</div>`;
    html += `<div class="actions-list">`;
    actions.forEach(a => {
      const isExecuted = a.status === "EXECUTED";
      const statusClass = isExecuted ? "executed" : "skipped";
      const statusIcon = `<span class="status-dot ${statusClass}" title="${isExecuted ? "Executed" : "Skipped"}"></span>`;
      const durationStr = isExecuted && a.duration_ms ? `${a.duration_ms.toFixed(1)}ms` : "";

      html += `
        <div class="action-row ${statusClass}">
          <div class="action-status-icon">${statusIcon}</div>
          <div class="action-info">
            <div class="action-id-name">
              <span class="action-id">${a.id}</span>
              <span class="action-name">${a.name}</span>
            </div>
            ${isExecuted && a.output_summary
              ? `<div class="action-output">${a.output_summary}</div>`
              : ''}
            ${!isExecuted && a.skip_reason
              ? `<div class="action-skip-reason"><em>Skipped: ${a.skip_reason}</em></div>`
              : ''}
          </div>
          ${durationStr ? `<div class="action-duration">${durationStr}</div>` : ''}
        </div>`;
    });
    html += `</div>`;
  }

  container.innerHTML = html;
}
