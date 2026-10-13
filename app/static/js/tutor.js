// Tutor chat drawer. Any element with data-tutor opens it:
//   data-course (required), data-concept, data-attempt + data-question (ask about one result),
//   data-mode (explain | quiz | compare | why-wrong), data-prompt (first message to send), data-title
(function () {
  const drawer = document.getElementById("tutor");
  if (!drawer) return;
  const log = drawer.querySelector(".tutor-log");
  const form = drawer.querySelector("form");
  const input = drawer.querySelector("textarea");
  const title = drawer.querySelector(".tutor-title");
  const modeChips = drawer.querySelectorAll("[data-set-mode]");
  let ctx = null;          // { course, concept, attempt, question, mode, key }
  let history = [];
  let busy = false;

  const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // Just enough Markdown for tutor replies: paragraphs, lists, **bold**, *italic*, `code`
  function md(text) {
    const inline = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|\W)\*([^*\n]+)\*(?=\W|$)/g, "$1<em>$2</em>").replace(/(^|\W)_([^_\n]+)_(?=\W|$)/g, "$1<em>$2</em>");
    return text.split(/\n{2,}/).map(block => {
      const lines = block.split("\n");
      if (lines.every(l => /^\s*([-*]|\d+\.)\s+/.test(l))) {
        const ordered = /^\s*\d+\./.test(lines[0]);
        const items = lines.map(l => `<li>${inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""))}</li>`).join("");
        return ordered ? `<ol>${items}</ol>` : `<ul>${items}</ul>`;
      }
      return `<p>${lines.map(inline).join("<br>")}</p>`;
    }).join("");
  }

  const storageKey = () => `tutor:${ctx.key}`;
  function save() { try { localStorage.setItem(storageKey(), JSON.stringify(history.slice(-40))); } catch (e) { /* ignore */ } }
  function restore() { try { return JSON.parse(localStorage.getItem(storageKey())) || []; } catch (e) { return []; } }

  function bubble(role, html) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerHTML = html;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }
  function renderAll() {
    log.innerHTML = "";
    if (!history.length) bubble("hint", "<p>Ask anything about this topic, or pick a mode above.</p>");
    history.forEach(m => bubble(m.role, m.role === "user" ? `<p>${esc(m.content)}</p>` : md(m.content)));
  }
  function setMode(mode) {
    ctx.mode = mode;
    modeChips.forEach(c => c.setAttribute("aria-pressed", c.dataset.setMode === mode));
  }

  async function send(text) {
    if (busy || !text.trim()) return;
    busy = true;
    history.push({ role: "user", content: text.trim() });
    bubble("user", `<p>${esc(text.trim())}</p>`);
    const out = bubble("assistant typing", "<p><span class='dots'><i></i><i></i><i></i></span></p>");
    let reply = "";
    try {
      const res = await fetch(`/tutor/${ctx.course}/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history, mode: ctx.mode, concept: ctx.concept, attempt_id: ctx.attempt, question_id: ctx.question }),
      });
      if (!res.ok) throw new Error(`the server answered ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        reply += decoder.decode(value, { stream: true });
        out.classList.remove("typing");
        out.innerHTML = md(reply);
        log.scrollTop = log.scrollHeight;
      }
    } catch (err) {
      reply += `\n\n⚠ Couldn't reach the tutor (${err.message}).`;
      out.innerHTML = md(reply);
    }
    out.classList.remove("typing");
    history.push({ role: "assistant", content: reply });
    save();
    busy = false;
    input.focus();
  }

  function open(el) {
    const d = el.dataset;
    ctx = {
      course: d.course, concept: d.concept || null, attempt: d.attempt || null, question: d.question || null,
      key: d.question ? `${d.attempt}:${d.question}` : `concept:${d.concept || "general"}`,
    };
    title.textContent = d.title || "Tutor";
    setMode(d.mode || "explain");
    history = restore();
    renderAll();
    drawer.hidden = false;
    requestAnimationFrame(() => drawer.classList.add("open"));
    if (d.prompt && !history.length) send(d.prompt); else input.focus();
  }
  function close() {
    drawer.classList.remove("open");
    setTimeout(() => { drawer.hidden = true; }, 250);
  }

  document.addEventListener("click", e => {
    const opener = e.target.closest("[data-tutor]");
    if (opener) { e.preventDefault(); open(opener); return; }
    if (e.target.closest("[data-tutor-close]")) close();
    const chip = e.target.closest("[data-set-mode]");
    if (chip && ctx) {
      setMode(chip.dataset.setMode);
      const starters = { quiz: "Quiz me on this.", compare: "How do Azure and Google Cloud do this?", explain: "Explain this differently, please." };
      if (!busy && starters[chip.dataset.setMode]) send(starters[chip.dataset.setMode]);
    }
    if (e.target.closest("[data-tutor-clear]") && ctx) { history = []; save(); renderAll(); }
  });
  form.addEventListener("submit", e => { e.preventDefault(); const t = input.value; input.value = ""; send(t); });
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !drawer.hidden) close(); });
})();
