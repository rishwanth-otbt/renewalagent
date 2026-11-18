/**
 * Renewal Desk — a short guided tour of the brief page.
 * Runs once on the first visit; "Take a tour" starts it again.
 */
(function () {
  const STEPS = [
    { el: "#uploadBtn", title: "Upload documents",
      text: "Opens a panel to drop or browse a contract JSON file. After it uploads, press Run agent to generate the brief." },
    { el: "#caseSelect", title: "Or pick an existing case",
      text: "Every case already loaded is listed here. Choosing one generates its brief." },
    { el: "#asOfInput", title: "Assessment date",
      text: "Leave it blank for today, or fix a date so the brief is repeatable in a demo." },
    { el: "#reloadBtn", title: "Generate brief",
      text: "Runs the move pipeline again for the selected case and redraws the brief." },
    { el: ".pipeline-container", title: "Move pipeline",
      text: "Shows each move the agent ran, from goals to the final recommendation. Click a move to see its actions." },
    { el: "#runPanelBtn", title: "Agent run",
      text: "Opens the side panel: every move the agent ran, and inside each one which gates passed and which actions ran or were skipped." },
    { el: "#printBtn", title: "Export PDF",
      text: "Once a brief is ready, save or print it as a one-page PDF." },
  ];
  const SEEN_KEY = "renewalDesk.tourSeen";

  let i = 0, ring, pop;

  const visible = (el) => el && el.getClientRects().length > 0 && el.getBoundingClientRect().width > 0;

  function build() {
    ring = document.createElement("div");
    ring.className = "tour-ring";
    pop = document.createElement("div");
    pop.className = "tour-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-live", "polite");
    document.body.append(ring, pop);
  }

  function place() {
    const step = STEPS[i];
    const el = document.querySelector(step.el);
    const r = el.getBoundingClientRect();
    const pad = 6;
    Object.assign(ring.style, {
      top: `${r.top - pad}px`, left: `${r.left - pad}px`,
      width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
    });
    const pw = pop.offsetWidth, ph = pop.offsetHeight, gap = 14;
    let top = r.bottom + gap;
    if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - gap);
    let left = r.left;
    if (r.right + gap + pw < window.innerWidth && r.left < 300) { left = r.right + gap; top = Math.max(8, r.top); }
    left = Math.min(Math.max(8, left), window.innerWidth - pw - 8);
    Object.assign(pop.style, { top: `${top}px`, left: `${left}px` });
  }

  function show(dir = 1) {
    // Skip steps whose target is hidden (e.g. the sidebar on a phone).
    while (i >= 0 && i < STEPS.length && !visible(document.querySelector(STEPS[i].el))) i += dir;
    if (i < 0 || i >= STEPS.length) return end();
    const step = STEPS[i];
    const el = document.querySelector(step.el);
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    pop.innerHTML = `
      <div class="tour-count">Step ${i + 1} of ${STEPS.length}</div>
      <h4>${step.title}</h4>
      <p>${step.text}</p>
      <div class="tour-actions">
        <button type="button" class="tour-skip">Skip tour</button>
        <span>
          ${i > 0 ? '<button type="button" class="tour-back">Back</button>' : ""}
          <button type="button" class="btn-primary tour-next">${i === STEPS.length - 1 ? "Done" : "Next"}</button>
        </span>
      </div>`;
    pop.querySelector(".tour-skip").onclick = end;
    pop.querySelector(".tour-next").onclick = () => { i += 1; show(1); };
    const back = pop.querySelector(".tour-back");
    if (back) back.onclick = () => { i -= 1; show(-1); };
    place();
    setTimeout(place, 250);
    pop.querySelector(".tour-next").focus();
  }

  function end() {
    ring?.remove(); pop?.remove(); ring = pop = null;
    window.removeEventListener("resize", onMove);
    window.removeEventListener("scroll", onMove, true);
    document.removeEventListener("keydown", onKey);
    try { localStorage.setItem(SEEN_KEY, "1"); } catch (_) { /* storage blocked: fine */ }
  }

  const onMove = () => { if (pop) place(); };
  const onKey = (e) => {
    if (e.key === "Escape") end();
    else if (e.key === "ArrowRight") { i += 1; show(1); }
    else if (e.key === "ArrowLeft" && i > 0) { i -= 1; show(-1); }
  };

  function start() {
    if (pop) end();
    document.querySelector(".app-shell")?.classList.remove("sb-open");
    i = 0;
    build();
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    document.addEventListener("keydown", onKey);
    show(1);
  }

  document.getElementById("tourBtn")?.addEventListener("click", start);
  document.getElementById("startTourBtn")?.addEventListener("click", start);

  let seen = false;
  try { seen = localStorage.getItem(SEEN_KEY) === "1"; } catch (_) { /* treat as not seen */ }
  if (!seen) window.addEventListener("load", () => setTimeout(start, 400));
})();
