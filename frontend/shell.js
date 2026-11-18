/**
 * Renewal Desk — app shell behaviour shared by every page:
 * sidebar collapse (desktop), mobile sidebar toggle, info tips, and the brief's section scroll-spy.
 */
(function () {
  const shell = document.querySelector(".app-shell");
  if (!shell) return;

  // Desktop: collapse the sidebar to an icon strip. Remembered per browser.
  const COLLAPSE_KEY = "renewalDesk.sidebarCollapsed";
  const collapseBtn = document.getElementById("sbCollapse");
  // remember=false: collapse for now only (e.g. when a run starts), so the next visit
  // still opens with the sidebar and its upload panel showing.
  const setCollapsed = (on, remember = true) => {
    shell.classList.toggle("sb-collapsed", on);
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-expanded", String(!on));
      const label = on ? "Expand sidebar" : "Collapse sidebar";
      collapseBtn.setAttribute("aria-label", label);
      collapseBtn.title = label;
    }
    if (!remember) return;
    try { localStorage.setItem(COLLAPSE_KEY, on ? "1" : "0"); } catch (_) { /* storage blocked: fine */ }
  };
  window.collapseSidebar = () => setCollapsed(true, false);
  let startCollapsed = false;
  try { startCollapsed = localStorage.getItem(COLLAPSE_KEY) === "1"; } catch (_) { /* default open */ }
  setCollapsed(startCollapsed);
  collapseBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    setCollapsed(!shell.classList.contains("sb-collapsed"));
  });

  // Info tips explain; clicking one must not trigger the link or button it sits in.
  document.querySelectorAll(".info-tip").forEach(t => t.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
  }));

  const close = () => shell.classList.remove("sb-open");
  document.getElementById("sbToggle")?.addEventListener("click", () => shell.classList.toggle("sb-open"));
  document.getElementById("sbBackdrop")?.addEventListener("click", close);
  // Buttons marked data-keep-open (upload panel controls) leave the mobile sidebar open.
  document.querySelectorAll(".sidebar a, .sidebar button:not([data-keep-open])").forEach(el => el.addEventListener("click", close));
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

  // Scroll-spy: highlight the brief section currently in view.
  const links = [...document.querySelectorAll(".sb-section-link")];
  if (!links.length || !("IntersectionObserver" in window)) return;
  const ids = links.map(l => l.getAttribute("href").slice(1));
  const visible = new Set();
  const observer = new IntersectionObserver(entries => {
    entries.forEach(e => (e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id)));
    const current = ids.find(id => visible.has(id));
    if (current) links.forEach(l => l.classList.toggle("active", l.getAttribute("href") === `#${current}`));
  }, { rootMargin: "-10% 0px -55% 0px" });
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
})();
