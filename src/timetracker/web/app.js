// Time Tracker day view: polls the API, renders the timer, progress bar and
// session list, and maps keyboard shortcuts to API calls.
"use strict";

const POLL_MS = 3000;
const $ = (id) => document.getElementById(id);

// Latest /api/status response and the local time it arrived, so the clock can
// tick between polls without asking the server.
let state = null;
let fetchedAt = 0;
let formDirty = false;

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "content-type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail);
  }
  return data;
}

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

function duration(seconds) {
  if (seconds > 0 && seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
}

function timeOfDay(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// A whole number of minutes as the big figure plus its unit, e.g. ["15",
// "minutes"] or ["1h 05m", ""].
function minutesFigure(minutes) {
  if (minutes >= 60) return [`${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`, ""];
  return [String(minutes), minutes === 1 ? "minute" : "minutes"];
}

// Short form for the tab title, e.g. "15m" or "1h 05m".
function minutesShort(minutes) {
  return minutes >= 60 ? minutesFigure(minutes)[0] : `${minutes}m`;
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
      title: `${prefix}${minutesShort(minutes)} ${suffix}${active && active.label ? ` · ${active.label}` : ""}`,
    };
  };
  if (!active) {
    const today = state.today;
    const last = today.sessions[today.sessions.length - 1];
    if (today.signed_off_at) {
      return { kind: "idle", heading: "Signed off", figure: "done", unit: "", label: "", sub: `Signed off at ${timeOfDay(today.signed_off_at)}`, title: "Signed off" };
    }
    if (!last) {
      return { kind: "idle", heading: "No session", figure: "–", unit: "", label: "", sub: "Press w to start", title: "Time Tracker" };
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
  document.title = view.title;
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

function accountingNote(s) {
  if (s.type === "work") {
    const over = s.duration_s - s.planned_s;
    return over > 60 ? `${duration(over)} past planned ${duration(s.planned_s)}` : `planned ${duration(s.planned_s)}`;
  }
  if (s.type === "break") return `${duration(s.counted_s)} credited`;
  return `charged ${duration(s.distraction_s)} (includes switch cost)`;
}

function renderSessions() {
  const body = $("sessions").tBodies[0];
  body.replaceChildren();
  const sessions = [...state.today.sessions].reverse();
  $("empty").hidden = sessions.length > 0;
  $("sessions").hidden = sessions.length === 0;
  for (const s of sessions) {
    const row = body.insertRow();
    if (!s.end) row.className = "active";
    const cells = [
      ["time", `${timeOfDay(s.start)} – ${s.end ? timeOfDay(s.end) : "now"}`],
      [`type type-${s.type}`, s.type],
      ["", s.label],
      ["num", duration(s.duration_s)],
      ["note", accountingNote(s)],
    ];
    for (const [cls, text] of cells) {
      const cell = row.insertCell();
      cell.className = cls;
      cell.textContent = text;
    }
  }
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
  help: () => { $("help").hidden = !$("help").hidden; },
};

const KEYS = { w: "focus", r: "repeat", b: "break", d: "distraction", e: "end", s: "signoff", t: "target", "?": "help" };

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const inField = event.target.tagName === "INPUT";
  if (event.key === "Escape") {
    $("help").hidden = true;
    closeTarget(false);
    if (inField) event.target.blur();
    return;
  }
  if (inField) return;
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
  if (button) ACTIONS[button.dataset.act]();
});
$("target-text").addEventListener("click", editTarget);
$("target-input").addEventListener("keydown", (event) => { if (event.key === "Enter") closeTarget(true); });
$("target-input").addEventListener("blur", () => closeTarget(false));
$("help").addEventListener("click", () => { $("help").hidden = true; });

refresh();
setInterval(refresh, POLL_MS);
setInterval(renderNow, 1000);
