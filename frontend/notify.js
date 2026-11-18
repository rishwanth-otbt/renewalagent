/**
 * Renewal Desk — in-app notifications (replace the browser's alert box).
 *
 *   notify({ type: "success" | "error" | "info", title, message, file, details, duration })
 *
 * - file:     a filename to show as its own chip (long names are shortened, full name on hover)
 * - details:  a list of extra lines (e.g. validation problems), shown as bullets
 * - duration: ms before it closes by itself; errors stay until closed unless one is given
 */
(function () {
  const ICONS = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="8" x2="12" y2="13"/><line x1="12" y1="16.5" x2="12.01" y2="16.5"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg>',
  };
  const FILE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>';
  const CLOSE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

  let stack;
  function getStack() {
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack no-print";
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    return stack;
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  window.notify = function notify({ type = "info", title = "", message = "", file = "", details = [], duration } = {}) {
    const ms = duration ?? (type === "error" ? 0 : 5000);
    const toast = el("div", `toast toast-${type}`);
    toast.setAttribute("role", type === "error" ? "alert" : "status");

    const icon = el("div", "toast-icon");
    icon.innerHTML = ICONS[type] || ICONS.info;

    const body = el("div", "toast-body");
    if (title) body.appendChild(el("div", "toast-title", title));
    if (file) {
      const chip = el("div", "toast-file");
      chip.title = file;
      chip.innerHTML = FILE_ICON;
      chip.appendChild(el("span", "", file));
      body.appendChild(chip);
    }
    if (message) body.appendChild(el("div", "toast-msg", message));
    if (details.length) {
      const ul = el("ul", "toast-details");
      details.slice(0, 6).forEach((d) => ul.appendChild(el("li", "", d)));
      if (details.length > 6) ul.appendChild(el("li", "", `…and ${details.length - 6} more`));
      body.appendChild(ul);
    }

    const close = el("button", "toast-close");
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = CLOSE_ICON;

    toast.append(icon, body, close);

    let timer;
    const dismiss = () => {
      clearTimeout(timer);
      toast.classList.add("leaving");
      setTimeout(() => toast.remove(), 220);
    };
    close.addEventListener("click", dismiss);

    if (ms > 0) {
      const bar = el("div", "toast-progress");
      bar.style.animationDuration = `${ms}ms`;
      toast.appendChild(bar);
      timer = setTimeout(dismiss, ms);
      // Pause while the user is reading it.
      toast.addEventListener("mouseenter", () => { clearTimeout(timer); bar.style.animationPlayState = "paused"; });
      toast.addEventListener("mouseleave", () => {
        bar.style.animationPlayState = "running";
        const left = ms * (1 - (bar.getBoundingClientRect().width / toast.getBoundingClientRect().width));
        timer = setTimeout(dismiss, Math.max(800, ms - left));
      });
    }

    getStack().appendChild(toast);
    return dismiss;
  };
})();
