let token = "";
let current = null;
let previewMode = "instructor";
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const stamp = (value) => value ? new Date(value).toLocaleString() : "Not saved yet";

function toast(message, bad = false) {
  const el = $("toast");
  el.textContent = message;
  el.style.background = bad ? "var(--amber)" : "var(--teal)";
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), 3000);
}

async function api(path, payload) {
  const response = await fetch(path, {
    method: payload === undefined ? "GET" : "POST",
    headers: payload === undefined ? {} : { "Content-Type": "application/json", "X-Request-Token": token },
    body: payload === undefined ? undefined : JSON.stringify(payload)
  });
  const type = response.headers.get("content-type") || "";
  const body = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof body === "string" ? body.slice(0, 220) : body.error || "Request failed");
  return body;
}

function fmt(value) {
  return Number.isInteger(value) ? String(value) : Number(value).toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function formData() {
  return {
    id: current.lesson.id,
    title: $("lesson-title").value,
    question: $("lesson-question").value,
    audience: $("lesson-audience").value,
    learning_goal: $("lesson-goal").value,
    worked_example: $("lesson-example").value,
    data: $("lesson-data").value.split(",").map((x) => x.trim()).filter(Boolean).map(Number),
    learner_prompt: $("lesson-prompt").value
  };
}

function fillLesson() {
  const x = current.lesson;
  $("lesson-title").value = x.title;
  $("lesson-question").value = x.question;
  $("lesson-audience").value = x.audience;
  $("lesson-goal").value = x.learning_goal;
  $("lesson-example").value = x.worked_example;
  $("lesson-data").value = x.data.map(fmt).join(", ");
  $("lesson-prompt").value = x.learner_prompt;
}

function renderSources() {
  $("source-count").textContent = current.sources.length;
  $("source-list").innerHTML = current.sources.map((source) => `
    <article class="source-card" data-source-card="${esc(source.id)}">
      <div class="source-top"><h3>${esc(source.title)}</h3><span class="status-pill ${source.source_reviewed ? "reviewed" : ""}">${source.source_reviewed ? "REVIEWED" : "CHECK SOURCE"}</span></div>
      <p class="source-section">${esc(source.section || "Source reference")} · v${source.version}</p>
      <p class="source-notes">${esc(source.notes || "Add a note about what you checked.")}</p>
      <div class="source-meta"><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a><span>Checked: ${esc(source.checked_at || "Not reviewed")}</span><span>Credit: ${esc(source.attribution)}</span><a href="${esc(source.license_url)}" target="_blank" rel="noopener noreferrer">License details ↗</a></div>
      <details class="source-edit"><summary>Edit source details</summary><div class="source-form source-edit-form">
        <label>Title<input data-field="title" maxlength="180" value="${esc(source.title)}"></label>
        <label>HTTPS link<input data-field="url" maxlength="1000" value="${esc(source.url)}"></label>
        <label>Section<input data-field="section" maxlength="160" value="${esc(source.section)}"></label>
        <label>Review notes<textarea data-field="notes" maxlength="1000" rows="2">${esc(source.notes)}</textarea></label>
        <label>Attribution<input data-field="attribution" maxlength="200" value="${esc(source.attribution)}"></label>
        <label>License link<input data-field="license_url" maxlength="1000" value="${esc(source.license_url)}"></label>
        <button class="small-button" data-action="save-source" data-id="${esc(source.id)}">Save source changes</button>
      </div></details>
      <div class="source-actions"><button class="small-button" data-action="review-source" data-id="${esc(source.id)}">${source.source_reviewed ? "Confirm source check" : "Mark source reviewed"}</button></div>
    </article>`).join("") || '<p class="empty-note">Add a public source you have read.</p>';
}

function renderClaims() {
  $("claim-list").innerHTML = current.claims.map((claim, index) => {
    const checked = new Set(claim.source_ids);
    const sources = current.sources.map((source) => `<label><input type="checkbox" data-field="source" value="${esc(source.id)}" ${checked.has(source.id) ? "checked" : ""} ${claim.is_inference ? "disabled" : ""}><span>${esc(source.title)} · ${source.source_reviewed ? "reviewed" : "needs review"}</span></label>`).join("");
    return `<article class="claim-card" data-claim="${esc(claim.id)}">
      <div class="claim-card-head"><strong>STATEMENT ${String(index + 1).padStart(2, "0")}</strong><span class="claim-state ${claim.review_current ? "current" : ""}">${claim.review_current ? "REVIEW CURRENT" : "REVIEW NEEDED"}</span></div>
      <div class="claim-fields">
        <label class="visually-hidden" for="claim-text-${esc(claim.id)}">Factual statement</label>
        <textarea id="claim-text-${esc(claim.id)}" data-field="text" maxlength="500">${esc(claim.text)}</textarea>
        <div class="claim-links">${sources || '<span class="empty-note">Add a source first.</span>'}</div>
        <label class="inference-toggle"><input type="checkbox" data-field="inference" ${claim.is_inference ? "checked" : ""}> Label as an inference from the example or lesson</label>
        <textarea class="inference-note" data-field="inference_note" maxlength="500" placeholder="Explain how you reached this inference" ${claim.is_inference ? "" : "hidden"}>${esc(claim.inference_note)}</textarea>
        <input class="review-note" data-field="review_note" maxlength="500" value="${esc(claim.review_note)}" placeholder="What did you compare or calculate?">
        <div class="claim-actions"><span class="claim-state">${claim.claim_reviewed ? "Checked by a person" : "Not checked"}</span><div><button class="small-button" data-action="save-claim" data-id="${esc(claim.id)}">Save statement</button><button class="small-button" data-action="review-claim" data-id="${esc(claim.id)}">Mark reviewed</button><button class="small-button danger-small" data-action="delete-claim" data-id="${esc(claim.id)}">Remove</button></div></div>
      </div>
    </article>`;
  }).join("") || '<p class="empty-note">Add each factual sentence as a separate statement.</p>';
}

function renderRevisions() {
  $("revision-label").textContent = `Revision ${current.lesson.revision}`;
  $("revision-chip").textContent = `v${current.lesson.revision}`;
  $("updated-label").textContent = stamp(current.lesson.updated_at);
  $("revision-list").innerHTML = current.revisions.map((rev) => `<li>${esc(rev.summary)}<time>${esc(stamp(rev.created_at))} · v${rev.lesson_revision}</time></li>`).join("") || '<li>No edits saved yet.</li>';
}

function renderPreview() {
  document.querySelectorAll(".view-tab").forEach((b) => {
    const active = b.dataset.view === previewMode;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", String(active));
  });
  const lesson = current.lesson;
  const sourceNames = new Map(current.sources.map((s) => [s.id, s.title]));
  const statements = current.claims.map((claim) => `<p class="preview-claim">${esc(claim.text)} <small>${claim.is_inference ? "Inference" : claim.source_ids.map((id) => esc(sourceNames.get(id) || id)).join(" · ")}</small></p>`).join("");
  const values = current.worked_results.sorted.map(fmt).join(", ");
  const instructor = previewMode === "instructor";
  const answer = instructor ? `<div class="preview-answer">Worked answer · mean ${fmt(current.worked_results.mean)} · median ${fmt(current.worked_results.median)}</div>` : "";
  $("preview-card").innerHTML = `<p class="preview-meta">${instructor ? "INSTRUCTOR VIEW" : "LEARNER VIEW"} · ${esc(lesson.audience)}</p><h3>${esc(lesson.title)}</h3><p><strong>Question:</strong> ${esc(lesson.question)}</p><p>${esc(lesson.learning_goal)}</p>${statements}<p><strong>Worked values:</strong> ${esc(values)}</p><p class="teacher-note"><strong>Teacher note, not source checked:</strong> ${esc(lesson.worked_example)}</p>${answer}<p class="preview-sources">${instructor ? "Source attribution appears in the export. Verify every statement before you teach it." : esc(current.settings.learner_instruction)}</p>`;
  $("exercise-question").textContent = lesson.learner_prompt;
  $("exercise-values").innerHTML = current.worked_results.sorted.map((n) => `<span>${esc(fmt(n))}</span>`).join("");
}

function renderReadability() {
  const r = current.readability;
  $("grade-score").textContent = r.flesch_kincaid_grade === null ? "—" : r.flesch_kincaid_grade;
  $("ease-score").textContent = r.flesch_reading_ease === null ? "—" : r.flesch_reading_ease;
  $("word-count").textContent = r.words;
}

function renderExportState() {
  const waiting = current.claims.filter((x) => !x.review_current).length;
  $("instructor-export").disabled = !current.export_ready;
  $("learner-export").disabled = !current.export_ready;
  $("export-state").textContent = current.export_ready ? "Ready to export" : `${waiting} statement${waiting === 1 ? "" : "s"} need review`;
  $("export-copy").textContent = current.export_ready ? "Exports include source credit and review status. The learner file leaves out answers." : "Review every source and statement, or label and review an inference, to enable exports.";
}

function render() {
  fillLesson();
  renderSources();
  renderClaims();
  renderRevisions();
  renderPreview();
  renderReadability();
  renderExportState();
}

async function refresh() {
  current = await api("/api/state");
  render();
}

function readSourceForm(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function claimPayload(card) {
  const source_ids = [...card.querySelectorAll('[data-field="source"]:checked')].map((el) => el.value);
  return {
    id: card.dataset.claim,
    text: card.querySelector('[data-field="text"]').value,
    source_ids,
    is_inference: card.querySelector('[data-field="inference"]').checked,
    inference_note: card.querySelector('[data-field="inference_note"]').value
  };
}

async function saveLesson() {
  try {
    current = await api("/api/lesson", formData());
    render();
    toast("Lesson edits saved.");
  } catch (err) { toast(err.message, true); }
}

$("save-lesson").addEventListener("click", saveLesson);
$("lesson-form").addEventListener("submit", (event) => { event.preventDefault(); saveLesson(); });
$("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = readSourceForm(form);
  values.id = `src-${crypto.randomUUID()}`;
  values.section = values.section || "Reference";
  values.notes = values.notes || "";
  try { current = await api("/api/source/save", values); form.reset(); render(); toast("Source saved. Review it before linking a claim."); }
  catch (err) { toast(err.message, true); }
});

$("source-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest(".source-card");
  try {
    if (button.dataset.action === "review-source") {
      current = await api("/api/source/review", { id: button.dataset.id });
      render();
      toast("Source marked as reviewed.");
    } else if (button.dataset.action === "save-source") {
      const payload = { id: button.dataset.id };
      card.querySelectorAll("[data-field]").forEach((field) => { payload[field.dataset.field] = field.value; });
      current = await api("/api/source/save", payload);
      render();
      toast("Source saved. Linked claims may need a new review.");
    }
  } catch (err) { toast(err.message, true); }
});

$("claim-list").addEventListener("change", (event) => {
  const card = event.target.closest(".claim-card");
  if (!card || !event.target.matches('[data-field="inference"]')) return;
  const inference = event.target.checked;
  card.querySelectorAll('[data-field="source"]').forEach((box) => { box.disabled = inference; if (inference) box.checked = false; });
  card.querySelector('[data-field="inference_note"]').hidden = !inference;
});

$("claim-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest(".claim-card");
  const payload = claimPayload(card);
  try {
    if (button.dataset.action === "save-claim") {
      current = await api("/api/claim/save", payload);
      render();
      toast("Statement saved. Review it again after any edit.");
    } else if (button.dataset.action === "review-claim") {
      current = await api("/api/claim/save", payload);
      current = await api("/api/claim/review", { id: payload.id, review_note: card.querySelector('[data-field="review_note"]').value });
      render();
      toast("Statement review saved.");
    } else if (button.dataset.action === "delete-claim") {
      current = await api("/api/claim/delete", { id: payload.id });
      render();
      toast("Statement removed.");
    }
  } catch (err) { toast(err.message, true); }
});

$("add-claim").addEventListener("click", async () => {
  const id = `claim-${crypto.randomUUID()}`;
  const draft = { id, text: "", source_ids: [], is_inference: false, inference_note: "" };
  try { current = await api("/api/claim/create", draft); render(); $("claim-text-" + id).focus(); }
  catch (err) { toast(err.message, true); }
});

document.querySelectorAll(".view-tab").forEach((button) => button.addEventListener("click", () => { previewMode = button.dataset.view; renderPreview(); }));

$("check-answer").addEventListener("click", async () => {
  const feedback = $("answer-feedback");
  try {
    const answer = { mean: Number($("answer-mean").value), median: Number($("answer-median").value) };
    const result = await api("/api/check", { answer });
    feedback.textContent = result.message;
    feedback.classList.toggle("error", !result.correct);
  } catch (err) { feedback.textContent = err.message; feedback.classList.add("error"); }
});

async function download(mode) {
  try {
    const response = await fetch("/api/export", { method: "POST", headers: { "Content-Type": "application/json", "X-Request-Token": token }, body: JSON.stringify({ mode }) });
    const text = await response.text();
    if (!response.ok) {
      let message = text;
      try { message = JSON.parse(text).error; } catch { /* Plain error text remains safe in toast. */ }
      throw new Error(message || "Export failed");
    }
    const blob = new Blob([text], { type: "text/html;charset=utf-8" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = mode === "instructor" ? "lesson-instructor.html" : "lesson-learner.html";
    anchor.click();
    URL.revokeObjectURL(anchor.href);
    toast(`${mode === "instructor" ? "Instructor" : "Learner"} lesson exported.`);
  } catch (err) { toast(err.message, true); }
}
$("instructor-export").addEventListener("click", () => download("instructor"));
$("learner-export").addEventListener("click", () => download("learner"));

function fillSettings() {
  $("setting-name").value = current.settings.instructor_name;
  $("setting-grade").value = current.settings.reading_target;
  $("setting-instruction").value = current.settings.learner_instruction;
}
$("settings-open").addEventListener("click", () => { fillSettings(); $("settings-dialog").showModal(); });
$("save-settings").addEventListener("click", async () => {
  const settings = { instructor_name: $("setting-name").value, reading_target: Number($("setting-grade").value), learner_instruction: $("setting-instruction").value };
  try { current = await api("/api/settings", { settings }); $("settings-dialog").close(); render(); toast("Preferences saved locally."); }
  catch (err) { toast(err.message, true); }
});
$("reset-workspace").addEventListener("click", async () => {
  if (!window.confirm("Reset lesson, sources, review notes, and preferences to the sample?")) return;
  try { current = await api("/api/reset", {}); $("settings-dialog").close(); previewMode = "instructor"; render(); toast("Sample lesson restored."); }
  catch (err) { toast(err.message, true); }
});

async function start() {
  try {
    token = (await api("/api/token")).token;
    await refresh();
    $("lesson-data").addEventListener("keydown", (event) => { if (event.key === "Enter") event.preventDefault(); });
  } catch (err) {
    document.querySelector("main").innerHTML = `<section class="error-card"><h1>Research to Lessons</h1><p>Could not load the local lesson store. Check that the app is running.</p></section>`;
  }
}
start();
