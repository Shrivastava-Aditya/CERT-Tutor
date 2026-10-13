// Test simulator in the browser. The server keeps the questions and grades the answers.
// Progress is saved in localStorage, so a refresh or a closed tab doesn't lose your answers.
(function () {
  const cfg = JSON.parse(document.getElementById("exam-config").textContent);
  const root = document.getElementById("exam");
  const timerEl = document.getElementById("timer");
  const progEl = document.getElementById("prog");
  const qs = cfg.questions;
  const KEY = `attempt-${cfg.id}`;
  const LETTERS = "ABCDE";
  // The server's clock decides when time is up; remember how far this device's clock is off
  const clockOffset = cfg.serverNow * 1000 - Date.now();

  let st = load() || { i: 0, answers: {}, flags: {}, seconds: {}, revealed: {} };
  let view = "question";      // question | review
  let confirmEnd = false;
  let limitWarn = false;
  let submitting = false;
  let shownAt = Date.now();

  function load() { try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; } }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) { /* private mode: keep going */ } }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const remaining = () => cfg.endsAt ? (cfg.endsAt * 1000 - (Date.now() + clockOffset)) / 1000 : null;
  const answered = q => (st.answers[q.id] || []).length === q.choose;
  const fmt = s => {
    s = Math.max(0, Math.round(s));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(sec).padStart(2, "0");
  };

  // Count time spent on the question on screen, for the "time sinks" insight
  function track() {
    const q = qs[st.i], now = Date.now();
    if (view === "question") st.seconds[q.id] = (st.seconds[q.id] || 0) + (now - shownAt) / 1000;
    shownAt = now;
  }

  // Wrap each clue phrase in <mark>, longest first, with a stagger so they light up one by one
  function withClues(stem, clues) {
    let html = esc(stem), i = 0;
    [...(clues || [])].sort((a, b) => b.length - a.length).forEach(clue => {
      const re = new RegExp(esc(clue).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
      html = html.replace(re, m => `<mark class="clue-hit" style="--i:${i++}">${m}</mark>`);
    });
    return html;
  }

  // ---------------- question view ----------------
  function questionView() {
    const q = qs[st.i];
    const sel = st.answers[q.id] || [];
    const revealed = cfg.study && st.revealed[q.id];
    const right = revealed ? q.options.filter(o => o.correct).map(o => o.id) : [];
    const gotIt = revealed && sel.length === right.length && sel.every(id => right.includes(id));

    const options = q.options.map((o, pos) => {
      let cls = "opt " + (q.choose > 1 ? "multi" : "single");
      if (revealed) cls += o.correct ? " is-right" : sel.includes(o.id) ? " is-wrong" : "";
      const why = revealed && sel.includes(o.id) && !o.correct && o.trap_why
        ? `<span class="opt-why">Trap: ${esc(o.trap_why)}</span>` : "";
      return `<button class="${cls}" role="${q.choose > 1 ? "checkbox" : "radio"}" aria-checked="${sel.includes(o.id)}"
                data-act="opt" data-id="${o.id}" ${revealed ? "disabled" : ""}>
                <span class="k">${LETTERS[pos]}</span><span class="opt-text">${esc(o.text)}${why}</span></button>`;
    }).join("");

    const instr = q.choose > 1
      ? `<p class="instr${limitWarn ? " warn" : ""}">${limitWarn ? `You can choose ${q.choose}. Deselect one first.` : `Choose ${q.choose === 2 ? "two" : "three"}.`}</p>`
      : "";

    const feedback = revealed ? `
      <div class="feedback ${gotIt ? "good" : "bad"}">
        <p class="fb-head">${gotIt ? "Correct" : "Not quite"}${gotIt ? ' <span class="xp-pop">+10 XP</span>' : ""}</p>
        <div class="rule fb-rule"><span class="rule-label">Pattern</span><span>${esc(q.rule)}</span></div>
        <p>${esc(q.explain)}</p>
        <a class="fb-link" href="/course/${cfg.course}/${q.concept}" target="_blank" rel="noopener">Review ${esc(q.concept_title)} →</a>
      </div>` : "";

    const last = st.i === qs.length - 1;
    const checkBtn = cfg.study && !revealed
      ? `<button class="btn" data-act="reveal" ${sel.length === q.choose ? "" : "disabled"}>Check answer</button>` : "";

    return `
      <div class="q-head">
        <span class="q-num">Question ${st.i + 1} of ${qs.length}</span>
        <button class="flag-btn" data-act="flag" aria-pressed="${!!st.flags[q.id]}">⚑ ${st.flags[q.id] ? "Flagged" : "Flag for review"}</button>
      </div>
      <p class="q-stem">${revealed ? withClues(q.stem, q.clues) : esc(q.stem)}</p>
      ${instr}
      <div class="opts ${revealed && !gotIt ? "shake" : ""}" role="${q.choose > 1 ? "group" : "radiogroup"}" aria-label="Answer options">${options}</div>
      ${feedback}
      <p class="kbd-hint"><kbd>A</kbd>–<kbd>E</kbd> choose · <kbd>←</kbd> <kbd>→</kbd> move · <kbd>F</kbd> flag${cfg.study ? " · <kbd>Enter</kbd> check" : ""}</p>
      <div class="exam-nav">
        <button class="btn" data-act="prev" ${st.i === 0 ? "disabled" : ""}>Previous</button>
        <div class="exam-nav-mid">${checkBtn}<button class="btn" data-act="review">Review all</button></div>
        ${last ? `<button class="btn primary" data-act="review">Finish</button>` : `<button class="btn primary" data-act="next">Next</button>`}
      </div>`;
  }

  // ---------------- review grid ----------------
  function reviewView() {
    const done = qs.filter(answered).length;
    const flagged = qs.filter(q => st.flags[q.id]).length;
    const open = qs.length - done;
    const tiles = qs.map((q, i) => `
      <button class="tile${answered(q) ? " ans" : ""}${st.flags[q.id] ? " flg" : ""}" data-act="goto" data-i="${i}"
        aria-label="Question ${i + 1}${answered(q) ? ", answered" : ", not answered"}${st.flags[q.id] ? ", flagged" : ""}">${i + 1}</button>`).join("");
    const confirm = confirmEnd ? `
      <div class="confirm">
        <p><b>End now?</b> ${open ? `${open} question${open === 1 ? " is" : "s are"} unanswered and will count as wrong.` : "Every question is answered."} You can't change answers after this.</p>
        <div class="row"><button class="btn danger" data-act="submit" ${submitting ? "disabled" : ""}>${submitting ? "Scoring…" : "End and score"}</button>
        <button class="btn" data-act="cancel">Keep going</button></div>
      </div>` : "";
    return `
      <h2>Review your answers</h2>
      <div class="counts"><div><b>${done}</b><span>answered</span></div><div><b>${open}</b><span>unanswered</span></div><div><b>${flagged}</b><span>flagged</span></div></div>
      <div class="legend"><span><i class="sw ans"></i>Answered</span><span><i class="sw"></i>Unanswered</span><span><i class="sw flg"></i>Flagged</span></div>
      <div class="grid">${tiles}</div>
      ${confirm}
      <div class="row">
        ${flagged ? `<button class="btn" data-act="first-flag">First flagged</button>` : ""}
        ${open ? `<button class="btn" data-act="first-open">First unanswered</button>` : ""}
        <button class="btn" data-act="back">Back to question ${st.i + 1}</button>
        ${confirmEnd ? "" : `<button class="btn primary" data-act="ask-end">End exam</button>`}
      </div>
      <p class="error" id="submit-error" hidden></p>`;
  }

  function render() {
    root.innerHTML = view === "question" ? questionView() : reviewView();
    progEl.style.width = `${100 * qs.filter(answered).length / qs.length}%`;
  }

  // ---------------- actions ----------------
  function choose(id) {
    const q = qs[st.i];
    if (cfg.study && st.revealed[q.id]) return;
    let sel = st.answers[q.id] || [];
    limitWarn = false;
    if (q.choose === 1) sel = [id];
    else if (sel.includes(id)) sel = sel.filter(x => x !== id);
    else if (sel.length < q.choose) sel = [...sel, id];
    else { limitWarn = true; render(); return; }
    st.answers[q.id] = sel;
    save(); render();
  }
  function go(i) {
    track();
    st.i = Math.max(0, Math.min(qs.length - 1, i));
    view = "question"; limitWarn = false;
    save(); render(); window.scrollTo(0, 0);
  }
  function reveal() {
    const q = qs[st.i];
    if ((st.answers[q.id] || []).length !== q.choose) return;
    st.revealed[q.id] = true;
    save(); render();
  }
  async function submit() {
    if (submitting) return;
    track();
    submitting = true; render();
    try {
      const res = await fetch(`/attempt/${cfg.id}/submit`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: st.answers, flags: st.flags, seconds: st.seconds }),
      });
      if (!res.ok) throw new Error(`The server answered ${res.status}`);
      const { redirect } = await res.json();
      try { localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
      location.href = redirect;
    } catch (err) {
      submitting = false; view = "review"; confirmEnd = true; render();
      const el = document.getElementById("submit-error");
      el.hidden = false;
      el.textContent = `Couldn't submit (${err.message}). Your answers are saved on this device. Check the connection and press "End and score" again.`;
    }
  }

  root.addEventListener("click", e => {
    const b = e.target.closest("[data-act]");
    if (!b || b.disabled) return;
    const act = b.dataset.act;
    if (act === "opt") choose(b.dataset.id);
    else if (act === "flag") { const id = qs[st.i].id; st.flags[id] = !st.flags[id]; save(); render(); }
    else if (act === "reveal") reveal();
    else if (act === "prev") go(st.i - 1);
    else if (act === "next") go(st.i + 1);
    else if (act === "review") { track(); view = "review"; confirmEnd = false; render(); window.scrollTo(0, 0); }
    else if (act === "goto") go(+b.dataset.i);
    else if (act === "back") go(st.i);
    else if (act === "first-flag") go(qs.findIndex(q => st.flags[q.id]));
    else if (act === "first-open") go(qs.findIndex(q => !answered(q)));
    else if (act === "ask-end") { confirmEnd = true; render(); }
    else if (act === "cancel") { confirmEnd = false; render(); }
    else if (act === "submit") submit();
  });

  document.addEventListener("keydown", e => {
    if (view !== "question" || e.metaKey || e.ctrlKey || e.altKey) return;
    const q = qs[st.i], key = e.key.toLowerCase();
    let pos = "abcde".indexOf(key);
    if (pos < 0) pos = "12345".indexOf(key);
    if (pos >= 0 && pos < q.options.length) { e.preventDefault(); choose(q.options[pos].id); }
    else if (e.key === "ArrowRight") { e.preventDefault(); if (st.i < qs.length - 1) go(st.i + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); if (st.i > 0) go(st.i - 1); }
    else if (key === "f") { e.preventDefault(); st.flags[q.id] = !st.flags[q.id]; save(); render(); }
    else if (e.key === "Enter" && cfg.study && !st.revealed[q.id]) { e.preventDefault(); reveal(); }
  });

  // ---------------- timer ----------------
  function tick() {
    const left = remaining();
    if (left === null) { timerEl.textContent = cfg.study ? "Study mode" : "Untimed"; return; }
    timerEl.textContent = fmt(left);
    timerEl.classList.toggle("low", left < 600);
    if (left <= 0 && !submitting) { timerEl.textContent = "Time's up"; submit(); }
  }
  setInterval(tick, 1000);
  tick();
  render();
})();
