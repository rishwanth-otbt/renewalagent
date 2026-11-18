/**
 * Renewal Policy settings page (M1).
 * Grouped dropdowns built from the backend field catalog, live impact preview,
 * save as a new version, history, and a first-run wizard.
 */

const API_BASE = window.location.protocol.startsWith("http")
  ? ""
  : "http://localhost:8000";

let catalog = [];      // [{key, title, description, fields:[{key,label,help,unit,choices,default}]}]
let defaults = {};     // default policy
let saved = null;      // {version, is_default, saved_by, saved_at, note, policy}
let draft = {};        // policy being edited

const WIZARD_STEPS = [
  { group: "renew", key: "max_increase_pct", question: "Up to what price increase should a renewal go ahead without negotiating?" },
  { group: "renew", key: "min_performance_rating", question: "What supplier performance rating is good enough to renew as-is?" },
  { group: "switch", key: "price_shock_pct", question: "From what price increase should we look at switching vendor?" },
  { group: "licenses", key: "target_utilization_pct", question: "Below what seat utilization are licenses wasted (shelfware)?" },
  { group: "deadlines", key: "urgent_notice_days", question: "How many days before the notice cutoff should we treat it as urgent?" },
];
let wizardIndex = 0;

const clone = (o) => JSON.parse(JSON.stringify(o));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = (v) => JSON.stringify(v);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function fmtValue(v, unit) {
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (unit === "%") return `${v}%`;
  return unit ? `${v} ${unit}` : String(v);
}

function fieldMeta(group, key) {
  const g = catalog.find(x => x.key === group);
  return g && g.fields.find(f => f.key === key);
}

function fmtCurrency(v) {
  if (v === null || v === undefined) return "—";
  return `$${Math.round(v).toLocaleString()}`;
}

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("saveBtn").addEventListener("click", savePolicy);
  document.getElementById("resetDefaultsBtn").addEventListener("click", () => { draft = clone(defaults); renderForm(); schedulePreview(); });
  document.getElementById("previewAsOf").addEventListener("change", schedulePreview);
  document.getElementById("wizardBtn").addEventListener("click", openWizard);
  document.getElementById("closeWizardBtn").addEventListener("click", closeWizard);
  document.getElementById("wizardBackBtn").addEventListener("click", () => { if (wizardIndex > 0) { wizardIndex--; renderWizard(); } });
  document.getElementById("wizardNextBtn").addEventListener("click", wizardNext);
  try {
    const savedName = localStorage.getItem("policySavedBy");
    if (savedName) document.getElementById("savedBy").value = savedName;
  } catch (e) { /* storage unavailable */ }

  await loadPolicy();
  if (saved && saved.is_default) openWizard();
});

async function loadPolicy() {
  try {
    const res = await fetch(`${API_BASE}/api/policy`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    catalog = body.catalog;
    defaults = body.defaults;
    saved = body.current;
    draft = clone(saved.policy);
    renderVersion();
    renderForm();
    renderPreviewIdle();
    loadHistory();
  } catch (err) {
    document.getElementById("versionBox").textContent = `Cannot reach API (${err.message}). Is the backend running?`;
  }
}

function renderVersion() {
  const box = document.getElementById("versionBox");
  if (saved.is_default) {
    box.innerHTML = `<strong>Built-in defaults</strong><span>No policy saved yet (version 0)</span>`;
    box.className = "policy-version-box warn";
  } else {
    box.innerHTML = `<strong>Version ${saved.version}</strong><span>Saved by ${esc(saved.saved_by)} · ${esc((saved.saved_at || "").replace("T", " ").slice(0, 16))}</span>`;
    box.className = "policy-version-box";
  }
}

// ---------------------------------------------------------------------------
// Form: one card per group, one dropdown per rule
// ---------------------------------------------------------------------------
function optionsFor(f, current) {
  const values = [...f.choices];
  if (!values.some(v => same(v, current))) values.push(current);
  if (!values.some(v => same(v, f.default))) values.push(f.default);
  if (values.every(v => typeof v === "number")) values.sort((a, b) => a - b);
  return values.map(v => {
    const tags = [];
    if (same(v, f.default)) tags.push("default");
    return `<option value="${esc(enc(v))}" ${same(v, current) ? "selected" : ""}>${esc(fmtValue(v, f.unit))}${tags.length ? `  (${tags.join(", ")})` : ""}</option>`;
  }).join("");
}

function renderForm() {
  const form = document.getElementById("policyForm");
  form.innerHTML = catalog.map(g => `
    <fieldset class="policy-group">
      <legend>${esc(g.title)}</legend>
      ${g.description ? `<p class="policy-muted">${esc(g.description)}</p>` : ""}
      ${g.fields.map(f => {
        const cur = draft[g.key][f.key];
        const changedFromSaved = !same(cur, saved.policy[g.key][f.key]);
        const differsFromDefault = !same(cur, f.default);
        return `
        <div class="policy-row ${changedFromSaved ? "changed" : ""}">
          <label class="policy-field-label" for="f_${g.key}_${f.key}">${esc(f.label)}</label>
          <select id="f_${g.key}_${f.key}" data-group="${g.key}" data-key="${f.key}">${optionsFor(f, cur)}</select>
          <div class="policy-help">${esc(f.help)}${differsFromDefault ? ` <span class="policy-default">Default: ${esc(fmtValue(f.default, f.unit))}</span>` : ""}</div>
        </div>`;
      }).join("")}
    </fieldset>
  `).join("");

  form.querySelectorAll("select").forEach(sel => {
    sel.addEventListener("change", () => {
      draft[sel.dataset.group][sel.dataset.key] = JSON.parse(sel.value);
      renderForm();
      schedulePreview();
    });
  });
}

// ---------------------------------------------------------------------------
// Impact preview
// ---------------------------------------------------------------------------
let previewTimer = null;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 250);
}

function renderPreviewIdle() {
  document.getElementById("previewSummary").textContent = "Change a value to see its impact.";
  document.querySelector("#previewTable tbody").innerHTML = "";
}

async function runPreview() {
  const summary = document.getElementById("previewSummary");
  const errorsEl = document.getElementById("policyErrors");
  if (same(draft, saved.policy)) {
    renderPreviewIdle();
    errorsEl.hidden = true;
    return;
  }
  summary.textContent = "Running all cases…";
  const asOf = document.getElementById("previewAsOf").value || null;
  try {
    const res = await fetch(`${API_BASE}/api/policy/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy: draft, as_of: asOf }),
    });
    const body = await res.json();
    if (res.status === 422) {
      showErrors(body.detail);
      summary.textContent = "Fix the problems below to see the impact.";
      document.querySelector("#previewTable tbody").innerHTML = "";
      return;
    }
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    errorsEl.hidden = true;
    summary.innerHTML = `<strong>${body.decisions_changed}</strong> of ${body.cases.length} cases change decision (as of ${esc(body.as_of)}).`;
    document.querySelector("#previewTable tbody").innerHTML = body.cases.map(c => {
      if (c.error) return `<tr><td>${esc(c.case_id)}</td><td colspan="2" class="policy-muted">${esc(c.error)}</td></tr>`;
      const cls = c.decision_changed ? "high" : (c.changed_fields.length ? "warn" : "neutral");
      const extra = c.changed_fields.filter(k => k !== "decision").map(k => {
        const a = c.current[k], b = c.draft[k];
        return k === "negotiation_target_acv" ? `target ${fmtCurrency(a)} → ${fmtCurrency(b)}` : `${k.replace(/_/g, " ")}: ${a} → ${b}`;
      });
      return `
        <tr class="${c.decision_changed ? "preview-changed" : ""}" title="${esc(c.draft.decided_by)}">
          <td><strong>${esc(c.vendor)}</strong><div class="policy-muted">${esc(c.case_id)}</div></td>
          <td>${esc(c.current.decision)}</td>
          <td><span class="status-chip ${cls}">${esc(c.draft.decision)}</span>${extra.length ? `<div class="policy-muted">${esc(extra.join("; "))}</div>` : ""}</td>
        </tr>`;
    }).join("");
  } catch (err) {
    summary.textContent = `Preview failed: ${err.message}`;
  }
}

function showErrors(detail) {
  const el = document.getElementById("policyErrors");
  const errors = (detail && detail.errors) || [typeof detail === "string" ? detail : "Policy is invalid"];
  el.innerHTML = `<strong>This policy contradicts itself:</strong><ul>${errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul>`;
  el.hidden = false;
}

// ---------------------------------------------------------------------------
// Save + history
// ---------------------------------------------------------------------------
async function savePolicy() {
  const savedBy = document.getElementById("savedBy").value.trim();
  const note = document.getElementById("saveNote").value.trim() || null;
  const status = document.getElementById("saveStatus");
  if (!savedBy) {
    status.textContent = "Enter your name so the version shows who saved it.";
    document.getElementById("savedBy").focus();
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/policy`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy: draft, saved_by: savedBy, note }),
    });
    const body = await res.json();
    if (res.status === 422) { showErrors(body.detail); status.textContent = "Not saved."; return; }
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    try { localStorage.setItem("policySavedBy", savedBy); } catch (e) { /* ignore */ }
    document.getElementById("policyErrors").hidden = true;
    document.getElementById("saveNote").value = "";
    status.textContent = `Saved as version ${body.version}. New briefs use it immediately.`;
    saved = body;
    draft = clone(saved.policy);
    renderVersion();
    renderForm();
    renderPreviewIdle();
    loadHistory();
  } catch (err) {
    status.textContent = `Save failed: ${err.message}`;
  }
}

async function loadHistory() {
  const list = document.getElementById("historyList");
  try {
    const res = await fetch(`${API_BASE}/api/policy/history`);
    const body = await res.json();
    if (!body.versions.length) {
      list.innerHTML = `<li class="policy-muted">No saved versions yet — built-in defaults are in use.</li>`;
      return;
    }
    list.innerHTML = body.versions.map((v, i) => {
      const prev = body.versions[i + 1] ? body.versions[i + 1].policy : defaults;
      const diffs = [];
      catalog.forEach(g => g.fields.forEach(f => {
        if (!same(v.policy[g.key][f.key], prev[g.key][f.key])) {
          diffs.push(`${f.label}: ${fmtValue(prev[g.key][f.key], f.unit)} → ${fmtValue(v.policy[g.key][f.key], f.unit)}`);
        }
      }));
      return `
        <li>
          <div><strong>v${v.version}</strong> · ${esc(v.saved_by)} · ${esc((v.saved_at || "").replace("T", " ").slice(0, 16))}</div>
          ${v.note ? `<div class="policy-muted">“${esc(v.note)}”</div>` : ""}
          <div class="policy-muted">${diffs.length ? esc(diffs.join("; ")) : "No rule changes"}</div>
          ${i > 0 ? `<button type="button" class="link-btn" data-version="${v.version}">Load into editor</button>` : ""}
        </li>`;
    }).join("");
    list.querySelectorAll("button[data-version]").forEach(btn => btn.addEventListener("click", () => {
      const v = body.versions.find(x => String(x.version) === btn.dataset.version);
      draft = clone(v.policy);
      renderForm();
      schedulePreview();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));
  } catch (err) {
    list.innerHTML = `<li class="policy-muted">History unavailable.</li>`;
  }
}

// ---------------------------------------------------------------------------
// First-run wizard: the five rules that matter most, one question at a time
// ---------------------------------------------------------------------------
function openWizard() {
  if (!catalog.length) return;
  wizardIndex = 0;
  renderWizard();
  document.getElementById("wizardModal").style.display = "flex";
}

function closeWizard() {
  document.getElementById("wizardModal").style.display = "none";
}

function renderWizard() {
  const step = WIZARD_STEPS[wizardIndex];
  const f = fieldMeta(step.group, step.key);
  const cur = draft[step.group][step.key];
  document.getElementById("wizardProgress").textContent = `Question ${wizardIndex + 1} of ${WIZARD_STEPS.length}`;
  const values = [...f.choices];
  if (!values.some(v => same(v, cur))) values.push(cur);
  if (values.every(v => typeof v === "number")) values.sort((a, b) => a - b);
  document.getElementById("wizardStep").innerHTML = `
    <h4 class="wizard-question">${esc(step.question)}</h4>
    <p class="policy-muted">${esc(f.help)}</p>
    <div class="wizard-choices">
      ${values.map(v => `
        <button type="button" class="wizard-choice ${same(v, cur) ? "selected" : ""}" data-value="${esc(enc(v))}">
          ${esc(fmtValue(v, f.unit))}${same(v, f.default) ? `<span class="wizard-rec">recommended</span>` : ""}
        </button>`).join("")}
    </div>`;
  document.querySelectorAll(".wizard-choice").forEach(btn => btn.addEventListener("click", () => {
    draft[step.group][step.key] = JSON.parse(btn.dataset.value);
    renderWizard();
  }));
  document.getElementById("wizardBackBtn").disabled = wizardIndex === 0;
  document.getElementById("wizardNextBtn").textContent = wizardIndex === WIZARD_STEPS.length - 1 ? "Review all rules →" : "Next →";
}

function wizardNext() {
  if (wizardIndex < WIZARD_STEPS.length - 1) {
    wizardIndex++;
    renderWizard();
    return;
  }
  closeWizard();
  renderForm();
  schedulePreview();
  document.getElementById("saveStatus").textContent = "Review the other rules (defaults are filled in), check the impact, then save.";
  document.getElementById("savedBy").focus();
}
