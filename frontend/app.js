/**
 * IT Vendor Renewal — Executive Decision Brief
 * Frontend Rendering Engine (POC 1)
 */

// Robust API Base URL resolution:
// If served by the FastAPI server, use relative path ("")
// If opened via file:// or another local dev server port, use "http://localhost:8000"
const API_BASE = (window.location.protocol.startsWith("http") && (window.location.port === "8000" || window.location.port === ""))
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
  loadCaseList();
});

let currentMoveTrace = [];

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

  caseSelect.addEventListener("change", (e) => {
    if (e.target.value) {
      loadCaseBrief(e.target.value);
    }
  });

  const asOfInput = document.getElementById("asOfInput");
  if (asOfInput) {
    asOfInput.addEventListener("change", () => {
      if (caseSelect.value) loadCaseBrief(caseSelect.value);
    });
  }

  reloadBtn.addEventListener("click", () => {
    if (caseSelect.value) {
      loadCaseBrief(caseSelect.value);
    }
  });

  printBtn.addEventListener("click", () => {
    window.print();
  });

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

    fileUploadInput.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);

        // Upload custom contract JSON to backend
        const res = await fetch(`${API_BASE}/api/upload`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, data: parsed })
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Server rejected JSON file");
        }
        const resp = await res.json();
        alert(`Uploaded "${resp.original_filename}" as ${resp.case_id} (${resp.renewal_id})`);

        // Refresh case list and immediately display the uploaded case
        await loadCaseList(resp.case_id);
      } catch (err) {
        alert(`Error uploading JSON: ${err.message}`);
      } finally {
        fileUploadInput.value = "";
      }
    });
  }
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
    
    caseSelect.innerHTML = "";
    if (data.cases && data.cases.length > 0) {
      data.cases.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c.replace(/_/g, " ").toUpperCase();
        caseSelect.appendChild(opt);
      });
      // Select the preferred case if provided, otherwise the first case
      const targetCase = (preferredCaseId && data.cases.includes(preferredCaseId)) 
        ? preferredCaseId 
        : data.cases[0];
      caseSelect.value = targetCase;
      loadCaseBrief(targetCase);
    } else {
      caseSelect.innerHTML = '<option value="">No cases found</option>';
    }
  } catch (err) {
    console.error("Error loading case list:", err);
    caseSelect.innerHTML = '<option value="">Cannot reach API (Is backend running?)</option>';
  }
}

/**
 * Fetch executive brief generated by Kozmo Move Orchestrator
 */
async function loadCaseBrief(caseId) {
  renderPipelineRunning();
  try {
    const asOf = document.getElementById("asOfInput")?.value;
    const query = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
    const res = await fetch(`${API_BASE}/api/case/${encodeURIComponent(caseId)}${query}`);
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Error evaluating case");
    }
    const brief = await res.json();

    // Store the move trace for the Move Flow modal
    currentMoveTrace = brief.meta?.move_trace || [];

    // Render the Kozmo Move pipeline bar
    renderMovePipeline(currentMoveTrace);
    renderBrief(brief);
  } catch (err) {
    console.error("Error evaluating brief:", err);
    alert(`Orchestrator execution error: ${err.message}`);
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
    stepEl.className = "pipe-step active";

    // Count executed vs skipped actions
    const actions = mt.actions || [];
    const executed = actions.filter(a => a.status === "EXECUTED").length;
    const skipped = actions.filter(a => a.status === "SKIPPED").length;

    stepEl.textContent = mt.move_id;
    stepEl.title = `${mt.name} — ${executed} executed, ${skipped} skipped`;
    container.appendChild(stepEl);

    if (idx < movesToShow.length - 1) {
      const arrow = document.createElement("span");
      arrow.className = "pipe-arrow";
      arrow.textContent = "➔";
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

  // 2. Section 1: Financial Impact
  const finTableBody = document.querySelector("#financialTable tbody");
  const currentMonths = meta.current_term_months ?? '—';
  const proposedMonths = vendor.proposed_term_months ?? '—';
  const termDelta = (typeof proposedMonths === "number" && typeof currentMonths === "number") ? proposedMonths - currentMonths : null;
  const termDeltaStr = termDelta === null ? "—" : termDelta > 0 ? `+${termDelta} months extension` : (termDelta === 0 ? "Same duration" : `${termDelta} months`);

  finTableBody.innerHTML = `
    <tr>
      <td><strong>Annual Contract Value (ACV)</strong></td>
      <td>${fmtCurrency(fin.current_acv)}</td>
      <td>${fmtCurrency(fin.proposed_acv)}</td>
      <td><span class="status-chip ${fin.increase_pct > 10 ? 'high' : (fin.increase_pct > 0 ? 'warn' : 'ok')}">${fmtPct(fin.increase_pct)} (${fmtCurrency(fin.increase_usd)})</span></td>
    </tr>
    <tr>
      <td><strong>Provisioned License Quantity</strong></td>
      <td>${seats.total?.toLocaleString()}</td>
      <td>${seats.total?.toLocaleString()}</td>
      <td>0% (Hold volume)</td>
    </tr>
    <tr>
      <td><strong>Average Per-Seat Cost (Annual)</strong></td>
      <td>$${seats.current_unit_price?.toLocaleString()}</td>
      <td>$${seats.proposed_unit_price?.toLocaleString()}</td>
      <td>${(seats.proposed_unit_price != null && seats.current_unit_price != null) ? `+$${(seats.proposed_unit_price - seats.current_unit_price).toLocaleString()} / seat` : "—"}</td>
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
  document.getElementById("histCurrentAsk").textContent = `${history.current_increase_pct}%`;
  document.getElementById("histVsAvg").textContent = `${fmtPct(history.current_increase_vs_avg)}`;
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
  perfTableBody.innerHTML = `
    <tr>
      <td>Service Availability (Uptime)</td>
      <td>${perf.uptime_contracted}%</td>
      <td><strong>${perf.uptime_actual}%</strong></td>
      <td><span class="status-chip ${perf.uptime_gap_pct > 0.1 ? 'below' : 'ok'}">${perf.uptime_gap_pct > 0.1 ? 'Below Target' : 'Met'}</span></td>
    </tr>
    <tr>
      <td>Support SLA Achievement</td>
      <td>90.0%</td>
      <td><strong>${perf.support_sla_pct}%</strong></td>
      <td><span class="status-chip ${perf.support_sla_pct < 85 ? 'below' : 'ok'}">${perf.support_sla_pct < 85 ? 'Sub-standard' : 'Met'}</span></td>
    </tr>
    <tr>
      <td>Critical Production Incidents</td>
      <td>0</td>
      <td><strong>${perf.critical_incidents}</strong></td>
      <td><span class="status-chip ${perf.critical_incidents > 0 ? 'below' : 'ok'}">${perf.critical_incidents > 0 ? 'Requires Review' : 'Zero Outages (Met)'}</span></td>
    </tr>
    <tr>
      <td>License Seat Utilization</td>
      <td>90.0%</td>
      <td><strong>${seats.utilization_pct}%</strong></td>
      <td><span class="status-chip ${seats.utilization_pct >= 90 ? 'ok' : 'warn'}">${seats.utilization_pct >= 90 ? 'Optimal Adoption' : 'Optimization Target'}</span></td>
    </tr>
    <tr>
      <td>Roadmap Milestones Delivered</td>
      <td>${perf.roadmap_total} of ${perf.roadmap_total}</td>
      <td><strong>${perf.roadmap_delivered} of ${perf.roadmap_total}</strong></td>
      <td><span class="status-chip ${perf.roadmap_delayed?.length > 0 ? 'below' : 'ok'}">${perf.roadmap_delayed?.length > 0 ? 'Delayed Delivery' : 'On Track'}</span></td>
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
      const passIcon = g.passed ? "✅" : "❌";
      html += `
        <div class="gate-card ${passClass}">
          <div class="gate-header">
            <span class="gate-id">${g.id}</span>
            <span class="gate-icon">${passIcon}</span>
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
      const statusIcon = isExecuted ? "🟢" : "⚪";
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
