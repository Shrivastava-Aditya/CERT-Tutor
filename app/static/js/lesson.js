// Lesson tabs (arrow keys move between them, the URL #hash remembers the open one) and copy buttons.
(function () {
  document.querySelectorAll("[data-tabs]").forEach(root => {
    const tabs = [...root.querySelectorAll('[role="tab"]')];
    const panels = [...root.querySelectorAll('[role="tabpanel"]')];

    function show(id, moveFocus) {
      tabs.forEach(t => {
        const on = t.dataset.tab === id;
        t.setAttribute("aria-selected", on);
        t.tabIndex = on ? 0 : -1;
        if (on && moveFocus) t.focus();
      });
      panels.forEach(p => { p.hidden = p.id !== `panel-${id}`; });
      history.replaceState(null, "", `#${id}`);
    }

    tabs.forEach((t, i) => {
      t.addEventListener("click", () => show(t.dataset.tab));
      t.addEventListener("keydown", e => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        const next = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
        show(next.dataset.tab, true);
      });
    });

    const fromHash = location.hash.slice(1);
    show(tabs.some(t => t.dataset.tab === fromHash) ? fromHash : tabs[0].dataset.tab);
  });

  // The clipboard API only works on https or localhost; on the LAN (http://192.168...) fall back to execCommand
  document.addEventListener("click", async e => {
    const btn = e.target.closest(".copy");
    if (!btn) return;
    const text = btn.dataset.copy;
    let ok = false;
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); ok = true; }
    } catch (err) { /* fall through */ }
    if (!ok) {
      const ta = Object.assign(document.createElement("textarea"), { value: text });
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      ta.remove();
    }
    btn.textContent = ok ? "Copied" : "Select and copy";
    btn.classList.toggle("done", ok);
    setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1600);
  });
})();
