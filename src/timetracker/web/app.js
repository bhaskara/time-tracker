// Time Tracker day view: polls the API, renders the timer, progress bar and
// session list, and maps keyboard shortcuts to API calls. Uses common.js.
"use strict";

const POLL_MS = 3000;
// Latest /api/status response and the local time it arrived, so the clock can
// tick between polls without asking the server.
let state = null;
let fetchedAt = 0;
let formDirty = false;
// Session list interaction: the highlighted row, the row being edited
// ({id} for an existing session, {id: null} for a new one), and the row for
// which a first "x" has been pressed.
let selectedId = null;
let editing = null;
let armedDelete = null;

function showMessage(text) {
  $("msg").textContent = text;
}

async function refresh() {
  try {
    state = await api("GET", "/api/status");
    fetchedAt = Date.now();
    render();
  } catch (e) {
    showMessage(`Cannot reach the server: ${e.message}`);
  }
}

// Run an API action, then refresh; show the server's reason if it refuses.
async function act(method, path, body) {
  showMessage("");
  try {
    await api(method, path, body);
  } catch (e) {
    showMessage(e.message);
  }
  await refresh();
}

// A whole number of minutes as the big figure plus its unit, e.g. ["15",
// "minutes"] or ["1h 05m", ""].
function minutesFigure(minutes) {
  if (minutes >= 60) return [`${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`, ""];
  return [String(minutes), minutes === 1 ? "minute" : "minutes"];
}

// What the big panel should show right now, derived from the last status.
// Only whole minutes are shown: time left is rounded up (so it reads 1 until
// the end), time elapsed or over is rounded down.
function nowView() {
  const sinceFetch = (Date.now() - fetchedAt) / 1000;
  const active = state.active;
  const view = (kind, heading, minutes, suffix, sub, prefix = "") => {
    const [figure, unit] = minutesFigure(minutes);
    return {
      kind, heading, sub,
      figure: prefix + figure,
      unit: `${unit} ${suffix}`.trim(),
      label: active ? active.label : "",
    };
  };
  if (!active) {
    const today = state.today;
    const last = today.sessions[today.sessions.length - 1];
    if (today.signed_off_at) {
      return { kind: "idle", heading: "Signed off", figure: "done", unit: "", label: "", sub: `Signed off at ${timeOfDay(today.signed_off_at)}` };
    }
    if (!last) {
      return { kind: "idle", heading: "No session", figure: "–", unit: "", label: "", sub: "Press w to start" };
    }
    const idle = Math.floor((Date.now() - Date.parse(last.end)) / 60000);
    return view("idle", "No session", idle, "idle", `since the last session ended at ${timeOfDay(last.end)}`);
  }
  const elapsed = state.elapsed_s + sinceFetch;
  const started = `started ${timeOfDay(active.start)}`;
  if (active.type === "distraction") {
    return view("distraction", "Distraction", Math.floor(elapsed / 60), "so far", started);
  }
  const remaining = state.remaining_s - sinceFetch;
  if (active.type === "break") {
    return { ...view("break", "Break", Math.max(0, Math.ceil(remaining / 60)), "left", `${started} · ends when the credit runs out`), expired: remaining <= 0 };
  }
  const planned = `planned ${duration(active.planned_s)} · ${started}`;
  if (remaining < 0 && remaining > -60) {
    return view("overrun", "Work · time's up", 0, "left", planned);
  }
  if (remaining < 0) {
    return view("overrun", "Work · past planned end", Math.floor(-remaining / 60), "over", planned, "+");
  }
  return view("work", "Work", Math.ceil(remaining / 60), "left", planned);
}

function renderNow() {
  if (!state) return;
  const view = nowView();
  $("now").dataset.kind = view.kind;
  $("kind").textContent = view.heading;
  $("timer-figure").textContent = view.figure;
  $("timer-unit").textContent = view.unit;
  $("label").textContent = view.label || "\u00a0";
  $("sub").textContent = view.sub;
  // The server ends a break at its cap; fetch the new state once that passes.
  if (view.expired && Date.now() - fetchedAt > 1000) refresh();
}

function renderProgress() {
  const t = state.today;
  const pct = (seconds) => `${Math.min(100, (100 * seconds) / t.target_s)}%`;
  $("bar-work").style.width = pct(t.work_s);
  $("bar-break").style.width = pct(Math.min(t.break_s, Math.max(0, t.target_s - t.work_s)));
  $("bar-distraction").style.width = pct(t.distraction_s);
  $("counted-text").textContent = `${duration(t.counted_s)} counted (${Math.round(100 * t.progress)}%)`;
  $("work-text").textContent = duration(t.work_s);
  $("break-text").textContent = duration(t.break_s);
  $("distraction-text").textContent = duration(t.distraction_s);
  if ($("target-input").hidden) $("target-text").textContent = duration(t.target_s);
}

// Local "HH:MM" of an ISO timestamp, as used by <input type="time">.
function hhmm(iso) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// ISO timestamp for a local "HH:MM" on the displayed tracking day. Times
// before the day-start hour belong to the following calendar date.
function toIso(time) {
  const [year, month, day] = state.today.day.split("-").map(Number);
  const [hours, minutes] = time.split(":").map(Number);
  const nextDate = hours < state.day_start_hour ? 1 : 0;
  return new Date(year, month - 1, day + nextDate, hours, minutes).toISOString();
}

function serverNow() {
  return Date.parse(state.now) + (Date.now() - fetchedAt);
}

function listOrder() {
  return [...state.today.sessions].reverse();
}

// Inline form for editing a session (or creating one when s is null).
function appendEditRow(body, s) {
  const row = body.insertRow();
  row.className = "edit";
  const cell = row.insertCell();
  cell.colSpan = 5;
  const form = document.createElement("form");
  form.id = "edit-form";
  form.autocomplete = "off";
  form.innerHTML = `
    <select name="type" aria-label="Type">
      <option value="work">work</option><option value="break">break</option><option value="distraction">distraction</option>
    </select>
    <input name="start" type="time" aria-label="Start" required>
    <span class="unit">to</span>
    <input name="end" type="time" aria-label="End">
    <input name="label" type="text" placeholder="Label" aria-label="Label">
    <input name="planned" type="number" min="0.05" step="any" aria-label="Planned minutes">
    <span class="unit">min planned</span>
    <button type="submit">Save</button>`;
  const f = form.elements;
  if (s) {
    f.type.value = s.type;
    f.start.value = hhmm(s.start);
    f.end.value = s.end ? hhmm(s.end) : "";
    f.label.value = s.label;
    f.planned.value = s.planned_s ? s.planned_s / 60 : "";
  } else {
    f.end.required = true;
  }
  form.addEventListener("submit", (event) => { event.preventDefault(); saveEdit(form, s); });
  cell.append(form);
}

function renderSessions() {
  // Leave the table alone while a row is being edited, so polling does not
  // wipe what is being typed.
  if (editing && $("edit-form")) return;
  const body = $("sessions").tBodies[0];
  body.replaceChildren();
  const sessions = listOrder();
  if (!sessions.some((s) => s.id === selectedId)) selectedId = null;
  const adding = editing && editing.id === null;
  $("empty").hidden = sessions.length > 0 || adding;
  $("sessions").hidden = sessions.length === 0 && !adding;
  if (adding) appendEditRow(body, null);
  for (const s of sessions) {
    if (editing && editing.id === s.id) {
      appendEditRow(body, s);
      continue;
    }
    const className = [s.end ? "" : "active", s.id === selectedId ? "selected" : ""].join(" ").trim();
    appendSessionRow(body, s, className);
  }
}

function moveSelection(delta) {
  const list = listOrder();
  if (!list.length || editing) return;
  const index = list.findIndex((s) => s.id === selectedId);
  const next = index < 0 ? (delta > 0 ? 0 : list.length - 1) : Math.min(list.length - 1, Math.max(0, index + delta));
  selectedId = list[next].id;
  armedDelete = null;
  showMessage("");
  renderSessions();
}

function startEdit(id) {
  editing = { id };
  renderSessions();
  $("edit-form").elements[id === null ? "type" : "start"].focus();
}

function cancelEdit() {
  if (!editing) return false;
  editing = null;
  renderSessions();
  return true;
}

// Send only what changed, so untouched times keep their seconds.
async function saveEdit(form, s) {
  const f = form.elements;
  const planned = f.type.value === "work" && f.planned.value ? Number(f.planned.value) : null;
  let method, path;
  const body = {};
  if (!s) {
    method = "POST";
    path = "/api/sessions";
    Object.assign(body, { type: f.type.value, label: f.label.value.trim(), start: toIso(f.start.value), end: toIso(f.end.value) });
    if (planned) body.planned_minutes = planned;
  } else {
    method = "PATCH";
    path = `/api/sessions/${s.id}`;
    if (f.type.value !== s.type) body.type = f.type.value;
    if (f.label.value.trim() !== s.label) body.label = f.label.value.trim();
    if (f.start.value !== hhmm(s.start)) body.start = toIso(f.start.value);
    const originalEnd = s.end ? hhmm(s.end) : "";
    if (f.end.value !== originalEnd) {
      if (f.end.value) body.end = toIso(f.end.value);
      else body.reopen = true;
    }
    if (planned && planned !== (s.planned_s || 0) / 60) body.planned_minutes = planned;
  }
  try {
    if (Object.keys(body).length) await api(method, path, body);
  } catch (e) {
    // Keep the form open so the entry can be corrected.
    showMessage(e.message);
    return;
  }
  showMessage("");
  editing = null;
  await refresh();
}

function deleteSelected() {
  if (!selectedId || editing) return;
  if (armedDelete !== selectedId) {
    armedDelete = selectedId;
    showMessage("Press x again to delete the selected session.");
    return;
  }
  armedDelete = null;
  act("DELETE", `/api/sessions/${selectedId}`);
}

// Record the break that followed the selected (finished work) session.
function breakAfterSelected() {
  if (!selectedId || editing) {
    showMessage("Select a finished work session first (j / k).");
    return;
  }
  act("POST", `/api/sessions/${selectedId}/break`);
}

function openAgo() {
  if (!state.active) {
    showMessage("No session is running.");
    return;
  }
  $("ago").hidden = false;
  $("ago-min").value = "";
  $("ago-min").focus();
}

function submitAgo() {
  const minutes = Number($("ago-min").value);
  $("ago").hidden = true;
  if (!(minutes >= 0) || !state.active) return;
  const start = new Date(serverNow() - minutes * 60000).toISOString();
  act("PATCH", `/api/sessions/${state.active.id}`, { start });
}

function renderForm() {
  const editing = document.activeElement === $("f-label") || document.activeElement === $("f-min");
  if (formDirty || editing) return;
  $("f-label").value = state.defaults.label;
  $("f-min").value = state.defaults.planned_minutes;
}

function render() {
  renderNow();
  renderProgress();
  renderSessions();
  renderForm();
}

function startWorkFromForm() {
  const minutes = Number($("f-min").value);
  if (!(minutes > 0)) {
    showMessage("Enter a duration in minutes.");
    return;
  }
  formDirty = false;
  document.activeElement.blur();
  act("POST", "/api/sessions", { type: "work", label: $("f-label").value.trim(), planned_minutes: minutes });
}

function editTarget() {
  const input = $("target-input");
  input.value = state.today.target_s / 3600;
  $("target-text").hidden = true;
  input.hidden = false;
  input.focus();
  input.select();
}

function closeTarget(save) {
  const input = $("target-input");
  if (input.hidden) return;
  const hours = Number(input.value);
  input.hidden = true;
  $("target-text").hidden = false;
  if (save && hours > 0) act("PUT", "/api/days/today", { target_hours: hours });
}

const ACTIONS = {
  focus: () => { $("f-label").focus(); $("f-label").select(); },
  repeat: () => act("POST", "/api/sessions", { type: "work" }),
  break: () => act("POST", "/api/sessions", { type: "break" }),
  distraction: () => act("POST", "/api/sessions", { type: "distraction" }),
  end: () => act("POST", "/api/sessions/end"),
  signoff: () => act("POST", "/api/days/today/signoff"),
  target: editTarget,
  ago: openAgo,
  down: () => moveSelection(1),
  up: () => moveSelection(-1),
  edit: () => { if (selectedId) startEdit(selectedId); },
  add: () => startEdit(null),
  remove: deleteSelected,
  breakAfter: breakAfterSelected,
  review: () => { window.location.href = "review.html"; },
  help: () => { $("help").hidden = !$("help").hidden; },
};

const KEYS = {
  w: "focus", r: "repeat", b: "break", d: "distraction", e: "end", s: "signoff", t: "target", "?": "help",
  a: "ago", v: "review", j: "down", ArrowDown: "down", k: "up", ArrowUp: "up", Enter: "edit", n: "add", x: "remove", B: "breakAfter",
};

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const inField = ["INPUT", "SELECT"].includes(event.target.tagName);
  if (event.key === "Escape") {
    $("help").hidden = true;
    $("ago").hidden = true;
    closeTarget(false);
    // Drop focus from whatever has it (a field or a clicked button).
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
    if (!cancelEdit() && !inField) {
      selectedId = null;
      armedDelete = null;
      showMessage("");
      renderSessions();
    }
    return;
  }
  if (inField) return;
  // Let Enter activate a focused button as usual.
  if (event.key === "Enter" && event.target.tagName === "BUTTON") return;
  const action = KEYS[event.key];
  if (action) {
    event.preventDefault();
    ACTIONS[action]();
  }
});

$("start").addEventListener("submit", (event) => { event.preventDefault(); startWorkFromForm(); });
$("start").addEventListener("input", () => { formDirty = true; });
$("actions").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  // Release focus so a later Enter goes to the session list, not this button.
  button.blur();
  ACTIONS[button.dataset.act]();
});
$("target-text").addEventListener("click", editTarget);
$("target-input").addEventListener("keydown", (event) => { if (event.key === "Enter") closeTarget(true); });
$("target-input").addEventListener("blur", () => closeTarget(false));
$("help").addEventListener("click", () => { $("help").hidden = true; });
$("ago").addEventListener("submit", (event) => { event.preventDefault(); submitAgo(); });

refresh();
setInterval(refresh, POLL_MS);
setInterval(renderNow, 1000);
